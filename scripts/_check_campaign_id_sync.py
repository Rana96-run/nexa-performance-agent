"""Verify lead_campaign_id_sync is populated in BQ after cursor sync."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

sql = f"""
SELECT qoyod_source, lead_campaign_id_sync, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND lead_campaign_id_sync IS NOT NULL
GROUP BY 1, 2
ORDER BY leads DESC
LIMIT 10
"""
rows = list(client.query(sql).result())
if rows:
    print(f"lead_campaign_id_sync populated for {len(rows)} channel×campaign combos in last 7 days:")
    for r in rows:
        print(f"  {str(r.qoyod_source or '?'):12s}  sync_id={str(r.lead_campaign_id_sync):20s}  leads={r.leads}")
else:
    print("No lead_campaign_id_sync data yet — mirror sync may still be running.")

# Also check counts
sql2 = f"""
SELECT COUNT(*) AS total, COUNTIF(lead_campaign_id_sync IS NOT NULL) AS with_sync_id
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
"""
for r in client.query(sql2).result():
    print(f"\nLast 30 days: total={r.total}, with lead_campaign_id_sync={r.with_sync_id} ({r.with_sync_id}/{r.total})")
