"""Check sync ID coverage for TODAY only (Riyadh date), per channel."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# TODAY only
sql = f"""
SELECT qoyod_source,
  COUNT(*) AS row_count, SUM(leads_total) AS leads,
  COUNTIF(lead_campaign_id_sync IS NOT NULL) AS rows_with_cid
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date = CURRENT_DATE('Asia/Riyadh')
  AND qoyod_source IN ('Google Ads','Microsoft Ads','Meta Ads','Snapchat Ads','Tiktok Ads')
GROUP BY 1
ORDER BY leads DESC
"""

print("TODAY only (Riyadh date)")
print(f"{'channel':18s}  leads  cid_rows  cov%")
print("-"*50)
for r in c.query(sql).result():
    cov = (r.rows_with_cid / r.row_count * 100) if r.row_count else 0
    print(f"  {r.qoyod_source:16s}  {r.leads or 0:5d}  {r.rows_with_cid:8d}  {cov:4.0f}%")
