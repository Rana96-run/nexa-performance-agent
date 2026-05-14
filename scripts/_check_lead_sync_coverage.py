"""Check lead module sync ID coverage by channel (last 3 days)."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

sql = f"""
SELECT qoyod_source,
  COUNT(*) AS row_count, SUM(leads_total) AS leads,
  COUNTIF(lead_campaign_id_sync IS NOT NULL) AS rows_with_cid,
  COUNTIF(lead_adgroup_id_sync  IS NOT NULL) AS rows_with_aid,
  COUNTIF(lead_ad_id_sync       IS NOT NULL) AS rows_with_adid
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 3 DAY)
  AND qoyod_source IN ('Google Ads','Microsoft Ads','Meta Ads','Snapchat Ads','Tiktok Ads','LinkedIn Ads')
GROUP BY 1
ORDER BY leads DESC
"""

print(f"{'channel':18s}  leads  cid%  adg%  ad%")
print("-"*55)
for r in c.query(sql).result():
    cov_cid = (r.rows_with_cid / r.row_count * 100) if r.row_count else 0
    cov_aid = (r.rows_with_aid / r.row_count * 100) if r.row_count else 0
    cov_ad  = (r.rows_with_adid / r.row_count * 100) if r.row_count else 0
    print(f"  {r.qoyod_source:16s}  {r.leads or 0:5d}  {cov_cid:4.0f}  {cov_aid:4.0f}  {cov_ad:4.0f}")
