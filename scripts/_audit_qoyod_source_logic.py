"""Audit qoyod_source classification gaps. For each known paid signal,
count how many leads are classified 'Other' or 'Direct Traffic' but should
be Microsoft/Meta/etc. based on their click IDs or UTM tags."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

print("=" * 80)
print("Last 30 days — qoyod_source distribution + paid-signal cross-check")
print("=" * 80)

# How many leads per qoyod_source channel
sql = f"""
SELECT qoyod_source, SUM(leads_total) AS leads, COUNT(*) AS row_count
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
GROUP BY 1
ORDER BY leads DESC
"""
print(f"\n{'qoyod_source':25s}  leads  rows")
for r in c.query(sql).result():
    print(f"  {str(r.qoyod_source):23s}  {r.leads or 0:5d}  {r.row_count:5d}")

# How many leads are 'Other' but have a paid signal?
print("\n" + "=" * 80)
print("PROBLEM LEADS: classified as 'Other' but have paid signals")
print("=" * 80)
sql = f"""
SELECT
  COUNT(*) AS total_other_rows,
  COUNTIF(lead_google_ad_click_id IS NOT NULL) AS other_with_gclid,
  COUNTIF(lead_utm_source = 'fb' OR lead_utm_source LIKE '%facebook%') AS other_with_fb_utm,
  COUNTIF(lead_utm_source LIKE '%bing%' OR lead_utm_source = 'bing') AS other_with_bing_utm,
  COUNTIF(lead_utm_source LIKE '%linkedin%') AS other_with_linkedin_utm,
  COUNTIF(lead_utm_source LIKE '%tiktok%') AS other_with_tiktok_utm,
  COUNTIF(lead_utm_source LIKE '%snap%') AS other_with_snap_utm
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND qoyod_source = 'Other'
"""
for r in c.query(sql).result():
    print(f"  Total 'Other' rows: {r.total_other_rows}")
    print(f"    → with gclid (should be Google):       {r.other_with_gclid}")
    print(f"    → with utm_source=fb/facebook:         {r.other_with_fb_utm}")
    print(f"    → with utm_source=bing:                {r.other_with_bing_utm}")
    print(f"    → with utm_source=linkedin:            {r.other_with_linkedin_utm}")
    print(f"    → with utm_source=tiktok:              {r.other_with_tiktok_utm}")
    print(f"    → with utm_source=snap:                {r.other_with_snap_utm}")

# Also: contacts classified as Direct/Organic but with paid click IDs
print("\n" + "=" * 80)
print("PHANTOM PAID: Direct/Organic with click IDs (should be reclassified)")
print("=" * 80)
sql = f"""
SELECT qoyod_source,
  COUNT(*) AS row_count,
  COUNTIF(lead_google_ad_click_id IS NOT NULL) AS with_gclid,
  COUNTIF(lead_campaign_id_sync IS NOT NULL) AS with_sync_id
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND qoyod_source IN ('Direct Traffic','Organic Search','Referrals','Other','Direct In-app Purchase')
  AND (lead_google_ad_click_id IS NOT NULL OR lead_campaign_id_sync IS NOT NULL)
GROUP BY 1
ORDER BY row_count DESC
"""
print(f"{'qoyod_source':25s}  rows  with_gclid  with_sync_id")
for r in c.query(sql).result():
    print(f"  {r.qoyod_source:23s}  {r.row_count:4d}  {r.with_gclid:10d}  {r.with_sync_id:12d}")
