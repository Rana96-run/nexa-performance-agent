"""Verify Meta campaign IDs in campaigns_daily match lead_campaign_id_sync."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

# Meta campaign IDs from campaigns_daily
print("=== Meta campaigns_daily (last 7 days) ===")
sql = f"""
SELECT DISTINCT channel, campaign_id, campaign_name
FROM `{proj}.{ds}.campaigns_daily`
WHERE channel = 'meta'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
LIMIT 5
"""
for r in client.query(sql).result():
    print(f"  cid={str(r.campaign_id or ''):25s}  name={str(r.campaign_name or '')[:40]}")

# Meta IDs from HubSpot
print("\n=== Meta lead_campaign_id_sync (last 7 days) ===")
sql2 = f"""
SELECT lead_campaign_id_sync, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE qoyod_source = 'Meta Ads'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND lead_campaign_id_sync IS NOT NULL
GROUP BY 1
ORDER BY leads DESC
LIMIT 5
"""
for r in client.query(sql2).result():
    print(f"  sync_id={str(r.lead_campaign_id_sync):25s}  leads={r.leads}")
