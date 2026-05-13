"""Verify all three sync ID columns are populated in BQ after mirror."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

# Coverage counts by channel
print("=== ID coverage by channel (last 30 days) ===")
sql = f"""
SELECT
  qoyod_source,
  COUNT(*) AS total_rows,
  COUNTIF(lead_campaign_id_sync IS NOT NULL) AS has_campaign_id,
  COUNTIF(lead_adgroup_id_sync  IS NOT NULL) AS has_adset_id,
  COUNTIF(lead_ad_id_sync       IS NOT NULL) AS has_ad_id
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
GROUP BY 1
ORDER BY has_campaign_id DESC
"""
for r in client.query(sql).result():
    print(f"  {str(r.qoyod_source or 'unknown'):14s}  rows={r.total_rows:4d}  cam={r.has_campaign_id:3d}  adset={r.has_adset_id:3d}  ad={r.has_ad_id:3d}")

# Sample TikTok and Meta rows with all IDs
print("\n=== Sample TikTok rows with all 3 IDs (last 7 days) ===")
sql2 = f"""
SELECT date, lead_utm_audience, lead_campaign_id_sync, lead_adgroup_id_sync, lead_ad_id_sync, leads_total
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE qoyod_source = 'Tiktok Ads'
  AND lead_adgroup_id_sync IS NOT NULL
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
ORDER BY date DESC, leads_total DESC
LIMIT 5
"""
for r in client.query(sql2).result():
    print(f"  {r.date}  adset_id={str(r.lead_adgroup_id_sync):20s}  ad_id={str(r.lead_ad_id_sync):20s}  leads={r.leads_total}")
