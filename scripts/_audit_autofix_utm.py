"""Auto-fix: re-apply canonical UTM final_url_suffix to ENABLED Search
campaigns that have it missing. Triggered by daily audit findings.

# KPI-RULE-BYPASS — this is a campaign config fix, not a SQL analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client, STANDARD_UTM_SUFFIX

ACCOUNT = "1513020554"
# Campaigns flagged by audit
TARGETS = ["23851270716", "23861101390", "23861837000"]  # ZATCAPhase2, ZATCAVendorShop, FinancialStatement

client = get_client()
camp_svc = client.get_service("CampaignService")

ops = []
for cid in TARGETS:
    op = client.get_type("CampaignOperation")
    op.update.resource_name    = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.update.final_url_suffix = STANDARD_UTM_SUFFIX
    client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["final_url_suffix"]))
    ops.append(op)

r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ re-applied UTM suffix: {res.resource_name}")
