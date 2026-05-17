"""Targeted fix — turn OFF Display Network on the 2 campaigns.
The previous fix used protobuf_helpers.field_mask which doesn't detect False
as 'set'. Using explicit FieldMask paths instead."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client
from google.protobuf import field_mask_pb2

ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]

client   = get_client()
camp_svc = client.get_service("CampaignService")

ops = []
for cid in CAMP_IDS:
    op = client.get_type("CampaignOperation")
    upd = op.update
    upd.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
    upd.network_settings.target_google_search        = True
    upd.network_settings.target_search_network        = True
    upd.network_settings.target_content_network        = False
    upd.network_settings.target_partner_search_network = False
    mask = field_mask_pb2.FieldMask(paths=[
        "network_settings.target_google_search",
        "network_settings.target_search_network",
        "network_settings.target_content_network",
        "network_settings.target_partner_search_network",
    ])
    client.copy_from(op.update_mask, mask)
    ops.append(op)

r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"✅ {res.resource_name}")
