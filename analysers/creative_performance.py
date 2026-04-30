"""
analysers/creative_performance.py
===================================
Performance analysis at the sub-campaign level.

SPLIT BY CHANNEL TYPE:
  Google / Bing (Search)  →  group by lead_utm_term     (keywords drive quality)
  Social (Meta, Snapchat, TikTok, LinkedIn, Twitter …)
                          →  group by lead_utm_content   (creatives drive quality)

Data source: hubspot_leads_module_daily only.
  - ads_daily is not used (table is empty — no ad-level collector exists yet).
  - Spend is shown at campaign level from campaigns_daily as context only.
    Per-creative spend is not available until an ad-level collector is built.

Qualification data:
  - leads_total     = total HubSpot leads for that keyword / creative
  - leads_qualified = SQLs
  - disquals        = leads_total - leads_qualified
  - qual_rate       = sqls / leads_total
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, timedelta

from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv(override=True)

# Channels whose identifier is utm_term (keyword)
_SEARCH_CHANNELS = {"google", "bing", "microsoft", "google ads", "microsoft ads"}

# Audience tokens for cross-type breakdown
_AUDIENCE_TOKENS = [
    "interests", "lookalike", "retargeting", "broad", "competitor",
    "impressionshare", "websitetraffic", "reach",
]


def _bq_client():
    project  = os.getenv("BQ_PROJECT_ID")
    dataset  = os.getenv("BQ_DATASET", "qoyod_marketing")
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
    creds    = service_account.Credentials.from_service_account_file(key_path)
    return bigquery.Client(project=project, credentials=creds), project, dataset


def _is_search(channel: str | None) -> bool:
    return (channel or "").lower().strip() in _SEARCH_CHANNELS


# ─── 1. Per-keyword / per-creative performance ────────────────────────────────

def audit_creative_performance(
    campaign_name: str | None = None,
    channel: str | None = None,
    days: int = 30,
    min_leads: int = 3,
) -> dict:
    """
    For Search (Google / Bing)  → groups by lead_utm_term   → "keywords"
    For Social (Meta / Snap …)  → groups by lead_utm_content → "creatives"

    Returns:
    {
      "campaign":    str | None,
      "channel":     str | None,
      "mode":        "keyword" | "creative",
      "identifier":  "utm_term" | "utm_content",
      "date_from":   str,
      "date_to":     str,
      "items": [
          {
            "name":       str,    # keyword text  OR  creative name
            "leads":      int,
            "sqls":       int,
            "disquals":   int,
            "qual_rate":  float,  # 0.0–1.0
            "campaign":   str,    # campaign it belongs to
          }, ...
      ],
      "best":      [top 3 by sqls],
      "worst":     [top 3 by disquals],
      "direction": str,
      "campaign_spend": float | None,   # total spend for the campaign (context only)
    }
    """
    client, project, dataset = _bq_client()
    today   = date.today()
    since   = (today - timedelta(days=days)).isoformat()
    date_to = (today - timedelta(days=1)).isoformat()

    search_mode = _is_search(channel)
    id_field    = "lead_utm_term" if search_mode else "lead_utm_content"
    mode        = "keyword" if search_mode else "creative"

    camp_filter = ""
    if campaign_name:
        safe = campaign_name.replace("'", "''")
        camp_filter = f"AND LOWER(lead_utm_campaign) = LOWER('{safe}')"

    source_filter = ""
    if search_mode:
        source_filter = "AND LOWER(lead_utm_source) IN ('google', 'bing', 'microsoft')"
    elif channel:
        safe_ch = channel.lower().strip()
        source_filter = f"AND LOWER(lead_utm_source) = '{safe_ch}'"

    sql_hs = f"""
        SELECT
          {id_field}            AS identifier,
          lead_utm_campaign     AS campaign,
          SUM(leads_total)      AS leads,
          SUM(leads_qualified)  AS sqls
        FROM `{project}.{dataset}.hubspot_leads_module_daily`
        WHERE date >= '{since}'
          AND date <= '{date_to}'
          AND {id_field} IS NOT NULL
          AND {id_field} != ''
          {camp_filter}
          {source_filter}
        GROUP BY {id_field}, lead_utm_campaign
        HAVING SUM(leads_total) >= {min_leads}
        ORDER BY leads DESC
    """

    try:
        hs_rows = list(client.query(sql_hs).result())
    except Exception as e:
        print(f"[creative-perf] HubSpot query failed: {e}")
        return {}

    if not hs_rows:
        return {
            "campaign":       campaign_name,
            "channel":        channel,
            "mode":           mode,
            "identifier":     id_field,
            "date_from":      since,
            "date_to":        date_to,
            "items":          [],
            "best":           [],
            "worst":          [],
            "direction":      f"No {mode} data found for this campaign/period.",
            "campaign_spend": None,
        }

    items = []
    for r in hs_rows:
        leads    = int(r.leads or 0)
        sqls     = int(r.sqls  or 0)
        disquals = leads - sqls
        qr       = sqls / leads if leads > 0 else 0.0
        items.append({
            "name":      r.identifier or "?",
            "leads":     leads,
            "sqls":      sqls,
            "disquals":  disquals,
            "qual_rate": round(qr, 3),
            "campaign":  r.campaign or "?",
        })

    # Campaign-level spend from campaigns_daily (context only)
    campaign_spend = None
    if campaign_name:
        try:
            safe = campaign_name.replace("'", "''")
            sql_spend = f"""
                SELECT SUM(spend) AS total_spend
                FROM `{project}.{dataset}.campaigns_daily`
                WHERE date >= '{since}' AND date <= '{date_to}'
                  AND LOWER(campaign_name) = LOWER('{safe}')
            """
            spend_rows = list(client.query(sql_spend).result())
            if spend_rows and spend_rows[0].total_spend:
                campaign_spend = round(float(spend_rows[0].total_spend), 2)
        except Exception as e:
            print(f"[creative-perf] spend query failed (non-fatal): {e}")

    best  = sorted([i for i in items if i["sqls"] > 0],
                   key=lambda x: (-x["sqls"], -x["qual_rate"]))[:3]
    worst = sorted([i for i in items if i["disquals"] > 0],
                   key=lambda x: (-x["disquals"], x["qual_rate"]))[:3]

    direction = _build_direction(best, worst, mode)

    return {
        "campaign":       campaign_name,
        "channel":        channel,
        "mode":           mode,
        "identifier":     id_field,
        "date_from":      since,
        "date_to":        date_to,
        "items":          items,
        "best":           best,
        "worst":          worst,
        "direction":      direction,
        "campaign_spend": campaign_spend,
    }


def _build_direction(best: list[dict], worst: list[dict], mode: str) -> str:
    label  = "keyword" if mode == "keyword" else "creative"
    lines  = []

    if best:
        top = best[0]
        lines.append(
            f"Best {label}: '{top['name']}' — "
            f"{top['sqls']} SQLs, {top['qual_rate']*100:.0f}% qual rate. "
            f"Scale spend on campaigns using this {label}."
        )
        if len(best) > 1:
            b2 = best[1]
            lines.append(
                f"Runner-up: '{b2['name']}' — {b2['sqls']} SQLs, "
                f"{b2['qual_rate']*100:.0f}% qual. Test budget alongside best."
            )

    if worst:
        w = worst[0]
        lines.append(
            f"Worst {label}: '{w['name']}' — "
            f"{w['disquals']} disqualified leads, {w['qual_rate']*100:.0f}% qual. "
            f"{'Add as negative keyword.' if mode == 'keyword' else 'Pause or rework this creative.'}"
        )

    return " ".join(lines) if lines else f"No {label} qualification data available."


# ─── 2. Social creatives × audience tier breakdown ───────────────────────────

def audit_creative_by_campaign_type(
    days: int = 30,
    min_leads: int = 3,
) -> dict:
    """
    Social only: show how the same utm_content performs across audience tiers
    (Interests, Lookalike, Retargeting, Broad).

    Google/Bing keywords are handled separately — audience tiers don't apply
    to search campaigns the same way.

    Returns:
    {
      "by_type": {
        "Interests":  [{ name, leads, sqls, disquals, qual_rate, campaign }, ...],
        "Lookalike":  [...],
        ...
      },
      "insights": [str, ...]
    }
    """
    client, project, dataset = _bq_client()
    today   = date.today()
    since   = (today - timedelta(days=days)).isoformat()
    date_to = (today - timedelta(days=1)).isoformat()

    sql = f"""
        SELECT
          lead_utm_content   AS identifier,
          lead_utm_campaign  AS campaign,
          SUM(leads_total)   AS leads,
          SUM(leads_qualified) AS sqls
        FROM `{project}.{dataset}.hubspot_leads_module_daily`
        WHERE date >= '{since}'
          AND date <= '{date_to}'
          AND lead_utm_content IS NOT NULL AND lead_utm_content != ''
          AND LOWER(lead_utm_source) NOT IN ('google', 'bing', 'microsoft')
        GROUP BY lead_utm_content, lead_utm_campaign
        HAVING SUM(leads_total) >= {min_leads}
    """

    try:
        rows = list(client.query(sql).result())
    except Exception as e:
        print(f"[creative-perf] by_type query failed: {e}")
        return {"by_type": {}, "insights": []}

    # Classify by audience token in campaign name
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        camp_lower = (r.campaign or "").lower()
        audience   = "Other"
        for token in _AUDIENCE_TOKENS:
            if token in camp_lower:
                audience = token.title()
                break

        leads    = int(r.leads or 0)
        sqls     = int(r.sqls  or 0)
        disquals = leads - sqls
        qr       = sqls / leads if leads > 0 else 0.0

        by_type.setdefault(audience, []).append({
            "name":      r.identifier or "?",
            "campaign":  r.campaign or "?",
            "leads":     leads,
            "sqls":      sqls,
            "disquals":  disquals,
            "qual_rate": round(qr, 3),
        })

    # Sort each tier by sqls desc
    for tier in by_type:
        by_type[tier].sort(key=lambda x: (-x["sqls"], -x["qual_rate"]))

    # Cross-type insights: same creative, ≥ 20pp qual rate gap across tiers
    creative_tiers: dict[str, dict[str, float]] = defaultdict(dict)
    for audience, items in by_type.items():
        for item in items:
            creative_tiers[item["name"]][audience] = item["qual_rate"]

    insights: list[str] = []
    for name, tier_rates in creative_tiers.items():
        if len(tier_rates) < 2:
            continue
        ranked     = sorted(tier_rates.items(), key=lambda x: -x[1])
        best_t,  best_qr  = ranked[0]
        worst_t, worst_qr = ranked[-1]
        if (best_qr - worst_qr) >= 0.20:
            insights.append(
                f"'{name}' works in *{best_t}* ({best_qr*100:.0f}% qual) "
                f"but underperforms in *{worst_t}* ({worst_qr*100:.0f}% qual). "
                f"Use different creatives per audience tier."
            )

    # Overall tier ranking
    tier_qr: dict[str, float] = {}
    for audience, items in by_type.items():
        vals = [i["qual_rate"] for i in items]
        if vals:
            tier_qr[audience] = sum(vals) / len(vals)

    if len(tier_qr) >= 2:
        best_t  = max(tier_qr, key=tier_qr.get)
        worst_t = min(tier_qr, key=tier_qr.get)
        if best_t != worst_t:
            insights.append(
                f"*{best_t}* audience tier averages {tier_qr[best_t]*100:.0f}% qual rate "
                f"vs *{worst_t}* at {tier_qr[worst_t]*100:.0f}%. "
                f"Prioritise {best_t} when scaling."
            )

    return {"by_type": by_type, "insights": insights}


# ─── 3. Formatting helpers ────────────────────────────────────────────────────

def format_creative_section(result: dict) -> str:
    """
    Asana markdown block.
    Labels as 'Keyword Performance' for Google/Bing, 'Creative Performance' for social.
    """
    if not result or not result.get("items"):
        return ""

    mode     = result.get("mode", "creative")
    label    = "Keyword Performance" if mode == "keyword" else "Creative Performance"
    id_label = "Keyword" if mode == "keyword" else "Ad Name / Creative"
    spend_note = (
        f" · Campaign spend: ${result['campaign_spend']:,.0f}"
        if result.get("campaign_spend") else ""
    )

    lines = [
        f"\n---\n### {label} — {result['date_from']} to {result['date_to']}{spend_note}",
        f"_Source: HubSpot Lead Module · "
        f"{'utm_term (search keywords)' if mode == 'keyword' else 'utm_content (ad creatives)'}_\n",
        f"| {id_label} | Leads | SQLs | Disquals | Qual% |",
        "|---|---|---|---|---|",
    ]

    best_names  = {i["name"] for i in result.get("best",  [])}
    worst_names = {i["name"] for i in result.get("worst", [])}

    for item in result["items"][:25]:
        flag = ""
        if item["name"] in best_names:
            flag = " ✅"
        elif item["name"] in worst_names:
            flag = " ❌"
        lines.append(
            f"| **{item['name']}**{flag} | "
            f"{item['leads']} | {item['sqls']} | {item['disquals']} | "
            f"{item['qual_rate']*100:.0f}% |"
        )

    if result.get("direction"):
        lines.append(f"\n**Direction:** {result['direction']}")

    return "\n".join(lines)


def format_creative_by_type_section(result: dict) -> str:
    """Asana markdown — social creative performance split by audience tier."""
    if not result or not result.get("by_type"):
        return ""

    lines = ["\n---\n### Creative Performance by Audience Tier"]
    for audience, items in sorted(result["by_type"].items()):
        if not items:
            continue
        lines.append(f"\n**{audience}**")
        lines.append("| Ad Name / Creative | Leads | SQLs | Disquals | Qual% |")
        lines.append("|---|---|---|---|---|")
        for c in items[:10]:
            lines.append(
                f"| {c['name']} | {c['leads']} | {c['sqls']} | "
                f"{c['disquals']} | {c['qual_rate']*100:.0f}% |"
            )

    if result.get("insights"):
        lines.append("\n**Insights:**")
        for ins in result["insights"]:
            lines.append(f"- {ins}")

    return "\n".join(lines)


def format_creative_slack(result: dict) -> str:
    """Short Slack block (≤ 8 lines)."""
    if not result or not result.get("items"):
        return ""

    mode   = result.get("mode", "creative")
    label  = ":mag: *Keyword Performance*" if mode == "keyword" else ":art: *Creative Performance*"
    lines  = [f"{label} ({result['date_from']} to {result['date_to']})"]

    for item in result.get("best", [])[:2]:
        lines.append(
            f":large_green_circle: Best: *{item['name']}* — "
            f"{item['sqls']} SQLs · {item['qual_rate']*100:.0f}% qual"
        )
    for item in result.get("worst", [])[:1]:
        lines.append(
            f":large_yellow_circle: Most junk: *{item['name']}* — "
            f"{item['disquals']} disquals · {item['qual_rate']*100:.0f}% qual"
        )

    if result.get("direction"):
        short = result["direction"].split(". ")[0] + "."
        lines.append(f"_Direction: {short}_")

    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else None
    channel  = sys.argv[2] if len(sys.argv) > 2 else None

    result = audit_creative_performance(
        campaign_name=campaign, channel=channel, days=30
    )
    mode = result.get("mode", "creative")
    print(f"\n{'Keyword' if mode == 'keyword' else 'Creative'} analysis")
    print(f"Campaign : {campaign or 'all'}")
    print(f"Channel  : {channel or 'all'}")
    print(f"Period   : {result.get('date_from')} to {result.get('date_to')}")
    print(f"Mode     : {result.get('identifier')}")
    print(f"Items    : {len(result.get('items', []))}")
    print()
    for item in result.get("items", []):
        flag = "✅" if item in result.get("best", []) else (
               "❌" if item in result.get("worst", []) else "  ")
        print(f"  {flag} {item['name']:<55} "
              f"leads={item['leads']:>4}  sqls={item['sqls']:>3}  "
              f"disquals={item['disquals']:>3}  qual={item['qual_rate']*100:.0f}%")
    print(f"\nDirection: {result.get('direction', '—')}")
