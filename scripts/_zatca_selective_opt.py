"""Try multiple approaches to set selective_optimization."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
CIDS = ["23851270716", "23861101390", "23861965426"]
LEAD_RN = f"customers/{ACCOUNT}/conversionActions/7040304673"

c = get_client()
camp_svc = c.get_service("CampaignService")

# Try mask = "selective_optimization" (parent message)
print("Attempt: mask='selective_optimization'")
ops = []
for cid in CIDS:
    op = c.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.update.selective_optimization.conversion_actions.append(LEAD_RN)
    c.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["selective_optimization.conversion_actions"]))
    ops.append(op)
try:
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
except Exception as e:
    msg = str(e)
    # Look for the actual error_code message buried in the exception
    import re
    for m in re.findall(r'message:\s*"([^"]+)"', msg):
        print(f"  ERR MSG: {m}")
    for m in re.findall(r'error_code\s*\{\s*\w+:\s*(\w+)', msg):
        print(f"  ERR CODE: {m}")
