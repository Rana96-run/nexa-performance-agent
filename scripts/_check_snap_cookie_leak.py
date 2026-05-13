"""Check qoyod_source distribution for leads attributed by Snapchat campaign ID."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

CID = "c3acb268-fba6-4494-88ae-c7c3187ca178"

sql = f"""
SELECT qoyod_source, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
  AND lead_campaign_id_sync = '{CID}'
GROUP BY 1
ORDER BY leads DESC
"""
print(f"Leads in BQ with lead_campaign_id_sync = {CID} (last 7 days)")
print("-"*60)
total = 0
for r in c.query(sql).result():
    print(f"  {str(r.qoyod_source):25s}  leads={r.leads}")
    total += r.leads
print(f"  {'TOTAL':25s}  leads={total}")
