"""Path A: bump Acc 1 FinancialStatement ceiling $4 → $10 for fast ramp."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

client = get_client()
csvc = client.get_service("CampaignService")
op = client.get_type("CampaignOperation")
op.update.resource_name = "customers/1513020554/campaigns/23861837000"
op.update.target_spend.cpc_bid_ceiling_micros = 10_000_000
client.copy_from(op.update_mask,
    field_mask_pb2.FieldMask(paths=["target_spend.cpc_bid_ceiling_micros"]))
r = csvc.mutate_campaigns(customer_id="1513020554", operations=[op])
print(f"✅ Acc 1 ceiling → $10.00  ({r.results[0].resource_name})")
