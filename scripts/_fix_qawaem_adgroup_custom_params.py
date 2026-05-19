"""Set ad-group-level custom params on both Qawaem ad groups so UTM
attribution resolves correctly per ad group at click time.

Without this, both AR and EN clicks report adgroupname='FinancialSt_AR'
and adgroupid=198301170444 (the campaign-level static values).
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"

AD_GROUPS = [
    {"id": "198301170444", "name": "FinancialSt_AR", "ad_name": "Google_Search_AR_FinancialStatemnt_AR_V1"},
    {"id": "199721186547", "name": "FinancialSt_EN", "ad_name": "Google_Search_AR_FinancialStatemnt_EN_V1"},
]

client = get_client()
ag_svc = client.get_service("AdGroupService")

ops = []
for ag in AD_GROUPS:
    op = client.get_type("AdGroupOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/adGroups/{ag['id']}"
    for k, v in [
        ("adname",      ag["ad_name"]),
        ("adgroupname", ag["name"]),
        ("adgroupid",   ag["id"]),
    ]:
        p = client.get_type("CustomParameter")
        p.key = k; p.value = v
        op.update.url_custom_parameters.append(p)
    client.copy_from(op.update_mask,
        field_mask_pb2.FieldMask(paths=["url_custom_parameters"]))
    ops.append(op)
    print(f"  → {ag['name']}: adgroupname={ag['name']}, adgroupid={ag['id']}, adname={ag['ad_name']}")

r = ag_svc.mutate_ad_groups(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ {res.resource_name}")
