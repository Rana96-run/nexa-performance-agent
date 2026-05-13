"""Add lead_campaign_id_sync column to hubspot_leads_module_daily and hubspot_leads_individual."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

client = get_client()
proj = os.environ["BQ_PROJECT_ID"]
ds   = os.environ["BQ_DATASET"]

for table_name in ("hubspot_leads_module_daily", "hubspot_leads_individual"):
    table_id = f"{proj}.{ds}.{table_name}"
    for col in ("lead_campaign_id_sync", "lead_adgroup_id_sync", "lead_ad_id_sync",
                "lead_campaign_id", "lead_ad_group_id", "lead_ad_id"):
        try:
            client.query(
                f"ALTER TABLE `{table_id}` ADD COLUMN IF NOT EXISTS `{col}` STRING"
            ).result()
            print(f"[OK] {table_name}.{col} — added (or already existed)")
        except Exception as e:
            print(f"[ERR] {table_name}.{col}: {e}")
