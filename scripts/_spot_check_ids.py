"""Spot-check that all 3 levels expose IDs in their views."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

def sec(t): print(f"\n{'='*70}\n{t}\n{'='*70}")

# Campaign-level
sec("CAMPAIGN level — paid_channel_campaign_daily (Meta, last 7d)")
sql = f"""
SELECT campaign_id, campaign_name,
       ROUND(SUM(spend),0) AS spend, SUM(leads) AS leads
FROM `{proj}.{ds}.paid_channel_campaign_daily`
WHERE channel='meta'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
GROUP BY 1,2 HAVING spend > 0
ORDER BY spend DESC LIMIT 5
"""
for r in c.query(sql).result():
    print(f"  cid={r.campaign_id}  spend=${r.spend}  leads={r.leads}  | {(r.campaign_name or '')[:45]}")

# Adset-level
sec("ADSET level — v_adset_performance (Meta, last 7d)")
sql = f"""
SELECT adset_id, campaign_id, utm_audience AS adset_name,
       ROUND(SUM(spend),0) AS spend, SUM(leads) AS leads
FROM `{proj}.{ds}.v_adset_performance`
WHERE channel='meta'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
GROUP BY 1,2,3 HAVING spend > 0
ORDER BY spend DESC LIMIT 5
"""
for r in c.query(sql).result():
    print(f"  aid={r.adset_id}  cid={r.campaign_id}  spend=${r.spend}  leads={r.leads}")
    print(f"      {(r.adset_name or '')[:55]}")

# Ad-level
sec("AD level — v_ad_performance (Meta, last 7d)")
sql = f"""
SELECT ad_id, adset_id, campaign_id, utm_content AS ad_name,
       ROUND(SUM(spend),0) AS spend, SUM(leads) AS leads
FROM `{proj}.{ds}.v_ad_performance`
WHERE channel='meta'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
GROUP BY 1,2,3,4 HAVING spend > 0
ORDER BY spend DESC LIMIT 5
"""
for r in c.query(sql).result():
    print(f"  ad_id={r.ad_id}  aid={r.adset_id}  cid={r.campaign_id}  spend=${r.spend}  leads={r.leads}")
    print(f"      {(r.ad_name or '')[:60]}")
