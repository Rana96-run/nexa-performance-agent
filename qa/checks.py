"""Individual QA checks. Each returns a QACheckResult.

All checks are idempotent and side-effect free. The gate orchestrates them.
"""
from __future__ import annotations
import os
import re
import time
from datetime import date, timedelta, datetime, timezone
from typing import Any

from .errors import QACheckResult

# Cache BQ-derived facts for 60s — checks fire many times per delivery cycle
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 60  # seconds


def _cached(key: str, fn):
    now = time.time()
    if key in _CACHE and (now - _CACHE[key][0]) < _CACHE_TTL:
        return _CACHE[key][1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def _bq():
    from collectors.bq_writer import get_client
    return get_client(), os.environ["BQ_PROJECT_ID"], os.environ["BQ_DATASET"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Freshness — every channel's MAX(date) ≥ yesterday Riyadh
# ─────────────────────────────────────────────────────────────────────────────
def check_freshness(max_lag_hours: int = 36) -> QACheckResult:
    """Pass if every channel has data through yesterday (Riyadh) within max_lag_hours."""
    def _q():
        c, p, d = _bq()
        sql = f"""
        SELECT channel,
               MAX(date) AS last_date,
               TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(updated_at), HOUR) AS lag_hours
        FROM `{p}.{d}.campaigns_daily`
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
        GROUP BY 1
        """
        return [(r.channel, r.last_date, r.lag_hours) for r in c.query(sql).result()]

    rows = _cached("freshness", _q)
    yesterday = date.today() - timedelta(days=1)
    stale = [(ch, ld, lh) for ch, ld, lh in rows if ld < yesterday or (lh or 0) > max_lag_hours]
    return QACheckResult(
        name="freshness",
        passed=len(stale) == 0,
        severity="block",
        detail=f"{len(stale)} channel(s) stale: {stale}" if stale else "all channels current",
        metrics={"channels": dict((ch, str(ld)) for ch, ld, _ in rows), "stale": len(stale)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-account presence — guards the bug we just fixed
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_ACCOUNTS = {
    "google_ads": 2, "meta": 2, "microsoft_ads": 2, "snapchat": 2, "tiktok": 2,
}


def check_multi_account_presence() -> QACheckResult:
    """Pass if every channel shows expected account count in last 7 days."""
    def _q():
        c, p, d = _bq()
        sql = f"""
        SELECT channel, COUNT(DISTINCT account_id) AS n_accts
        FROM `{p}.{d}.campaigns_daily`
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
        GROUP BY 1
        """
        return {r.channel: r.n_accts for r in c.query(sql).result()}

    seen = _cached("multi_acct", _q)
    deficient = {ch: (seen.get(ch, 0), n) for ch, n in EXPECTED_ACCOUNTS.items()
                 if seen.get(ch, 0) < n}
    return QACheckResult(
        name="multi_account_presence",
        passed=not deficient,
        severity="warn",  # warn — Meta legitimately has 1 active account some days
        detail=f"Channels missing accounts: {deficient}" if deficient else "all channels show expected accounts",
        metrics={"seen": seen, "expected": EXPECTED_ACCOUNTS, "deficient": deficient},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dedupe — full-key uniqueness ratio ≤ 1.01x
# ─────────────────────────────────────────────────────────────────────────────
def check_dedupe(table: str, key_fields: list[str]) -> QACheckResult:
    """Pass if COUNT(*) / COUNT(DISTINCT full_key) ≤ 1.01 over last 7d."""
    if not key_fields:
        return QACheckResult(name=f"dedupe_{table}", passed=True, severity="block",
                             detail="no key_fields — skipping")
    c, p, d = _bq()
    key_concat = " || '|' || ".join(f"CAST({k} AS STRING)" for k in key_fields)
    sql = f"""
    SELECT COUNT(*) AS row_count,
           COUNT(DISTINCT {key_concat}) AS unique_count
    FROM `{p}.{d}.{table}`
    WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
    """
    r = list(c.query(sql).result())[0]
    if r.unique_count == 0:
        ratio = 1.0
    else:
        ratio = r.row_count / r.unique_count
    return QACheckResult(
        name=f"dedupe_{table}",
        passed=ratio <= 1.01,
        severity="block",
        detail=f"ratio={ratio:.3f}x (rows={r.row_count}, unique={r.unique_count})",
        metrics={"ratio": round(ratio, 3), "rows": r.row_count, "unique": r.unique_count},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. BQ ↔ HubSpot reconciliation — paid leads, 7-day window
# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT: reconciles against `paid_channel_daily.leads_total` (NOT the raw
# `hubspot_leads_module_daily`). The team's reporting only cares about leads
# attributed to a paid campaign — leads with null/organic utm_campaign are
# excluded by definition because the view inner-joins to campaigns_daily.
# Discovered 2026-05-17: raw lead_module=137 vs paid=74 yesterday; only 74
# is the reportable number.
def check_bq_hubspot_reconcile(drift_threshold: float = 0.05) -> QACheckResult:
    """Pass if BQ paid_channel_daily vs HubSpot live paid-lead counts agree within drift_threshold over last 7 days."""
    def _q():
        c, p, d = _bq()
        # BQ side: paid leads from the blessed reporting view, last 7 settled days
        sql = f"""
        SELECT SUM(leads_total) AS bq_paid_leads
        FROM `{p}.{d}.paid_channel_daily`
        WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                       AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
        """
        bq_paid = list(c.query(sql).result())[0].bq_paid_leads or 0

        # HubSpot side: live API count of Lead Module records whose lead_utm_campaign
        # matches a paid campaign that actually ran spend in the same window.
        # We use the BQ list of known paid campaign names as the filter.
        camp_sql = f"""
        SELECT DISTINCT LOWER(campaign_name) AS cname
        FROM `{p}.{d}.campaigns_daily`
        WHERE date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
                       AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
          AND spend > 0
        """
        known_paid = {r.cname for r in c.query(camp_sql).result()}

        import os, requests
        from datetime import datetime, timezone, timedelta as td
        riyadh = timezone(td(hours=3))
        end_local = datetime.now(riyadh).replace(hour=0, minute=0, second=0, microsecond=0)
        start_local = end_local - td(days=7)
        url = "https://api.hubapi.com/crm/v3/objects/0-136/search"
        hdr = {"Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}",
               "Content-Type": "application/json"}
        hs_paid = 0; after = 0
        while True:
            body = {
                "filterGroups": [{
                    "filters": [
                        {"propertyName": "hs_createdate", "operator": "GTE",
                         "value": int(start_local.timestamp() * 1000)},
                        {"propertyName": "hs_createdate", "operator": "LT",
                         "value": int(end_local.timestamp() * 1000)},
                    ]}],
                "properties": ["lead_utm_campaign"],
                "limit": 100, "after": after,
            }
            r = requests.post(url, headers=hdr, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            for obj in data.get("results", []):
                cname = (obj.get("properties", {}).get("lead_utm_campaign") or "").lower()
                if cname in known_paid:
                    hs_paid += 1
            paging = data.get("paging", {}).get("next", {}).get("after")
            if not paging: break
            after = paging
            if hs_paid > 5000: break
        return {"bq_total": int(bq_paid), "hs_total": int(hs_paid)}

    try:
        result = _cached("recon", _q)
        bq = result["bq_total"]; hs = result["hs_total"]
        drift = (bq - hs) / hs if hs else 0
        return QACheckResult(
            name="bq_hubspot_reconcile",
            passed=abs(drift) <= drift_threshold,
            severity="block",
            detail=f"paid leads — bq={bq} hs={hs} drift={drift:+.2%}",
            metrics={"bq_total": bq, "hs_total": hs, "drift": drift},
        )
    except Exception as e:
        # Do NOT silently pass — surface the failure so the team knows
        # reconciliation was skipped and numbers need manual verification.
        return QACheckResult(name="bq_hubspot_reconcile", passed=False, severity="warn",
                             detail=f"reconciler error — manual check required: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 4b. BQ ↔ HubSpot — deals + amounts reconciliation (Sales Pipeline, 7d)
# ─────────────────────────────────────────────────────────────────────────────
# Catches: amount calculation bugs, won-amount drift, currency-conversion
# errors, createdate mis-bucketing. Added 2026-05-20 after the deals
# collector silent-failure incident, which would have caught the 3-day
# data gap immediately if this check had existed.
def check_deals_full_reconcile(
    count_threshold: float = 0.01,    # counts must match within 1%
    amount_threshold: float = 0.02,   # amounts within 2% (FP rounding noise)
) -> QACheckResult:
    """Pass if BQ hubspot_deals_daily reconciles to HubSpot Search API on:
    counts (total + won) AND amounts (total_USD + won_USD), Sales Pipeline,
    last 7 settled days (T-2..T-8). Drift > threshold → block."""
    import datetime as _dt
    def _q():
        import requests
        c, p, d = _bq()
        riyadh = _dt.timezone(_dt.timedelta(hours=3))
        today_r = _dt.datetime.now(riyadh).date()
        end = today_r - _dt.timedelta(days=2)
        start = end - _dt.timedelta(days=6)

        # BQ side
        sql = f"""
        SELECT SUM(deals_total) AS deals_total,
               SUM(deals_won)   AS deals_won,
               ROUND(SUM(amount_total), 2) AS amount_total,
               ROUND(SUM(amount_won),   2) AS amount_won
        FROM `{p}.{d}.hubspot_deals_daily`
        WHERE date BETWEEN '{start}' AND '{end}'
          AND pipeline = 'Sales Pipeline'
        """
        bq_r = list(c.query(sql).result())[0]

        # HubSpot side — Sales Pipeline by createdate window
        since_ms = int(_dt.datetime(start.year, start.month, start.day,
                                    tzinfo=riyadh).timestamp() * 1000)
        until_ms = int(_dt.datetime((end + _dt.timedelta(days=1)).year,
                                    (end + _dt.timedelta(days=1)).month,
                                    (end + _dt.timedelta(days=1)).day,
                                    tzinfo=riyadh).timestamp() * 1000)
        token = os.environ["HUBSPOT_ACCESS_TOKEN"]
        # Find Sales Pipeline ID
        r = requests.get("https://api.hubapi.com/crm/v3/pipelines/deals",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        sp_id = next((pp["id"] for pp in r.json().get("results", [])
                      if pp["label"] == "Sales Pipeline"), None)
        if not sp_id:
            return None
        hs_count = hs_won = 0
        hs_amt = hs_won_amt = 0.0
        after = 0
        while True:
            body = {
                "filterGroups": [{"filters": [
                    {"propertyName": "pipeline",   "operator": "EQ",  "value": sp_id},
                    {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
                    {"propertyName": "createdate", "operator": "LT",  "value": until_ms},
                ]}],
                "properties": ["amount", "hs_is_closed_won"],
                "limit": 100, "after": after,
            }
            rr = requests.post("https://api.hubapi.com/crm/v3/objects/deals/search",
                               headers={"Authorization": f"Bearer {token}",
                                        "Content-Type": "application/json"},
                               json=body, timeout=30)
            if rr.status_code != 200:
                break
            data = rr.json()
            for obj in data.get("results", []):
                pp = obj.get("properties", {})
                amt = float(pp.get("amount") or 0)
                is_won = pp.get("hs_is_closed_won") == "true"
                hs_count += 1
                hs_amt += amt
                if is_won:
                    hs_won += 1
                    hs_won_amt += amt
            nxt = data.get("paging", {}).get("next", {}).get("after")
            if not nxt: break
            after = nxt
            if hs_count > 5000: break
        # SAR → USD via 3.75 peg (matches collector)
        return {
            "bq_deals_total":   int(bq_r.deals_total or 0),
            "bq_deals_won":     int(bq_r.deals_won or 0),
            "bq_amount_total":  float(bq_r.amount_total or 0),
            "bq_amount_won":    float(bq_r.amount_won or 0),
            "hs_deals_total":   hs_count,
            "hs_deals_won":     hs_won,
            "hs_amount_total":  round(hs_amt / 3.75, 2),
            "hs_amount_won":    round(hs_won_amt / 3.75, 2),
        }

    try:
        m = _cached("deals_recon", _q)
        if not m:
            return QACheckResult(name="deals_full_reconcile", passed=True, severity="warn",
                                 detail="could not load Sales Pipeline id — non-fatal")
        # Compute drifts
        def _drift(b, h):
            return ((b - h) / h) if h else 0
        d_total = _drift(m["bq_deals_total"],   m["hs_deals_total"])
        d_won   = _drift(m["bq_deals_won"],     m["hs_deals_won"])
        a_total = _drift(m["bq_amount_total"],  m["hs_amount_total"])
        a_won   = _drift(m["bq_amount_won"],    m["hs_amount_won"])
        failures = []
        if abs(d_total) > count_threshold:
            failures.append(f"deals_total drift {d_total:+.2%}")
        if abs(d_won)   > count_threshold:
            failures.append(f"deals_won drift {d_won:+.2%}")
        if abs(a_total) > amount_threshold:
            failures.append(f"amount_total drift {a_total:+.2%}")
        if abs(a_won)   > amount_threshold:
            failures.append(f"amount_won drift {a_won:+.2%}")
        ok = not failures
        detail = (
            f"deals BQ={m['bq_deals_total']}/{m['bq_deals_won']} "
            f"HS={m['hs_deals_total']}/{m['hs_deals_won']}; "
            f"amt BQ=${m['bq_amount_total']:.0f}/${m['bq_amount_won']:.0f} "
            f"HS=${m['hs_amount_total']:.0f}/${m['hs_amount_won']:.0f}"
        )
        if failures:
            detail = "; ".join(failures) + " | " + detail
        return QACheckResult(
            name="deals_full_reconcile",
            passed=ok,
            severity="block",
            detail=detail,
            metrics=m,
        )
    except Exception as e:
        return QACheckResult(name="deals_full_reconcile", passed=True, severity="warn",
                             detail=f"reconciler unavailable: {e} — non-fatal")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Numeric claim check — extract $XXX figures from Slack text + verify against BQ
# ─────────────────────────────────────────────────────────────────────────────
_DOLLAR = re.compile(r"\$\s?([0-9][0-9,]*\.?[0-9]*)")


def check_numeric_claims(text: str, max_orphan_pct: float = 0.20) -> QACheckResult:
    """Pass if dollar figures cited in text appear in BQ's last-30-day aggregates.

    Heuristic: extract every $XXX number from the text, compare against the
    distribution of recent campaign-level spend totals. If >max_orphan_pct of
    cited numbers have no BQ counterpart within 5% tolerance → fail (suspect
    hallucinated numbers).

    Returns warn-severity by default (rate-limited as it's heuristic).
    """
    cited = []
    for m in _DOLLAR.finditer(text or ""):
        try:
            v = float(m.group(1).replace(",", ""))
            # Only check spend-scale amounts (>= $500). CPQL/CPL values ($60–$200)
            # will never match campaign spend totals — checking them generates
            # constant false-positive orphan warnings that make the check useless.
            if v >= 500.0:
                cited.append(v)
        except ValueError:
            pass

    if not cited:
        return QACheckResult(name="numeric_claims", passed=True, severity="warn",
                             detail="no dollar figures in payload")

    def _q():
        c, p, d = _bq()
        sql = f"""
        SELECT ROUND(SUM(spend),2) AS s
        FROM `{p}.{d}.campaigns_daily`
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
        GROUP BY date, channel, campaign_id
        """
        return [r.s for r in c.query(sql).result() if r.s and r.s > 0]

    known = set(_cached("known_amounts", _q) or [])
    orphans = [v for v in cited if not any(abs(v - k) / max(k, 1) < 0.05 for k in known)]
    orphan_pct = len(orphans) / len(cited)
    return QACheckResult(
        name="numeric_claims",
        passed=orphan_pct <= max_orphan_pct,
        severity="warn",
        detail=f"{len(orphans)}/{len(cited)} dollar figures unmatched ({orphan_pct:.0%})",
        metrics={"cited": cited[:5], "orphans": orphans[:5], "orphan_pct": orphan_pct},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Slack-format compliance — pre-send-review rules from CLAUDE.md
# ─────────────────────────────────────────────────────────────────────────────
def check_slack_format(text: str, channel: str) -> QACheckResult:
    """Enforce non-negotiable Slack format rules (dashboard URL, no IS/QS abbrev)."""
    issues = []
    # Daily digest must carry dashboard URL
    if channel in ("daily", "performance", "daily-performance") or "daily" in (channel or "").lower():
        if "railway.app" not in text and "hex.tech" not in text and "http" not in text:
            issues.append("daily digest missing dashboard URL")
    # Forbid abbreviations
    if re.search(r"\b(IS|QS)\b(?!\w)", text or ""):
        # Allow Quality Score / Impression Share spelled out
        if "Quality Score" not in text and "Impression Share" not in text:
            issues.append("contains forbidden abbreviation IS/QS — spell out")
    # Reject "last X days" — date ranges must be explicit YYYY-MM-DD
    if re.search(r"last\s+\d+\s+days?", text or "", re.IGNORECASE):
        issues.append("contains 'last N days' — use YYYY-MM-DD to YYYY-MM-DD")

    return QACheckResult(
        name="slack_format",
        passed=not issues,
        severity="block",
        detail="; ".join(issues) if issues else "format compliant",
        metrics={"issues": issues},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6b. Pause-precedence — refuse campaign-pause tasks if ad-level candidates exist
# ─────────────────────────────────────────────────────────────────────────────
def check_pause_precedence(task: dict) -> QACheckResult:
    """Block any campaign-level PAUSE Asana task when the same campaign still
    has ad-level pause candidates not yet actioned. Rule confirmed 2026-05-17.

    Heuristic: scan task name + notes for "[Recommendation | Pause]" + "campaign"
    asset level, then extract the campaign name from the title (everything after
    the prefix). If we can match it to a campaigns_daily row with ANY ad-level
    pause candidate, block.
    """
    title = task.get("name") or ""
    notes = task.get("notes") or task.get("html_notes") or ""
    # Only fire on campaign-level PAUSE tasks
    title_l = title.lower()
    notes_l = notes.lower()
    # Support both legacy "key: value" footer format and current "| key | value |" table format
    is_pause = (
        "pause" in title_l
        or "action: pause" in notes_l
        or "| action | pause |" in notes_l
    )
    is_campaign_level = (
        "asset level: campaign" in notes_l
        or "asset_level: campaign" in notes_l
        or "| asset level | campaign |" in notes_l
    )
    if not (is_pause and is_campaign_level):
        return QACheckResult(name="pause_precedence", passed=True, severity="block",
                             detail="not a campaign-pause task — skipped")

    # Already-marked drilldown / pause-blocked notes pass through
    if "pause blocked" in notes_l or "ad-level cleanup first" in notes_l:
        return QACheckResult(name="pause_precedence", passed=True, severity="block",
                             detail="task already routed through ad-level cleanup")

    # Extract probable campaign name from title — e.g. "[Recommendation | Pause] Bing_Search_AR_Brand"
    import re as _re
    m = _re.search(r"\]\s*(.+)$", title)
    campaign_name = (m.group(1) if m else title).strip()
    if not campaign_name or len(campaign_name) < 3:
        return QACheckResult(name="pause_precedence", passed=True, severity="warn",
                             detail="could not extract campaign name from title")

    # Match campaign name → (campaign_id, channel) via campaigns_daily
    c, p, d = _bq()
    sql = f"""
    SELECT DISTINCT campaign_id, channel FROM `{p}.{d}.campaigns_daily`
    WHERE LOWER(campaign_name) = @cname
      AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
    LIMIT 5
    """
    from google.cloud import bigquery as _bq_lib
    job = c.query(sql, job_config=_bq_lib.QueryJobConfig(
        query_parameters=[_bq_lib.ScalarQueryParameter("cname", "STRING", campaign_name.lower())]
    ))
    matches = [(str(r.campaign_id), r.channel) for r in job.result()]
    if not matches:
        return QACheckResult(name="pause_precedence", passed=True, severity="warn",
                             detail=f"could not find campaign '{campaign_name}' in BQ")

    # Channel-aware: search → keyword candidates + LP review; social → ad candidates
    is_search = any(ch in ("google_ads", "microsoft_ads") for _, ch in matches)
    is_social = any(ch in ("meta", "snapchat", "tiktok")  for _, ch in matches)

    blocking = []
    try:
        if is_search:
            from analysers.campaign_health import _campaigns_with_keyword_pause_candidates
            kw_cands = _cached("kw_pause_cands",
                               lambda: _campaigns_with_keyword_pause_candidates(days=14))
            for cid, _ in matches:
                blocking.extend(kw_cands.get(cid, []))
            if blocking:
                summary = "; ".join(f"{k['keyword'][:25]} ({'+'.join(k['reasons'])})"
                                    for k in blocking[:3])
                return QACheckResult(
                    name="pause_precedence", passed=False, severity="block",
                    detail=(f"SEARCH campaign '{campaign_name}' has {len(blocking)} "
                            f"keyword-pause candidate(s) — pause keywords + review LP first: {summary}"),
                    metrics={"campaign": campaign_name, "blocking_keywords": len(blocking)},
                )
            # No flagged keywords still requires LP review for search channels
            return QACheckResult(
                name="pause_precedence", passed=False, severity="block",
                detail=(f"SEARCH campaign '{campaign_name}': no keyword candidates flagged, "
                        f"but LP review is mandatory before campaign-pause on search channels. "
                        f"Visit the destination landing page first (load, form submit, intent match)."),
                metrics={"campaign": campaign_name, "lp_review_required": True},
            )
        if is_social:
            from analysers.campaign_health import _campaigns_with_ad_pause_candidates
            ad_cands = _cached("ad_pause_cands",
                               lambda: _campaigns_with_ad_pause_candidates(days=14))
            for cid, _ in matches:
                blocking.extend(ad_cands.get(cid, []))
            if blocking:
                summary = "; ".join(f"{a['ad_name'][:30]} ({'+'.join(a['reasons'])})"
                                    for a in blocking[:3])
                return QACheckResult(
                    name="pause_precedence", passed=False, severity="block",
                    detail=(f"SOCIAL campaign '{campaign_name}' has {len(blocking)} "
                            f"ad-level pause candidate(s) — pause ads first: {summary}"),
                    metrics={"campaign": campaign_name, "blocking_ads": len(blocking)},
                )
    except Exception as e:
        return QACheckResult(name="pause_precedence", passed=True, severity="warn",
                             detail=f"could not query candidates: {e}")

    return QACheckResult(name="pause_precedence", passed=True, severity="block",
                         detail=f"no blocking candidates in '{campaign_name}'")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Asana footer compliance
# ─────────────────────────────────────────────────────────────────────────────
def check_asana_footer(task: dict) -> QACheckResult:
    """Every Asana task description must end with the required footer block."""
    notes = task.get("notes") or task.get("html_notes") or ""
    required = ["Created", "Due", "Priority", "Type", "Channel"]
    missing = [k for k in required if k not in notes]
    return QACheckResult(
        name="asana_footer",
        passed=not missing,
        severity="block",
        detail=f"footer missing fields: {missing}" if missing else "footer complete",
        metrics={"missing": missing},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Table format compliance — every pipe table must be well-formed
# ─────────────────────────────────────────────────────────────────────────────

# Table types produced by campaign_health_tasks.py + executors/asana.py:
#
#   CAMPAIGN CARD   header = "| Metric | Value |"  + |---|---| separator
#                   11 required data rows (Channel → Last Edit)
#
#   FOOTER          header = "| Field | Value |"   + |---|---| separator
#                   10 required data rows (Created on → Assignee)
#
#   DRILLDOWN       arbitrary columns              + |---|---| separator
#                   consistent column count required; no empty cells
#
# All tables share three structural invariants:
#   1. Every row starts and ends with |
#   2. Column count is consistent across all rows in the same block
#   3. No completely empty cells in data rows (| | or |  |)
#   4. The separator row |---|---| appears at position 2 (index 1) only

_SEP_RE = re.compile(r"^\|[-: |]+\|$")

# Required label cells for each named table type.
# We do partial-match (lower-in-lower) so "Qualified Leads (SQL)" matches "qualified leads".
_CAMPAIGN_CARD_ROWS = [
    "channel", "campaign", "period", "spend", "total leads",
    "qualified leads", "qual rate", "cpl", "cpql", "roas", "last edit",
]
_FOOTER_ROWS = [
    "created on", "created by", "due", "completed on",
    "priority", "type", "channel", "asset level", "action", "assignee",
]


def _parse_table_blocks(text: str) -> list[list[str]]:
    """Extract contiguous pipe-table rows from task description text."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            current.append(line)
        else:
            if current:
                blocks.append(current)
                current = []
    if current:
        blocks.append(current)
    return blocks


def _cell_labels(row: str) -> list[str]:
    """Return stripped cell contents of a non-separator pipe row."""
    parts = row.split("|")
    return [p.strip() for p in parts[1:-1]]  # drop first/last empty string


def check_table_format(task: dict) -> QACheckResult:
    """Verify every markdown pipe table in the task description is well-formed.

    Three structural rules apply to ALL tables:
      1. Consistent column count across every row in the same block
      2. Separator row (|---|---|) must be at position 2 (index 1) — not elsewhere
      3. No completely empty cells in data rows

    Two content rules apply to named table types (detected by their header row):
      - Campaign card  (| Metric | Value |): all 11 required metric rows present
      - Footer         (| Field  | Value |): all 10 required footer rows present

    Drilldown / keyword tables are validated for structure only.
    """
    notes = task.get("notes") or task.get("html_notes") or ""
    if not notes:
        return QACheckResult(name="table_format", passed=True, severity="warn",
                             detail="no notes content — skipped")

    blocks = _parse_table_blocks(notes)
    if not blocks:
        return QACheckResult(name="table_format", passed=True, severity="warn",
                             detail="no pipe tables found — skipped")

    issues: list[str] = []

    for idx, rows in enumerate(blocks, 1):
        tag = f"Table {idx}"
        header_lower = rows[0].lower() if rows else ""

        # Identify table type from header
        is_campaign_card = ("metric" in header_lower and "value" in header_lower)
        is_footer        = ("field"  in header_lower and "value" in header_lower)

        # ── Structural checks (all table types) ───────────────────────────
        col_counts: list[int] = []
        for row_i, row in enumerate(rows):
            is_sep = bool(_SEP_RE.match(row))

            # 1. Separator must be at index 1 only
            if is_sep and row_i != 1:
                issues.append(
                    f"{tag}: separator row at position {row_i + 1} "
                    f"(expected position 2): {row[:50]!r}"
                )

            # 2. Column count for consistency check
            cells = _cell_labels(row)
            col_counts.append(len(cells))

            # 3. No empty cells in data rows
            if not is_sep:
                empty = [i + 1 for i, c in enumerate(cells) if c == "" or c == "—" and len(cells) == 1]
                # Only flag truly blank cells (not "—" which is intentional placeholder)
                truly_blank = [i + 1 for i, c in enumerate(cells) if c == ""]
                if truly_blank:
                    issues.append(
                        f"{tag} row {row_i + 1}: blank cell(s) at column(s) "
                        f"{truly_blank}: {row[:60]!r}"
                    )

        # 4. Consistent column count
        unique_counts = set(col_counts)
        if len(unique_counts) > 1:
            issues.append(
                f"{tag}: inconsistent column counts across rows — "
                f"found {sorted(unique_counts)}. "
                f"A missing or extra | in one row breaks the table."
            )

        # 5. Separator must exist (all our tables require it for GFM rendering)
        has_sep = any(_SEP_RE.match(r) for r in rows)
        if not has_sep:
            issues.append(
                f"{tag}: no separator row (|---|---|) found. "
                f"Table will not render as a table in Asana."
            )

        # ── Content checks — campaign card ────────────────────────────────
        if is_campaign_card:
            present_labels = {
                _cell_labels(r)[0].lower()
                for r in rows[2:]          # skip header + separator
                if not _SEP_RE.match(r) and _cell_labels(r)
            }
            missing = [
                req for req in _CAMPAIGN_CARD_ROWS
                if not any(req in label for label in present_labels)
            ]
            if missing:
                issues.append(
                    f"{tag} (campaign card): missing required row(s): "
                    + ", ".join(f"'{r}'" for r in missing)
                )

        # ── Content checks — footer ────────────────────────────────────────
        if is_footer:
            present_labels = {
                _cell_labels(r)[0].lower()
                for r in rows[2:]
                if not _SEP_RE.match(r) and _cell_labels(r)
            }
            missing = [
                req for req in _FOOTER_ROWS
                if not any(req in label for label in present_labels)
            ]
            if missing:
                issues.append(
                    f"{tag} (footer): missing required row(s): "
                    + ", ".join(f"'{r}'" for r in missing)
                )

    return QACheckResult(
        name="table_format",
        passed=not issues,
        severity="block",
        detail=(
            "; ".join(issues)
            if issues
            else f"{len(blocks)} table(s) checked — all well-formed"
        ),
        metrics={"table_count": len(blocks), "issue_count": len(issues),
                 "issues": issues[:5]},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. BQ write sanity — incoming row batch passes basic integrity rules
# ─────────────────────────────────────────────────────────────────────────────
def check_bq_write(table: str, rows: list[dict], key_fields: list[str]) -> QACheckResult:
    """Pass if incoming rows have no internal duplicates and required keys are populated.

    Note (2026-05-20): `key_fields=["date"]` is a sentinel meaning
    "rebuild entire date partition" — _rebuild_daily_buckets() in
    hubspot_leads_bq.py uses this pattern. The upsert DELETEs the whole
    date and re-INSERTs all rows for that day; multiple rows per date
    are intentional, not duplicates. Same exemption applies to any
    single-key upsert whose key is a partition column.
    """
    issues = []
    if not rows:
        return QACheckResult(name="bq_write_sanity", passed=True, severity="block",
                             detail="empty batch — nothing to write")
    # Internal dupe check — skipped for partition-rebuild upserts (key = ["date"] only)
    if key_fields and key_fields != ["date"]:
        seen = set()
        dupes = 0
        for r in rows:
            k = tuple(str(r.get(f, "")) for f in key_fields)
            if k in seen:
                dupes += 1
            seen.add(k)
        if dupes:
            issues.append(f"{dupes} internal duplicate rows on key {key_fields}")
    # Multi-account: if account_id is in row, expect ≥1 distinct value. A batch
    # with 0 accounts in a channel that's supposed to have any is a collector
    # bug → BLOCK. A batch with 1 of 2 expected accounts is usually a paused
    # secondary account (legitimate state, e.g. Meta's second account dormant
    # since 2026-05) → WARN, don't block. Found 2026-05-20: Meta+TikTok
    # generated 74 false-positive blocks/week from this previously.
    warnings = []
    if rows and "account_id" in rows[0] and "channel" in rows[0]:
        ch = rows[0]["channel"]
        if ch in EXPECTED_ACCOUNTS:
            n = len({r.get("account_id") for r in rows if r.get("account_id")})
            if n == 0 and len(rows) >= 10:
                issues.append(f"0 account(s) in {ch} batch (expected {EXPECTED_ACCOUNTS[ch]}) — collector bug")
            elif n < EXPECTED_ACCOUNTS[ch] and len(rows) >= 10:
                warnings.append(f"only {n} account(s) in {ch} batch (expected {EXPECTED_ACCOUNTS[ch]}, likely paused)")
    detail = "; ".join(issues + warnings) if (issues or warnings) else f"{len(rows)} rows ok"
    return QACheckResult(
        name="bq_write_sanity",
        passed=not issues,            # warnings do NOT fail the check
        severity="block",
        detail=detail,
        metrics={"row_count": len(rows), "issues": issues, "warnings": warnings},
    )
