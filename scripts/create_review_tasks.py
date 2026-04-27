"""
Create the Asana tasks from the campaign + keyword review.

Design:
- ONE task per channel summarising pause-zone campaigns (5 channels = 5 tasks max)
- ONE task: pause N wasting keywords (with list in body)
- ONE task: build keywords_daily collector so this is automated
- ONE task: investigate 0-CPQL campaigns (NO_DATA bucket)
- ONE watch task: 2 borderline campaigns

Total: ~8 tasks. Concise, actionable, lands in correct projects + sections.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

from collectors.bq_writer import get_client, PROJECT_ID, DATASET
from collectors.google_ads import get_client as ga_get_client
from collectors.google_ads_bq import _customer_ids
from collectors.currency import normalize_currency, to_usd
from executors.asana import create_task
from config import (
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
)


# ─── 1. Campaign data ────────────────────────────────────────────────────────
client = get_client()
q_camp = f"""
WITH base AS (
  SELECT *
  FROM `{PROJECT_ID}.{DATASET}.paid_channel_campaign_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
    AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
),
agg AS (
  SELECT channel, campaign_name,
         SUM(spend) AS spend,
         SUM(leads) AS leads,
         SUM(qualified) AS qual,
         SUM(open_leads) AS open_l,
         SUM(deals) AS deals
  FROM base GROUP BY channel, campaign_name
)
SELECT *,
       SAFE_DIVIDE(spend, NULLIF(leads, 0)) AS cpl,
       SAFE_DIVIDE(spend, NULLIF(qual, 0))  AS cpql
FROM agg
WHERE spend > 100
ORDER BY spend DESC
"""
campaigns = [dict(r) for r in client.query(q_camp).result()]


def in_pause_zone(c):
    cpl = c.get("cpl"); cpql = c.get("cpql")
    return (cpl is not None and cpl > CPL_WARNING) or (cpql is not None and cpql > CPQL_WARNING)


def in_watch_zone(c):
    cpl = c.get("cpl"); cpql = c.get("cpql")
    in_warning = (cpl is not None and CPL_ACCEPTABLE < cpl <= CPL_WARNING) or \
                 (cpql is not None and CPQL_ACCEPTABLE < cpql <= CPQL_WARNING)
    return in_warning and not in_pause_zone(c)


def has_no_qual(c):
    return (c.get("qual") or 0) == 0 and (c.get("spend") or 0) > 100


pause_by_channel = {}
watch = []
no_qual = []
for c in campaigns:
    if has_no_qual(c) and c.get("qual") == 0:
        no_qual.append(c)
    if in_pause_zone(c):
        pause_by_channel.setdefault(c["channel"], []).append(c)
    elif in_watch_zone(c):
        watch.append(c)


# ─── 2. Keyword data (Google Ads only, live API) ─────────────────────────────
print("[keywords] pulling live from Google Ads…")
ga = ga_get_client().get_service("GoogleAdsService")
end_date = date.today() - timedelta(days=1)
start_date = end_date - timedelta(days=13)
gaql = f"""
  SELECT
    ad_group_criterion.keyword.text,
    ad_group_criterion.keyword.match_type,
    ad_group_criterion.resource_name,
    ad_group.name, campaign.name,
    customer.currency_code,
    metrics.cost_micros, metrics.conversions,
    metrics.clicks, metrics.impressions
  FROM keyword_view
  WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    AND ad_group_criterion.status = 'ENABLED'
"""
keywords = []
for cid in _customer_ids():
    try:
        for r in ga.search(customer_id=cid, query=gaql):
            cur = normalize_currency(getattr(r.customer, "currency_code", None))
            spend_native = r.metrics.cost_micros / 1_000_000
            keywords.append({
                "account": cid,
                "campaign": r.campaign.name,
                "ad_group": r.ad_group.name,
                "keyword":  r.ad_group_criterion.keyword.text,
                "match":    r.ad_group_criterion.keyword.match_type.name,
                "spend":    round(to_usd(spend_native, cur), 2),
                "clicks":   int(r.metrics.clicks),
                "conv":     float(r.metrics.conversions),
                "impressions": int(r.metrics.impressions),
                "resource": r.ad_group_criterion.resource_name,
            })
    except Exception as e:
        print(f"  account {cid}: error {e}")

pause_kw = sorted([k for k in keywords if k["spend"] > 15 and k["conv"] == 0],
                   key=lambda k: -k["spend"])
total_waste = sum(k["spend"] for k in pause_kw)


# ─── 3. Build per-channel pause tasks ────────────────────────────────────────
created = []

CHANNEL_LABEL = {
    "google_ads": "Google Ads", "meta": "Meta", "snapchat": "Snapchat",
    "tiktok": "TikTok", "linkedin": "LinkedIn", "microsoft_ads": "Microsoft",
}

for channel, items in pause_by_channel.items():
    items.sort(key=lambda c: -c["spend"])
    body = (
        f"7-day data ending yesterday. {len(items)} {CHANNEL_LABEL.get(channel, channel)} "
        f"campaigns in pause-zone (CPL > ${CPL_WARNING:.0f} or CPQL > ${CPQL_WARNING:.0f}).\n\n"
    )
    body += "| Campaign | Spend | Leads | Qual | CPL | CPQL | Action |\n"
    body += "|---|---|---|---|---|---|---|\n"
    for c in items:
        cpl  = f"${c['cpl']:.0f}"  if c.get('cpl')  is not None else "—"
        cpql = f"${c['cpql']:.0f}" if c.get('cpql') is not None else "—"
        action = "Pause" if (c.get("qual") == 0 and c.get("spend") > 200) else "Reduce budget / pause underperforming ad sets"
        body += (f"| {c['campaign_name']} | ${c['spend']:.0f} | "
                 f"{int(c['leads'] or 0)} | {int(c['qual'] or 0)} | {cpl} | {cpql} | {action} |\n")
    body += (
        f"\n**What you need to do:** Open the channel optimisation board → "
        f"review each campaign → pause or reduce budget. The agent has NOT "
        f"executed these directly — they all require approval per the Media "
        f"Buyer playbook (campaign-level pauses are not on the direct-execute list)."
    )

    title = f"{CHANNEL_LABEL.get(channel, channel)} — Pause-zone review ({len(items)} campaigns)"
    gid = create_task(
        title=title,
        description=body,
        project_key="optimization",
        task_type="Recommendation",
        channel=channel,
        asset_level="campaign",
        action="pause",
    )
    created.append((title, gid))


# ─── 4. Keyword-pause rollup task (Google Ads only) ──────────────────────────
if pause_kw:
    body = (
        f"Last 14 days · {len(pause_kw)} keywords with $15+ spend and 0 conversions.\n"
        f"**Total waste: ${total_waste:,.0f} USD**\n\n"
        f"Top 30 (by spend):\n\n"
        f"| Spend | Clicks | Match | Keyword | Campaign |\n"
        f"|---|---|---|---|---|\n"
    )
    for k in pause_kw[:30]:
        body += (f"| ${k['spend']:.0f} | {k['clicks']} | {k['match']} | "
                 f"{k['keyword']} | {k['campaign']} |\n")

    body += (
        f"\n**Rule applied:** Pause keyword if zero conversions for 14+ days "
        f"with spend > $15 (per Media Buyer playbook — direct-execute rule).\n\n"
        f"**Action:** These ARE on the direct-execute list (low risk). Once "
        f"the keywords_daily collector lands in BigQuery, the agent will do "
        f"these pauses automatically nightly. For now: review and pause manually "
        f"in Google Ads UI, or approve here so the agent runs `pause_keyword` "
        f"on each via the executor."
    )
    gid = create_task(
        title=f"Google Ads — Pause {len(pause_kw)} wasting keywords (${total_waste:,.0f}/14d)",
        description=body,
        project_key="optimization",
        task_type="Recommendation",
        channel="google_ads",
        asset_level="keyword",
        action="pause",
    )
    created.append((f"keyword pause rollup ({len(pause_kw)} kw)", gid))


# ─── 5. Watch tasks ──────────────────────────────────────────────────────────
if watch:
    body = (
        f"{len(watch)} campaigns drifting toward pause-zone (CPL or CPQL in warning band).\n\n"
        f"| Channel | Campaign | Spend | Leads | Qual | CPL | CPQL |\n"
        f"|---|---|---|---|---|---|---|\n"
    )
    for c in watch:
        cpl  = f"${c['cpl']:.0f}"  if c.get('cpl')  is not None else "—"
        cpql = f"${c['cpql']:.0f}" if c.get('cpql') is not None else "—"
        body += (f"| {c['channel']} | {c['campaign_name']} | ${c['spend']:.0f} | "
                 f"{int(c['leads'])} | {int(c['qual'])} | {cpl} | {cpql} |\n")
    body += "\nMonitor for 2-3 more days. If the trend holds, these move to pause-zone next week."

    gid = create_task(
        title=f"Watch list — {len(watch)} campaigns drifting toward pause-zone",
        description=body,
        project_key="daily_activity",
        task_type="Recommendation",
        channel="general",
        action="watch",
    )
    created.append(("watch list", gid))


# ─── 6. Tracking gap: 0-qualified campaigns ──────────────────────────────────
zero_qual = [c for c in campaigns if c.get("qual") == 0 and (c.get("spend") or 0) > 200]
if zero_qual:
    body = (
        f"{len(zero_qual)} high-spend campaigns produced 0 qualified leads "
        f"in last 7d ending yesterday. This is either a real performance issue "
        f"OR a tracking/attribution gap.\n\n"
        f"| Channel | Campaign | Spend | Total Leads | Qualified |\n"
        f"|---|---|---|---|---|\n"
    )
    for c in zero_qual:
        body += (f"| {c['channel']} | {c['campaign_name']} | ${c['spend']:.0f} | "
                 f"{int(c['leads'])} | {int(c['qual'])} |\n")
    body += (
        "\n**Investigate:**\n"
        "1. Are the leads landing in HubSpot under a different `qoyod_source`?\n"
        "2. Is the campaign UTM tagged correctly (`lead_utm_campaign` matches "
        "campaign name)?\n"
        "3. Do the leads exist but lack a qualification stage update?\n\n"
        "If the data is right — pause these. If tracking is broken, fix the "
        "HubSpot workflow and re-evaluate next week."
    )
    gid = create_task(
        title=f"Investigate {len(zero_qual)} high-spend campaigns with 0 qualified leads",
        description=body,
        project_key="daily_activity",
        task_type="Tracking",
        channel="hubspot",
        asset_level="tracking",
        action="fix",
    )
    created.append(("zero-qual investigation", gid))


# ─── 7. Build keywords_daily collector (foundational) ────────────────────────
gid = create_task(
    title="Build collectors/google_ads_keywords_bq.py — keyword-grain BQ collector",
    description=(
        "Today the agent had to pull 8,764 keyword rows live from Google Ads "
        "API to do waste analysis. That's slow and not historical.\n\n"
        "**Build:** A new collector that writes to `keywords_daily` table:\n"
        "  - Source: `keyword_view` GAQL (already used in `collectors/google_ads.get_keyword_performance`)\n"
        "  - Loop both Google Ads accounts (use `_customer_ids()`)\n"
        "  - Schema: date, account_id, campaign_id, ad_group_id, keyword, "
        "match_type, spend, spend_native, currency, clicks, conversions, impressions, resource_name\n"
        "  - Writes via `bq_writer.upsert_rows(\"keywords_daily\")`\n"
        "  - Add to `reporting_scheduler.COLLECTORS`\n\n"
        "Once landed, the daily cadence runs keyword-pause analysis from BQ "
        "(no live API calls), and direct-execute auto-pauses keywords matching "
        "the rule (zero conv, 14d, >$15 spend).\n\n"
        "Same pattern needed for: ad_group_view (`adgroups_daily`), "
        "ad_view (`ads_daily`), asset_group (PMax). Create separate tasks "
        "after this one ships."
    ),
    project_key="daily_activity",
    task_type="Build",
    channel="google_ads",
    asset_level="keyword",
    action="build",
)
created.append(("build keywords_daily collector", gid))


# ─── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print(f"CREATED {len(created)} ASANA TASKS")
print("=" * 80)
for title, gid in created:
    short = title[:70]
    print(f"  ✓ gid={gid}  {short}")
