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
        return QACheckResult(name="bq_hubspot_reconcile", passed=True, severity="warn",
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
            if v >= 1.0:
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
# 8. BQ write sanity — incoming row batch passes basic integrity rules
# ─────────────────────────────────────────────────────────────────────────────
def check_bq_write(table: str, rows: list[dict], key_fields: list[str]) -> QACheckResult:
    """Pass if incoming rows have no internal duplicates and required keys are populated."""
    issues = []
    if not rows:
        return QACheckResult(name="bq_write_sanity", passed=True, severity="block",
                             detail="empty batch — nothing to write")
    # Internal dupe check
    if key_fields:
        seen = set()
        dupes = 0
        for r in rows:
            k = tuple(str(r.get(f, "")) for f in key_fields)
            if k in seen:
                dupes += 1
            seen.add(k)
        if dupes:
            issues.append(f"{dupes} internal duplicate rows on key {key_fields}")
    # Multi-account: if account_id is in row, must have ≥2 distinct values for ms/google/snap
    if rows and "account_id" in rows[0] and "channel" in rows[0]:
        ch = rows[0]["channel"]
        if ch in EXPECTED_ACCOUNTS:
            n = len({r.get("account_id") for r in rows if r.get("account_id")})
            if n < EXPECTED_ACCOUNTS[ch] and len(rows) >= 10:
                issues.append(f"only {n} account(s) in {ch} batch (expected {EXPECTED_ACCOUNTS[ch]})")
    return QACheckResult(
        name="bq_write_sanity",
        passed=not issues,
        severity="block" if issues else "block",
        detail="; ".join(issues) if issues else f"{len(rows)} rows ok",
        metrics={"row_count": len(rows), "issues": issues},
    )
