"""Switch ZATCAPhase2 back to MAXIMIZE_CONVERSIONS — it has 5 leads / 4 SQLs
in 14d which meets the threshold for Smart Bidding (5+ conversions in 14d).
Same rule the user already applied correctly to ZATCAVendorShop.

# KPI-RULE-BYPASS — campaign config change, not SQL leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT  = "1513020554"
CAMP_ID  = "23851270716"  # ZATCAPhase2

client = get_client()
camp_svc = client.get_service("CampaignService")

op = client.get_type("CampaignOperation")
op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
# Set bidding strategy by populating MaximizeConversions sub-message
op.update.maximize_conversions.target_cpa_micros = 0  # no tCPA yet
client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=[
    "maximize_conversions.target_cpa_micros",
]))

try:
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=[op])
    print(f"  ✅ switched to MAXIMIZE_CONVERSIONS: {r.results[0].resource_name}")
except Exception as e:
    import re
    for m in re.findall(r'message:\s*"([^"]+)"', str(e))[:3]:
        print(f"  ❌ {m}")
