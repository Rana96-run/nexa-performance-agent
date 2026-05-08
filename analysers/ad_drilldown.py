"""
analysers/ad_drilldown.py
==========================
Ad-level and keyword-level drill-down queries for campaigns that have crossed
the CPQL > $130 + CPL > $32 threshold.

Analysis hierarchy enforced here:
  Social (Meta, Snap, TikTok, LinkedIn):
    Ad -> AdSet -> Campaign

  Search (Google Ads, Microsoft Ads):
    Keyword -> Ad Group -> Campaign

Returns Markdown tables ready to embed in Asana task descriptions.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv(override=True)

from collectors.bq_writer import get_client, PROJECT_ID, DATASET
from config import KEYWORD_PAUSE_SPEND, KEYWORD_PAUSE_CPL, KEYWORD_PAUSE_DAYS


# ── Social: Ad-level drill-down ───────────────────────────────────────────────

def get_ad_drilldown_table(channel: str, campaign_name: str, days: int = 14) -> str:
    """
    Query ads_daily for a specific campaign and return a Markdown table
    sorted by CPL desc (worst ads first), grouped by ad set.

    Flags ads for pause: spend > $8 with 0 leads for 7+ days.
    """
    client = get_client()
    since = (date.today() - timedelta(days=days)).isoformat()

    sql = f"""
        SELECT
          adset_name,
          ad_name,
          ad_id,
          status,
          SUM(spend)       AS spend,
          SUM(impressions) AS impressions,
          SUM(leads)       AS leads,
          SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)) AS cpl,
          COUNT(DISTINCT date) AS active_days
        FROM `{PROJECT_ID}.{DATASET}.ads_daily`
        WHERE channel = '{channel}'
          AND LOWER(campaign_name) = LOWER('{campaign_name.replace("'", "''")}')
          AND date >= '{since}'
        GROUP BY adset_name, ad_name, ad_id, status
        HAVING SUM(spend) > 0
        ORDER BY adset_name, cpl DESC NULLS FIRST
    """

    try:
        rows = list(client.query(sql).result())
    except Exception as e:
        return f"_(ads_daily query failed: {e})_\n"

    if not rows:
        return f"_(No ad-level data yet for {campaign_name} — ads_daily is empty for this channel)_\n"

    header = f"\n**{campaign_name} — Ad breakdown ({days}d)**\n"
    header += "| AdSet | Ad | Spend | Leads | CPL | Days Active | Status | Action |\n"
    header += "|---|---|---|---|---|---|---|---|\n"

    table_rows = ""
    for r in rows:
        cpl_s  = f"${r.cpl:.2f}" if r.cpl else "N/A"
        flag   = ""
        # Pause flag: spend > $8, zero leads, running 7+ days
        if (r.spend or 0) > 8 and (r.leads or 0) == 0 and (r.active_days or 0) >= 7:
            flag = "**PAUSE**"
        elif r.cpl and r.cpl > 60:
            flag = "Review"
        else:
            flag = "—"
        table_rows += (f"| {r.adset_name or '?'} | {r.ad_name or r.ad_id or '?'} | "
                       f"${r.spend:.0f} | {r.leads or 0} | {cpl_s} | "
                       f"{r.active_days} | {r.status or '?'} | {flag} |\n")

    # AdSet summary — aggregate across ads to identify bad adsets
    adset_summary: dict[str, dict] = {}
    for r in rows:
        key = r.adset_name or "unknown"
        s   = adset_summary.setdefault(key, {"spend": 0, "leads": 0, "ads": 0, "bad_ads": 0})
        s["spend"] += r.spend or 0
        s["leads"] += r.leads or 0
        s["ads"]   += 1
        if (r.spend or 0) > 8 and (r.leads or 0) == 0:
            s["bad_ads"] += 1

    adset_block = "\n**AdSet summary:**\n"
    adset_block += "| AdSet | Spend | Leads | CPL | Ads | Bad Ads | Action |\n"
    adset_block += "|---|---|---|---|---|---|---|\n"
    for adset, s in adset_summary.items():
        cpl_s  = f"${s['spend']/s['leads']:.2f}" if s["leads"] else "N/A"
        ratio  = s["bad_ads"] / max(s["ads"], 1)
        flag   = "**PAUSE ADSET**" if ratio >= 0.5 else ("Review" if ratio > 0 else "—")
        adset_block += (f"| {adset} | ${s['spend']:.0f} | {s['leads']} | {cpl_s} | "
                        f"{s['ads']} | {s['bad_ads']} | {flag} |\n")

    return header + table_rows + adset_block


# ── Search: Keyword-level drill-down ─────────────────────────────────────────

def get_keyword_drilldown_table(channel: str, campaign_name: str, days: int = 14) -> str:
    """
    Query keyword performance for a Google Ads campaign.

    Falls back to a guidance note if keywords_daily table doesn't exist yet.
    Pause rule: spend > $4, 0 conversions, running ≥ 14 days.
    """
    client = get_client()
    since = (date.today() - timedelta(days=days)).isoformat()

    # Try keywords_daily table first
    sql = f"""
        SELECT
          ad_group_name,
          keyword_text,
          match_type,
          status,
          SUM(cost_micros) / 1000000          AS spend,
          SUM(impressions)                     AS impressions,
          SUM(clicks)                          AS clicks,
          SUM(conversions)                     AS conversions,
          COUNT(DISTINCT segments_date)        AS active_days
        FROM `{PROJECT_ID}.{DATASET}.google_keywords_daily`
        WHERE campaign_name = '{campaign_name.replace("'", "''")}'
          AND segments_date >= '{since}'
        GROUP BY ad_group_name, keyword_text, match_type, status
        HAVING SUM(cost_micros) > 0
        ORDER BY ad_group_name, spend DESC
    """

    try:
        rows = list(client.query(sql).result())
    except Exception:
        # keywords_daily table doesn't exist yet — return guidance note
        return (
            f"\n**{campaign_name} — Keyword drill-down (manual)**\n"
            f"_(keywords_daily table not yet populated — pull directly from Google Ads UI.)_\n\n"
            f"**Manual checklist in Google Ads (last {days} days):**\n"
            f"- **Rule A — Zero conversions:** pause keyword if spend > ${KEYWORD_PAUSE_SPEND:.0f} AND 0 conversions\n"
            f"- **Rule B — Poor CPL:** pause keyword if CPL > ${KEYWORD_PAUSE_CPL:.0f} AND 1+ conversions\n"
            f"- Both rules require the keyword running ≥ {KEYWORD_PAUSE_DAYS} days\n"
            f"- Group remaining keywords by ad group\n"
            f"- If ≥50% of keywords in an ad group are flagged → pause the ad group\n"
            f"- If all ad groups in the campaign are flagged → pause campaign\n"
        )

    if not rows:
        return (
            f"\n_(No keyword data for {campaign_name} in the last {days} days — "
            f"check Google Ads UI directly.)_\n"
        )

    header = f"\n**{campaign_name} — Keyword breakdown ({days}d)**\n"
    header += "| Ad Group | Keyword | Match | Spend | Conv. | CPL | Days | Action |\n"
    header += "|---|---|---|---|---|---|---|---|\n"

    table_rows = ""
    adgroup_summary: dict[str, dict] = {}
    for r in rows:
        spend = r.spend or 0
        conv  = r.conversions or 0
        cpl   = (spend / conv) if conv > 0 else None
        cpl_s = f"${cpl:.2f}" if cpl else "N/A"

        # Rule A: spend > $35, zero conversions, 14+ days → pause
        rule_a = spend > KEYWORD_PAUSE_SPEND and conv == 0 and (r.active_days or 0) >= KEYWORD_PAUSE_DAYS
        # Rule B: CPL > $80 with 1+ conversions, 14+ days → pause (low quality)
        rule_b = cpl is not None and cpl > KEYWORD_PAUSE_CPL and conv >= 1 and (r.active_days or 0) >= KEYWORD_PAUSE_DAYS

        if rule_a:
            flag = f"**PAUSE** (>${KEYWORD_PAUSE_SPEND} spend, 0 conv, {r.active_days}d)"
        elif rule_b:
            flag = f"**PAUSE** (CPL ${cpl:.0f} > ${KEYWORD_PAUSE_CPL:.0f}, {r.active_days}d)"
        elif spend > KEYWORD_PAUSE_SPEND * 0.5 and conv == 0:
            flag = "Watch"
        else:
            flag = "—"
        table_rows += (f"| {r.ad_group_name or '?'} | {r.keyword_text or '?'} | "
                       f"{r.match_type or '?'} | ${spend:.2f} | {conv} | "
                       f"{cpl_s} | {r.active_days} | {flag} |\n")

        key = r.ad_group_name or "unknown"
        s   = adgroup_summary.setdefault(key, {"spend": 0, "conv": 0, "kws": 0, "bad_kws": 0})
        s["spend"] += spend
        s["conv"]  += conv
        s["kws"]   += 1
        if rule_a or rule_b:
            s["bad_kws"] += 1

    adgroup_block = "\n**Ad Group summary:**\n"
    adgroup_block += "| Ad Group | Spend | Conv. | Keywords | Bad Keywords | Action |\n"
    adgroup_block += "|---|---|---|---|---|---|\n"
    for ag, s in adgroup_summary.items():
        ratio = s["bad_kws"] / max(s["kws"], 1)
        flag  = "**PAUSE AD GROUP**" if ratio >= 0.5 else ("Review" if ratio > 0 else "—")
        adgroup_block += (f"| {ag} | ${s['spend']:.0f} | {s['conv']} | "
                          f"{s['kws']} | {s['bad_kws']} | {flag} |\n")

    return header + table_rows + adgroup_block
