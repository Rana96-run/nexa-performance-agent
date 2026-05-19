"""Pause the 2 disapproved Qawaem RSAs now that the fresh ones are approved."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
DISAPPROVED = [
    "customers/1513020554/adGroupAds/198301170444~809297773356",  # AR old
    "customers/1513020554/adGroupAds/199721186547~809299010076",  # EN old
]

c = get_client()
svc = c.get_service("AdGroupAdService")

ops = []
for rn in DISAPPROVED:
    op = c.get_type("AdGroupAdOperation")
    op.update.resource_name = rn
    op.update.status = c.enums.AdGroupAdStatusEnum.PAUSED
    c.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["status"]))
    ops.append(op)

r = svc.mutate_ad_group_ads(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ paused: {res.resource_name}")
