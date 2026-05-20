"""Verify (1) current bidding strategy on each Google compliance campaign,
(2) HubSpot truth lead count per campaign — to confirm which need kickstart
vs which already have enough conversion signal to stay on Max Conversions.

# KPI-RULE-BYPASS — this script intentionally pulls bidding_strategy_type
# from campaigns table and joins to hubspot_leads_module_daily for leads.
# Channel-reported leads are NOT used.
"""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client
from google.cloud import bigquery

COMPLIANCE_CAMPS = {
    "23851270716": "ZATCAPhase2",
    "23861101390": "ZATCAVendorShop",
    "23861965426": "ZATCACompetitor",
    "23861837000": "FinancialStatement",
}

# 1. Current bid strategy + budget per campaign
print("=" * 80)
print("CURRENT BIDDING STRATEGY (live state from Google Ads API)")
print("=" * 80)
ga = get_client().get_service("GoogleAdsService")
ids = ",".join(COMPLIANCE_CAMPS.keys())
q = f"""
SELECT campaign.id, campaign.name, campaign.status,
       campaign.bidding_strategy_type,
       campaign.maximize_conversions.target_cpa_micros,
       campaign_budget.amount_micros
FROM campaign
WHERE campaign.id IN ({ids})
"""
campaign_names = {}
for r in ga.search(customer_id="1513020554", query=q):
    tcpa = r.campaign.maximize_conversions.target_cpa_micros or 0
    bud = r.campaign_budget.amount_micros / 1_000_000
    campaign_names[str(r.campaign.id)] = r.campaign.name
    print(f"\n{r.campaign.name} (id={r.campaign.id})")
    print(f"  status   : {r.campaign.status.name}")
    print(f"  bidding  : {r.campaign.bidding_strategy_type.name}")
    print(f"  budget   : ${bud:.2f}/d")
    print(f"  Target CPA (if Max Conv): ${tcpa/1_000_000:.2f}")

# 2. HubSpot truth — leads per campaign (last 14d + last 30d)
print("\n" + "=" * 80)
print("HUBSPOT-TRUTH LEAD COUNT per campaign (NOT channel-reported)")
print("=" * 80)
bq = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")
# Build the OR-ish IN list — the lead_utm_campaign field on HS side matches the campaign name
# in lowercase. Just LIKE-match on the unique substrings.
checks = {
    "ZATCAPhase2":         "zatcaphase2",
    "ZATCAVendorShop":     "zatcavendorshop",
    "ZATCACompetitor":     "zatcacompetitor",
    "FinancialStatement":  "financialstatem",  # match both typo + corrected spellings
}
for label, marker in checks.items():
    q_hs = f"""
    SELECT
      SUM(IF(date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 14 DAY), leads_total, 0)) AS leads_14d,
      SUM(IF(date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 14 DAY), leads_qualified, 0)) AS sqls_14d,
      SUM(leads_total)     AS leads_30d,
      SUM(leads_qualified) AS sqls_30d
    FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
    WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
      AND LOWER(lead_utm_campaign) LIKE '%{marker}%'
    """
    rows = list(bq.query(q_hs).result())
    if rows:
        r = rows[0]
        l14 = r.leads_14d or 0
        s14 = r.sqls_14d  or 0
        l30 = r.leads_30d or 0
        s30 = r.sqls_30d  or 0
        ready = "✅ READY for Max Conv" if l14 >= 5 else f"❌ needs kickstart ({l14} leads in 14d, threshold 5)"
        print(f"\n{label:<20} 14d: {l14} leads / {s14} SQLs  |  30d: {l30} leads / {s30} SQLs  →  {ready}")
