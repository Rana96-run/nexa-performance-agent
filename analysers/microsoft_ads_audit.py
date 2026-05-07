"""
analysers/microsoft_ads_audit.py
=================================
Microsoft Ads parallel of analysers/google_ads_audit.py.

Microsoft Ads has the same auction/quality model as Google (it's the Bing
search engine, plus Yahoo/AOL syndication), so the same audit shape applies:

  1. Impression-share audit  (lost-budget vs lost-rank)
  2. Quality-score audit
  3. Search-terms audit (converting → expand, wasted → negate, brand/competitor
                          rules from executors/keyword_policy.py)
  4. Non-converting keyword auto-pause (Rule A: spend ≥ $80, 0 conv, 7d, age ≥ 10d)

Findings are surfaced via analysers/microsoft_ads_audit_tasks.py which creates
Asana tasks under role='performance_audit', channel='microsoft_ads'.

Microsoft Ads API note: uses the v13 Reporting REST API. Helpers live in
collectors/microsoft_ads_bq.py (we re-import the existing async-report
plumbing rather than duplicate it).
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from collectors.microsoft_ads_bq import (
    _get_access_token,
    _submit_report_generic,
    _poll_report,
    _download_and_parse,
    ACCOUNT_ID,
)
from collectors.currency import normalize_currency, to_usd
from executors.keyword_policy import classify_term


# ─── Thresholds (mirror Google) ──────────────────────────────────────────────
IS_LOW_THRESHOLD     = 0.50
IS_LOST_BUDGET_FLAG  = 0.20
IS_LOST_RANK_FLAG    = 0.30
IS_SATURATED         = 0.80

QS_TASK_THRESHOLD    = 5
QS_URGENT_THRESHOLD  = 4
QS_MIN_SPEND_USD     = 70

EXPANSION_MIN_CONV   = 1.0
EXPANSION_MIN_SPEND  = 25.0


def _run_report(report_type: str, columns: list[str],
                start: date, end: date) -> list[dict]:
    """Submit + poll + download a Microsoft Ads report. Returns list of dict
    rows (csv-parsed). Empty list on error or no data."""
    token = _get_access_token()
    if not token:
        print(f"[ms-audit] no access token — skipping {report_type}")
        return []
    req_id = _submit_report_generic(token, start, end, report_type, columns)
    if not req_id:
        return []
    url = _poll_report(token, req_id)
    if not url:
        return []
    return _download_and_parse(url) or []


# ─── 1. Impression Share ─────────────────────────────────────────────────────

def audit_impression_share(days: int = 14) -> list[dict]:
    """For each enabled Search campaign, pull IS metrics over the last N days.
    Returns one dict per recommendation."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)

    # Column names verified against existing collector (microsoft_ads_bq.py).
    # 'CurrencyCode' (not 'Currency'). No 'CampaignType' or 'AccountName' —
    # they 400 the request.
    columns = [
        "TimePeriod", "AccountId", "CurrencyCode",
        "CampaignId", "CampaignName", "CampaignStatus",
        "Spend", "Impressions",
        "ImpressionSharePercent", "ImpressionLostToBudgetPercent",
        "ImpressionLostToRankAggPercent",
    ]
    rows = _run_report("CampaignPerformanceReportRequest", columns, start, end)

    # Aggregate per campaign across the window
    agg: dict[str, dict] = {}
    for r in rows:
        cid = r.get("CampaignId")
        if not cid:
            continue
        slot = agg.setdefault(cid, {
            "campaign":     r.get("CampaignName", ""),
            "currency":     r.get("CurrencyCode", "USD"),
            "spend_native": 0.0, "impressions": 0,
            "is_share":     [], "is_lost_budget": [], "is_lost_rank": [],
        })
        slot["spend_native"] += float(r.get("Spend", 0) or 0)
        slot["impressions"] += int(r.get("Impressions", 0) or 0)
        for k_in, k_out in (("ImpressionSharePercent",          "is_share"),
                             ("ImpressionLostToBudgetPercent",   "is_lost_budget"),
                             ("ImpressionLostToRankAggPercent",  "is_lost_rank")):
            v = r.get(k_in)
            if v not in (None, "", "—"):
                try:
                    slot[k_out].append(float(v) / 100.0)
                except ValueError:
                    pass

    findings: list[dict] = []
    for cid, slot in agg.items():
        spend = to_usd(slot["spend_native"], normalize_currency(slot["currency"]))
        if spend < QS_MIN_SPEND_USD:
            continue   # too small to act on
        is_share       = sum(slot["is_share"]) / max(len(slot["is_share"]), 1)
        is_lost_budget = sum(slot["is_lost_budget"]) / max(len(slot["is_lost_budget"]), 1)
        is_lost_rank   = sum(slot["is_lost_rank"]) / max(len(slot["is_lost_rank"]), 1)

        verdict = None
        if is_lost_budget > IS_LOST_BUDGET_FLAG:
            verdict = "scale-budget-candidate"
        elif is_lost_rank > IS_LOST_RANK_FLAG:
            verdict = "rank-issue"
        elif is_share > IS_SATURATED:
            verdict = "saturated"
        if verdict:
            findings.append({
                "channel":       "microsoft_ads",
                "campaign_id":   cid,
                "campaign":      slot["campaign"],
                "spend":         round(spend, 2),
                "impressions":   slot["impressions"],
                "is_share":      round(is_share, 4),
                "is_lost_budget": round(is_lost_budget, 4),
                "is_lost_rank":  round(is_lost_rank, 4),
                "verdict":       verdict,
            })
    findings.sort(key=lambda f: -f["spend"])
    return findings


# ─── 2. Quality Score ────────────────────────────────────────────────────────

def audit_quality_score(days: int = 14) -> list[dict]:
    """Per enabled keyword: QS, expected_ctr, ad_relevance, landing_page.
    Returns rows for keywords with QS < threshold + minimum spend."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)

    columns = [
        "TimePeriod", "AccountId", "CurrencyCode",
        "CampaignId", "CampaignName", "AdGroupId", "AdGroupName",
        "Keyword", "KeywordId", "KeywordStatus",
        "QualityScore", "ExpectedCtr", "AdRelevance", "LandingPageExperience",
        "Spend", "Conversions",
    ]
    rows = _run_report("KeywordPerformanceReportRequest", columns, start, end)

    # Aggregate per keyword id
    agg: dict[str, dict] = {}
    for r in rows:
        kid = r.get("KeywordId")
        # MS Ads can return statuses like 'Active' / 'Paused' / 'Submitted' / etc.
        if not kid or (r.get("KeywordStatus") or "").lower() not in ("active", ""):
            continue
        slot = agg.setdefault(kid, {
            "keyword":   r.get("Keyword", ""),
            "campaign":  r.get("CampaignName", ""),
            "ad_group":  r.get("AdGroupName", ""),
            "currency":  r.get("CurrencyCode", "USD"),
            "spend_native": 0.0, "conv": 0.0,
            "qs": [], "ectr": [], "rel": [], "lp": [],
        })
        slot["spend_native"] += float(r.get("Spend", 0) or 0)
        slot["conv"]         += float(r.get("Conversions", 0) or 0)
        for col, key in (("QualityScore", "qs"), ("ExpectedCtr", "ectr"),
                          ("AdRelevance", "rel"), ("LandingPageExperience", "lp")):
            v = r.get(col)
            if v not in (None, "", "—"):
                slot[key].append(v)

    findings: list[dict] = []
    for kid, slot in agg.items():
        spend = to_usd(slot["spend_native"], normalize_currency(slot["currency"]))
        if spend < QS_MIN_SPEND_USD:
            continue
        try:
            qs = int(slot["qs"][-1]) if slot["qs"] else None
        except (ValueError, TypeError):
            qs = None
        if qs is None or qs >= QS_TASK_THRESHOLD:
            continue
        findings.append({
            "channel":      "microsoft_ads",
            "keyword":      slot["keyword"],
            "keyword_id":   kid,
            "campaign":     slot["campaign"],
            "ad_group":     slot["ad_group"],
            "spend":        round(spend, 2),
            "conv":         slot["conv"],
            "quality_score": qs,
            "expected_ctr":  slot["ectr"][-1] if slot["ectr"] else "",
            "ad_relevance":  slot["rel"][-1]  if slot["rel"]  else "",
            "landing_page_experience": slot["lp"][-1] if slot["lp"] else "",
            "urgency":       "URGENT" if qs < QS_URGENT_THRESHOLD else "review",
        })
    findings.sort(key=lambda f: (f["urgency"] != "URGENT", -f["spend"]))
    return findings


# ─── 3. Search Terms ─────────────────────────────────────────────────────────

def audit_search_terms(days: int = 30) -> dict:
    """Pull search-query report for converting + wasted queries.
    Returns 4 buckets like google_ads_audit:
      add_as_keyword | add_as_negative | auto_negative | pause_watch
    """
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)

    # SearchQueryPerformanceReport rejects CurrencyCode (400). MS Ads spend
    # is already in account currency — assume USD if account is USD-billed
    # (we'll convert via account-level lookup if needed).
    columns = [
        "TimePeriod", "AccountId",
        "CampaignId", "CampaignName", "AdGroupId", "AdGroupName",
        "Keyword", "SearchQuery",
        "Spend", "Clicks", "Impressions", "Conversions",
    ]
    rows = _run_report("SearchQueryPerformanceReportRequest", columns, start, end)

    add_kw: list[dict]      = []
    add_neg: list[dict]     = []
    auto_neg: list[dict]    = []
    pause_watch: list[dict] = []

    for r in rows:
        term = (r.get("SearchQuery") or "").strip()
        if not term:
            continue
        spend  = to_usd(float(r.get("Spend", 0) or 0),
                        normalize_currency(r.get("CurrencyCode", "USD")))
        conv   = float(r.get("Conversions", 0) or 0)
        clicks = int(r.get("Clicks", 0) or 0)
        # SearchQueryPerformanceReport doesn't expose QueryStatus — treat as
        # unknown ("") so we don't accidentally filter out legitimate matches.
        status = ""
        camp_name = r.get("CampaignName", "")
        kind   = classify_term(term, camp_name)

        row = {
            "channel":     "microsoft_ads",
            "campaign":    camp_name,
            "ad_group":    r.get("AdGroupName", ""),
            "term":        term,
            "spend":       round(spend, 2),
            "clicks":      clicks,
            "conv":        conv,
            "status":      status,
            "policy_kind": kind,
        }

        # 3a. Converting search terms NOT yet a keyword → expansion candidate
        if conv >= EXPANSION_MIN_CONV and status != "ADDED":
            row["cpa"] = round(spend / conv, 0) if conv else None
            if kind == "always_negative":
                row["policy_reason"] = "always-negative pattern"
            elif kind == "brand_only_block":
                row["policy_reason"] = "brand-only term in non-brand campaign"
                pause_watch.append(row)
            elif kind == "competitor_in_competitor":
                row["policy_reason"] = "competitor in competitor campaign — correct placement"
            elif kind == "competitor_in_generic":
                row["policy_reason"] = "competitor in non-competitor campaign — move or pause"
                pause_watch.append(row)
            elif kind == "language_mismatch":
                row["policy_reason"] = "language mismatch (AR↔EN) — move or pause"
                pause_watch.append(row)
            else:
                add_kw.append(row)

        # 3b. Wasted (≥$25 spend, 0 conv, not already excluded)
        elif spend >= EXPANSION_MIN_SPEND and conv == 0 and status != "EXCLUDED":
            if kind == "always_negative":
                auto_neg.append(row)
            elif kind in ("brand_only_block", "brand_allowed",
                           "competitor_in_competitor", "competitor_in_generic",
                           "language_mismatch"):
                row["policy_reason"] = f"{kind} — never negate; review keyword"
                pause_watch.append(row)
            else:
                add_neg.append(row)

    add_kw.sort(key=lambda x: -x["conv"])
    add_neg.sort(key=lambda x: -x["spend"])
    auto_neg.sort(key=lambda x: -x["spend"])
    pause_watch.sort(key=lambda x: -x["spend"])

    print(f"[ms-search-terms] add_kw={len(add_kw)}, add_neg={len(add_neg)}, "
          f"auto_neg={len(auto_neg)}, pause_watch={len(pause_watch)}")

    return {
        "add_as_keyword":  add_kw,
        "add_as_negative": add_neg,
        "auto_negative":   auto_neg,
        "pause_watch":     pause_watch,
    }


# ─── Orchestrator ────────────────────────────────────────────────────────────

def run_full_audit(days: int = 14) -> dict:
    """Run IS + QS + search-terms audit for Microsoft Ads. Returns a combined
    finding set in the same shape as google_ads_audit.run_full_audit() so
    audit_tasks code can stay symmetric."""
    if not ACCOUNT_ID:
        print("[ms-audit] MS_ACCOUNT_ID not set — skipping Microsoft Ads audit")
        return {"impression_share": [], "quality_score": [],
                "keyword_expansion": {"add_as_keyword": [], "add_as_negative": [],
                                       "auto_negative": [], "pause_watch": []},
                "keywords_paused": []}

    print(f"[ms-audit] running IS + QS + search-terms audit ({days}d)")
    is_findings  = audit_impression_share(days=days)
    qs_findings  = audit_quality_score(days=days)
    search_terms = audit_search_terms(days=30)
    print(f"  IS findings:     {len(is_findings)}")
    print(f"  QS findings:     {len(qs_findings)}")
    print(f"  add as keyword:  {len(search_terms['add_as_keyword'])}")
    print(f"  add as negative: {len(search_terms['add_as_negative'])}")
    print(f"  auto_negative:   {len(search_terms.get('auto_negative', []))}")
    print(f"  pause_watch:     {len(search_terms.get('pause_watch', []))}")
    return {
        "impression_share":  is_findings,
        "quality_score":     qs_findings,
        "keyword_expansion": search_terms,
        "keywords_paused":   [],   # MS Ads keyword auto-pause is a follow-up
    }


if __name__ == "__main__":
    import json
    result = run_full_audit()
    print(json.dumps({k: len(v) if isinstance(v, list) else
                       {k2: len(v2) for k2, v2 in v.items()}
                       for k, v in result.items()}, indent=2))
