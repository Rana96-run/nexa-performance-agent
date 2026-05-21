"""See why Acc 2 ceiling mutate failed (was already $0 — maybe no-op rejected)."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client
from google.ads.googleads.errors import GoogleAdsException

client = get_client()
csvc = client.get_service("CampaignService")

def _err(e):
    if isinstance(e, GoogleAdsException):
        for err in e.failure.errors:
            return f"{err.error_code} :: {err.message}"
    return str(e)[:300]

op = client.get_type("CampaignOperation")
op.update.resource_name = "customers/5753494964/campaigns/23870151040"
op.update.target_spend.cpc_bid_ceiling_micros = 0
client.copy_from(op.update_mask,
    field_mask_pb2.FieldMask(paths=["target_spend.cpc_bid_ceiling_micros"]))
try:
    csvc.mutate_campaigns(customer_id="5753494964", operations=[op])
    print("✅ set to 0")
except Exception as e:
    print(f"❌ {_err(e)}")
