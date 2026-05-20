"""Revert my mistaken campaign-level UTM suffix override.
UTM is set at account level (customer.tracking_url_template +
customer.final_url_suffix). Campaign-level suffix should be EMPTY so
campaigns inherit from account.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
# The 3 campaigns I incorrectly overrode in _audit_autofix_utm.py
TARGETS = ["23851270716", "23861101390", "23861837000"]

client = get_client()
camp_svc = client.get_service("CampaignService")

ops = []
for cid in TARGETS:
    op = client.get_type("CampaignOperation")
    op.update.resource_name    = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.update.final_url_suffix = ""  # clear → inherit from account
    # Also clear my custom params at campaign level — they conflict with
    # any account-level custom params
    client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=[
        "final_url_suffix",
        "url_custom_parameters",
    ]))
    ops.append(op)

r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ reverted (suffix cleared, custom params cleared): {res.resource_name}")

# ZATCACompetitor (23861965426) was never touched by my override but
# does still have the canonical suffix from earlier work. Should I
# also clear it? Yes — for consistency, account-level handles everything.
extra_op = client.get_type("CampaignOperation")
extra_op.update.resource_name    = f"customers/{ACCOUNT}/campaigns/23861965426"
extra_op.update.final_url_suffix = ""
client.copy_from(extra_op.update_mask, field_mask_pb2.FieldMask(paths=[
    "final_url_suffix",
    "url_custom_parameters",
]))
r2 = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=[extra_op])
for res in r2.results:
    print(f"  ✅ also cleared ZATCACompetitor for consistency: {res.resource_name}")

print()
print("All 4 compliance campaigns now inherit UTM from account-level template.")
