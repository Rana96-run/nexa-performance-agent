"""Run full HubSpot leads mirror to populate lead_campaign_id_sync for all leads."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.hubspot_leads_bq import sync_full_mirror
n = sync_full_mirror()
print(f"Mirror complete: {n} daily rows updated.")
