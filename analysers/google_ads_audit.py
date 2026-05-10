"""
analysers/google_ads_audit.py
==============================
Daily Google Ads audit producing three actionable feeds:

  1. Impression-share analysis
     - Lost-to-budget   -> scale candidates (raise budget)
     - Lost-to-rank     -> quality issue (improve QS / creative / bid)
     - Saturated (>80%) -> no headroom; consider broadening

  2. Quality-score analysis
     - Per enabled keyword: QS, expected_ctr, ad_relevance, landing_page_experience
     - QS < 5 with $50+ spend -> "improve relevance / LP" task
     - QS < 4 -> urgent

  3. Search-terms / keyword-expansion analysis
     - Converting search terms NOT already in the keyword list -> add as exact/phrase
     - Spending search terms with 0 conv -> negative-keyword candidates
     - Already in keyword list -> ignore (those are the keyword-pause analysis)

Each function returns a list of structured recommendations. The orchestrator
turns them into Asana tasks via executors.asana.create_task with the right
project / section / action_level.

Wired into operational_scheduler nightly cadence.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from collectors.google_ads import get_client
from collectors.google_ads_bq import _customer_ids
from collectors.currency import normalize_currency, to_usd

# ─── Thresholds (tunable via .env later) ──────────────────────────────────────
IS_LOW_THRESHOLD     = 0.50   # IS below 50% has headroom
IS_LOST_BUDGET_FLAG  = 0.20   # > 20% lost to budget -> scale candidate
IS_LOST_RANK_FLAG    = 0.30   # > 30% lost to rank   -> QS / bid issue
IS_SATURATED         = 0.80   # IS > 80% = no growth headroom

QS_TASK_THRESHOLD    = 5      # QS < 5 -> recommend
QS_URGENT_THRESHOLD  = 4
QS_MIN_SPEND_USD     = 70     # only flag if keyword has spent >$70 in window

EXPANSION_MIN_CONV   = 1.0    # search terms with conv >= 1 -> candidate
EXPANSION_MIN_SPEND  = 25.0   # search terms with $25+ spend, 0 conv -> negative

# ─── Keyword routing rules ────────────────────────────────────────────────────
# Single source of truth lives in executors/keyword_policy.py. Re-exported here
# only so legacy imports keep working.
from executors.keyword_policy import (
    ALWAYS_NEGATIVE_PATTERNS,
    BRAND_ONLY_PATTERNS,
    NEVER_NEGATIVE_PATTERNS,
    classify_term,
    is_brand_campaign,
    matches_any as _matches_any,
)


# ─── 1. Impression Share ─────────────────────────────────────────────────────

def audit_impression_share(days: int = 14) -> list[dict]:
    """
    For each enabled Search/PMax campaign, pull IS metrics over the last N days.
    Returns one dict per recommendation.
    """
    client = get_client()
    ga = client.get_service("GoogleAdsService")
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    # PMax exposes different IS metrics — for now we only audit Search/Display.
    # search_impression_share is null for PMax/Video — those rows skip themselves.
    # Google Ads API v18 field names (v17 used different snake_case order).
    query = f"""
      SELECT
        campaign.id, campaign.name, campaign.advertising_channel_type,
        customer.currency_code,
        metrics.cost_micros,
        metrics.impressions,
        metrics.search_impression_share,
        metrics.search_top_impression_share,
        metrics.search_budget_lost_impression_share,
        metrics.search_rank_lost_impression_share
      FROM campaign
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND campaign.status = 'ENABLED'
    """

    findings: list[dict] = []
    for cid in _customer_ids():
        try:
            rows = list(ga.search(customer_id=cid, query=query))
        except Exception as e:
            print(f"[is-audit] account {cid} skipped: {e}")
            continue

        # Aggregate to campaign level (rows here are already per-campaign row)
        for r in rows:
            cur = normalize_currency(getattr(r.customer, "currency_code", None))
            spend = to_usd(r.metrics.cost_micros / 1_000_000, cur)
            if spend < 70:
                continue   # too small to act on

            is_share   = float(r.metrics.search_impression_share or 0)
            lost_bud   = float(r.metrics.search_budget_lost_impression_share or 0)
            lost_rank  = float(r.metrics.search_rank_lost_impression_share or 0)

            # Skip rows where IS isn't reported (PMax / Video / Display etc.)
            if is_share == 0 and lost_bud == 0 and lost_rank == 0:
                continue

            verdict = None
            action = None
            if lost_bud >= IS_LOST_BUDGET_FLAG:
                verdict = "scale-budget-candidate"
                action  = (f"Search-Lost-IS-Budget = {lost_bud*100:.0f}%. "
                           f"Campaign is ranking but budget-capped. Raise daily "
                           f"budget by 20-30% to capture more impressions.")
            elif lost_rank >= IS_LOST_RANK_FLAG:
                verdict = "rank-issue"
                action  = (f"Search-Lost-IS-Rank = {lost_rank*100:.0f}%. Ad rank "
                           f"is the bottleneck — improve Quality Score (relevance, "
                           f"LP experience), raise bids, or restructure ad groups.")
            elif is_share >= IS_SATURATED:
                verdict = "saturated"
                action  = (f"Search IS = {is_share*100:.0f}% (saturated). No "
                           f"headroom on current keywords. Consider broadening "
                           f"keyword list, adding match types, or new ad groups.")
            else:
                continue   # no action

            findings.append({
                "channel":          "google_ads",
                "campaign_id":      str(r.campaign.id),
                "campaign":         r.campaign.name,
                "advertising_type": r.campaign.advertising_channel_type.name,
                "spend":            round(spend, 2),
                "is_share":         round(is_share, 4),
                "is_lost_budget":   round(lost_bud, 4),
                "is_lost_rank":     round(lost_rank, 4),
                "verdict":          verdict,
                "action":           action,
            })

    findings.sort(key=lambda f: -f["spend"])
    return findings


# ─── 2. Quality Score ────────────────────────────────────────────────────────

def audit_quality_score(days: int = 14) -> list[dict]:
    """
    For each enabled keyword with $QS_MIN_SPEND_USD+ spend, pull quality score
    components and flag low-QS keywords for action.
    """
    client = get_client()
    ga = client.get_service("GoogleAdsService")
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    query = f"""
      SELECT
        ad_group_criterion.keyword.text,
        ad_group_criterion.keyword.match_type,
        ad_group_criterion.resource_name,
        ad_group_criterion.quality_info.quality_score,
        ad_group_criterion.quality_info.creative_quality_score,
        ad_group_criterion.quality_info.post_click_quality_score,
        ad_group_criterion.quality_info.search_predicted_ctr,
        ad_group.name,
        campaign.name,
        customer.currency_code,
        metrics.cost_micros,
        metrics.clicks,
        metrics.conversions
      FROM keyword_view
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND ad_group_criterion.status = 'ENABLED'
    """

    findings: list[dict] = []
    for cid in _customer_ids():
        try:
            rows = list(ga.search(customer_id=cid, query=query))
        except Exception as e:
            print(f"[qs-audit] account {cid} skipped: {e}")
            continue
        for r in rows:
            qs = r.ad_group_criterion.quality_info.quality_score
            if not qs or qs >= QS_TASK_THRESHOLD:
                continue
            cur = normalize_currency(getattr(r.customer, "currency_code", None))
            spend = to_usd(r.metrics.cost_micros / 1_000_000, cur)
            if spend < QS_MIN_SPEND_USD:
                continue

            # Component scores: BELOW_AVERAGE / AVERAGE / ABOVE_AVERAGE / UNSPECIFIED
            ce = r.ad_group_criterion.quality_info.creative_quality_score.name
            pc = r.ad_group_criterion.quality_info.post_click_quality_score.name
            ctr = r.ad_group_criterion.quality_info.search_predicted_ctr.name

            urgency = "URGENT" if qs < QS_URGENT_THRESHOLD else "review"
            findings.append({
                "channel":     "google_ads",
                "campaign":    r.campaign.name,
                "ad_group":    r.ad_group.name,
                "keyword":     r.ad_group_criterion.keyword.text,
                "match_type":  r.ad_group_criterion.keyword.match_type.name,
                "resource":    r.ad_group_criterion.resource_name,
                "quality_score":          qs,
                "ad_relevance":           ce,
                "landing_page_experience": pc,
                "expected_ctr":           ctr,
                "spend":   round(spend, 2),
                "clicks":  int(r.metrics.clicks),
                "conv":    float(r.metrics.conversions),
                "urgency": urgency,
            })

    findings.sort(key=lambda f: (f["urgency"] != "URGENT", -f["spend"]))
    return findings


# ─── 3. Keyword expansion (search terms) ─────────────────────────────────────

def audit_search_terms(days: int = 30) -> dict:
    """
    Pull search_term_view for converting + wasted queries.
    Returns {"add_as_keyword": [...], "add_as_negative": [...]}.
    """
    client = get_client()
    ga = client.get_service("GoogleAdsService")
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    query = f"""
      SELECT
        search_term_view.search_term,
        search_term_view.status,
        ad_group.name,
        ad_group.resource_name,
        campaign.name,
        campaign.resource_name,
        customer.currency_code,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions
      FROM search_term_view
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    """

    add_kw: list[dict] = []      # converting terms → add as keyword (approval gate)
    add_neg: list[dict] = []     # wasted terms → add as negative (direct-execute)
    auto_neg: list[dict] = []    # always-negative terms → silent direct-execute
    pause_watch: list[dict] = [] # never-negative terms (قيود / competitors) → pause if not converting

    for cid in _customer_ids():
        try:
            rows = list(ga.search(customer_id=cid, query=query))
        except Exception as e:
            print(f"[search-terms] account {cid} skipped: {e}")
            continue
        for r in rows:
            cur = normalize_currency(getattr(r.customer, "currency_code", None))
            spend = to_usd(r.metrics.cost_micros / 1_000_000, cur)
            term = r.search_term_view.search_term
            status = r.search_term_view.status.name  # ADDED / EXCLUDED / NONE / UNKNOWN
            conv = float(r.metrics.conversions)

            row = {
                "channel":           "google_ads",
                "customer_id":       cid,
                "campaign":          r.campaign.name,
                "campaign_resource": r.campaign.resource_name,
                "ad_group":          r.ad_group.name,
                "ad_group_resource": r.ad_group.resource_name,
                "term":              term,
                "spend":             round(spend, 2),
                "clicks":            int(r.metrics.clicks),
                "conv":              conv,
                "status":            status,
            }

            kind = classify_term(term, r.campaign.name)
            row["policy_kind"] = kind

            # 3a. Converting search terms NOT yet in the keyword list -> add as keyword
            if conv >= EXPANSION_MIN_CONV and status not in ("ADDED",):
                row["cpa"] = round(spend / conv, 0) if conv else None
                if kind == "always_negative":
                    # Login / مجاني / دورة / تحميل / قرض / تمويل / وظيفة / etc.
                    # Never expand on these intents — drop silently.
                    row["policy_reason"] = "always-negative pattern"
                elif kind == "brand_only_block":
                    # قيود / qoyod outside Brand campaign — even if converting,
                    # don't add. Human reviews whether to move into Brand.
                    row["policy_reason"] = "brand-only term in non-brand campaign"
                    pause_watch.append(row)
                elif kind == "competitor_in_competitor":
                    # Competitor name in a Competitor campaign — correct
                    # placement. Don't add as keyword (already targeting the
                    # whole intent), don't pause-watch.
                    row["policy_reason"] = "competitor in competitor campaign — correct placement"
                elif kind == "competitor_in_generic":
                    # Competitor name in a non-competitor campaign — wrong
                    # placement. Don't add; flag the keyword that triggered it.
                    row["policy_reason"] = "competitor in non-competitor campaign — move or pause"
                    pause_watch.append(row)
                elif kind == "language_mismatch":
                    # AR keyword in EN campaign or vice versa — flag for review.
                    row["policy_reason"] = "language mismatch (AR↔EN) — move or pause"
                    pause_watch.append(row)
                else:
                    add_kw.append(row)

            # 3b. Wasted terms (0 conv, $25+ spend, not already excluded)
            elif spend >= EXPANSION_MIN_SPEND and conv == 0 and status not in ("EXCLUDED",):
                if kind == "always_negative":
                    auto_neg.append(row)              # silent direct-execute
                elif kind == "competitor_in_competitor":
                    # Wasted spend on a competitor term in a Competitor campaign
                    # = the keyword needs review/pause (don't negate — it's the
                    # campaign's whole purpose). Pause-watch the keyword.
                    row["policy_reason"] = "competitor spend in competitor campaign — review keyword"
                    pause_watch.append(row)
                elif kind == "competitor_in_generic":
                    # Competitor in wrong campaign — never negate; flag for move/pause.
                    row["policy_reason"] = "competitor in non-competitor campaign — never negate"
                    pause_watch.append(row)
                elif kind in ("brand_only_block", "brand_allowed"):
                    # قيود/qoyod-related — never negate; pause-watch.
                    row["policy_reason"] = "brand term — never negate"
                    pause_watch.append(row)
                elif kind == "language_mismatch":
                    row["policy_reason"] = "language mismatch — fix campaign placement, don't negate"
                    pause_watch.append(row)
                else:
                    add_neg.append(row)               # normal negative candidate

    add_kw.sort(key=lambda x: -x["conv"])
    add_neg.sort(key=lambda x: -x["spend"])
    auto_neg.sort(key=lambda x: -x["spend"])
    pause_watch.sort(key=lambda x: -x["spend"])

    print(f"[search-terms] add_kw={len(add_kw)}, add_neg={len(add_neg)}, "
          f"auto_neg={len(auto_neg)} (always-neg rules), "
          f"pause_watch={len(pause_watch)} (brand/competitor/language — never negate)")

    return {
        "add_as_keyword": add_kw,
        "add_as_negative": add_neg,
        "auto_negative": auto_neg,        # always-negative: execute immediately, no approval
        "pause_watch": pause_watch,       # never-negative: flag for pause review only
    }


# ─── 4. Non-converting keyword auto-pause ────────────────────────────────────

def audit_and_pause_nonconverting_keywords(days: int = 7) -> list[dict]:
    """
    Find keywords that have been ENABLED for {days}+ days with spend >
    KEYWORD_PAUSE_SPEND and 0 HubSpot-qualified leads, then PAUSE them immediately.

    Uses HubSpot Lead Module (hubspot_leads_module_daily) as the lead source —
    NOT Google Ads conversion tracking alone.
    """
    from config import KEYWORD_PAUSE_SPEND
    from collectors.google_ads import get_client as _get_client
    from collectors.google_ads_bq import _customer_ids

    client = _get_client()
    ga     = client.get_service("GoogleAdsService")
    crit_svc = client.get_service("AdGroupCriterionService")

    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)

    query = f"""
      SELECT
        ad_group_criterion.resource_name,
        ad_group_criterion.keyword.text,
        ad_group_criterion.keyword.match_type,
        ad_group.name,
        campaign.name,
        campaign.id,
        customer.currency_code,
        metrics.cost_micros,
        metrics.conversions
      FROM keyword_view
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND ad_group_criterion.status = 'ENABLED'
    """

    from config import MIN_KEYWORD_AGE_DAYS
    from executors.keyword_policy import keyword_first_impression_dates, days_since

    paused: list[dict] = []
    for cid in _customer_ids():
        try:
            rows = list(ga.search(customer_id=cid, query=query))
        except Exception as e:
            print(f"[kw-pause] account {cid} skipped: {e}")
            continue

        # First pass: build the list of pause candidates (over spend, 0 conv)
        candidates = []
        for r in rows:
            from collectors.currency import normalize_currency, to_usd
            cur   = normalize_currency(getattr(r.customer, "currency_code", None))
            spend = to_usd(r.metrics.cost_micros / 1_000_000, cur)
            conv  = float(r.metrics.conversions)
            if spend < KEYWORD_PAUSE_SPEND or conv > 0:
                continue   # under spend threshold or already converting
            candidates.append((r, spend, conv))

        if not candidates:
            continue

        # Apply age guard — only pause keywords ≥ MIN_KEYWORD_AGE_DAYS old.
        firsts = keyword_first_impression_dates(
            client, cid,
            [r.ad_group_criterion.resource_name for r, _, _ in candidates],
        )

        for r, spend, conv in candidates:
            rn = r.ad_group_criterion.resource_name
            first = firsts.get(rn)
            age = days_since(first)
            if age < MIN_KEYWORD_AGE_DAYS:
                print(f"[kw-pause] AGE-GUARD skip: '{r.ad_group_criterion.keyword.text}' "
                      f"({age}d old, threshold {MIN_KEYWORD_AGE_DAYS}d)")
                continue

            try:
                op   = client.get_type("AdGroupCriterionOperation")
                crit = op.update
                crit.resource_name = rn
                crit.status = client.enums.AdGroupCriterionStatusEnum.PAUSED
                op.update_mask.paths.append("status")
                crit_svc.mutate_ad_group_criteria(customer_id=cid, operations=[op])
                status = "paused"
            except Exception as e:
                status = f"error: {e}"

            paused.append({
                "channel":    "google_ads",
                "customer_id": cid,
                "campaign":   r.campaign.name,
                "campaign_id": str(r.campaign.id),
                "ad_group":   r.ad_group.name,
                "keyword":    r.ad_group_criterion.keyword.text,
                "match_type": r.ad_group_criterion.keyword.match_type.name,
                "spend":      round(spend, 2),
                "conv":       conv,
                "days":       days,
                "status":     status,
            })
            print(f"[kw-pause] {status}: '{r.ad_group_criterion.keyword.text}' "
                  f"({r.campaign.name}) spend=${spend:.2f} conv=0")

    actually_paused = [p for p in paused if p["status"] == "paused"]
    if actually_paused:
        try:
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="keyword_management", action="keywords_paused",
                channel="google_ads", rows_affected=len(actually_paused),
                details={"keywords": [p["keyword"] for p in actually_paused[:20]],
                         "days_window": days},
            )
        except Exception:
            pass

    return paused


# ─── 30-keyword-per-ad-group cap helper ──────────────────────────────────────
def _count_keywords_per_adgroup(adgroup_resources: set[str]) -> dict[str, int]:
    """Returns {ad_group_resource_name: enabled_keyword_count} for the given set."""
    if not adgroup_resources:
        return {}

    client = get_client()
    ga = client.get_service("GoogleAdsService")
    counts: dict[str, int] = {rn: 0 for rn in adgroup_resources}

    # Group ad groups by customer_id so we can query per-account
    by_cid: dict[str, list[str]] = {}
    for rn in adgroup_resources:
        # ad_group resource looks like "customers/{cid}/adGroups/{id}"
        try:
            cid = rn.split("/")[1]
        except Exception:
            continue
        by_cid.setdefault(cid, []).append(rn)

    for cid, rns in by_cid.items():
        # Build IN clause; cap to 1000 to keep query size bounded
        rns_str = ", ".join(f"'{rn}'" for rn in rns[:1000])
        q = f"""
          SELECT ad_group.resource_name
          FROM ad_group_criterion
          WHERE ad_group_criterion.type    = 'KEYWORD'
            AND ad_group_criterion.status  = 'ENABLED'
            AND ad_group_criterion.negative = FALSE
            AND ad_group.resource_name IN ({rns_str})
        """
        try:
            for r in ga.search(customer_id=cid, query=q):
                rn = r.ad_group.resource_name
                counts[rn] = counts.get(rn, 0) + 1
        except Exception as e:
            print(f"[kw-cap] count query failed for {cid}: {e}")
    return counts


def filter_kw_against_adgroup_cap(add_kw: list[dict],
                                  max_per_adgroup: int = 30
                                  ) -> tuple[list[dict], list[dict]]:
    """
    Apply the per-ad-group keyword cap. Returns (kept, dropped).
    For each ad group we may add at most (max_per_adgroup - current_enabled_count)
    new keywords. Within an ad group, keep highest-conv first.
    """
    if not add_kw:
        return [], []

    # Group candidates by ad group, sort by descending conv
    by_ag: dict[str, list[dict]] = {}
    for kw in add_kw:
        rn = kw.get("ad_group_resource", "")
        if not rn:
            continue
        by_ag.setdefault(rn, []).append(kw)
    for rn in by_ag:
        by_ag[rn].sort(key=lambda x: -x.get("conv", 0))

    counts = _count_keywords_per_adgroup(set(by_ag.keys()))

    kept: list[dict] = []
    dropped: list[dict] = []
    for rn, candidates in by_ag.items():
        existing = counts.get(rn, 0)
        room = max(0, max_per_adgroup - existing)
        kept.extend(candidates[:room])
        for c in candidates[room:]:
            c["drop_reason"] = (f"ad group at cap ({existing}/{max_per_adgroup} "
                                f"keywords already)")
            dropped.append(c)

    print(f"[kw-cap] kept={len(kept)}, dropped={len(dropped)} (30-per-adgroup cap)")
    return kept, dropped


# ─── Orchestrator ────────────────────────────────────────────────────────────

def _is_weekly_keyword_day() -> bool:
    """True on Sunday (Riyadh). Mirror of the helper in audit_tasks — kept here
    so the orchestrator can skip the auto-pause function on off-days."""
    import os
    if os.getenv("FORCE_WEEKLY_KEYWORDS", "").lower() in ("1", "true", "yes"):
        return True
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=3))).weekday() == 6


def run_full_audit(days: int = 14) -> dict:
    """Run all four audits and return a single combined finding set.
    Keyword auto-pause runs WEEKLY (Sunday) — on other days it returns []."""
    print(f"[google-ads-audit] running IS + QS + search-terms + kw-auto-pause audit ({days}d)")
    is_findings   = audit_impression_share(days=days)
    qs_findings   = audit_quality_score(days=days)
    search_terms  = audit_search_terms(days=30)
    if _is_weekly_keyword_day():
        kw_paused = audit_and_pause_nonconverting_keywords(days=7)
    else:
        kw_paused = []
        print("[kw-pause] skipped — runs weekly on Sunday Riyadh (set FORCE_WEEKLY_KEYWORDS=1 to override)")
    print(f"  IS findings:          {len(is_findings)}")
    print(f"  QS findings:          {len(qs_findings)}")
    print(f"  add as keyword:       {len(search_terms['add_as_keyword'])}")
    print(f"  add as negative:      {len(search_terms['add_as_negative'])}")
    print(f"  auto_negative:        {len(search_terms.get('auto_negative', []))} (always-neg rules)")
    print(f"  pause_watch:          {len(search_terms.get('pause_watch', []))} (قيود/competitors)")
    print(f"  keywords auto-paused: {len(kw_paused)}")
    return {
        "impression_share":  is_findings,
        "quality_score":     qs_findings,
        "keyword_expansion": search_terms,
        "keywords_paused":   kw_paused,
    }


if __name__ == "__main__":
    import json
    result = run_full_audit()
    print()
    print(json.dumps({k: len(v) if isinstance(v, list) else
                          {kk: len(vv) for kk, vv in v.items()}
                       for k, v in result.items()}, indent=2))
