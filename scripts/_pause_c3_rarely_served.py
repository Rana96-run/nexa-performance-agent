"""Pause all C3 keywords with system_serving_status = RARELY_SERVED."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"

client  = get_client()
ga      = client.get_service("GoogleAdsService")
agc_svc = client.get_service("AdGroupCriterionService")

q = """
SELECT ad_group.id, ad_group_criterion.criterion_id,
       ad_group_criterion.keyword.text
FROM ad_group_criterion
WHERE campaign.id = 23861965426
  AND ad_group_criterion.type = 'KEYWORD'
  AND ad_group_criterion.negative = FALSE
  AND ad_group_criterion.status = 'ENABLED'
  AND ad_group_criterion.system_serving_status = 'RARELY_SERVED'
"""
to_pause = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    to_pause.append({
        "ag_id":   str(r.ad_group.id),
        "crit_id": str(r.ad_group_criterion.criterion_id),
        "text":    r.ad_group_criterion.keyword.text,
    })

print(f"Found {len(to_pause)} keyword(s) to pause:")
for k in to_pause:
    print(f"  - {k['text']}")

if to_pause:
    ops = []
    for k in to_pause:
        op = client.get_type("AdGroupCriterionOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/adGroupCriteria/{k['ag_id']}~{k['crit_id']}"
        op.update.status        = client.enums.AdGroupCriterionStatusEnum.PAUSED
        client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["status"]))
        ops.append(op)
    r = agc_svc.mutate_ad_group_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"\n✅ paused {len(r.results)} keyword(s)")
