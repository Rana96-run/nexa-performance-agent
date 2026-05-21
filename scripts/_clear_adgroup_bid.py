"""Try to clear ad-group cpc_bid_micros — extract clean error."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client
from google.ads.googleads.errors import GoogleAdsException

client = get_client()
ga = client.get_service("GoogleAdsService")
ag_svc = client.get_service("AdGroupService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        for err in e.failure.errors:
            return f"{err.error_code}\n     {err.message}"
    return str(e)[:300]


for acct, cid, label in [("1513020554","23861837000","Acc 1"),
                          ("5753494964","23870151040","Acc 2")]:
    print(f"\n=== {label} ===")
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.resource_name, ad_group.name
        FROM ad_group WHERE campaign.id = {cid}
    """):
        for new_bid in [0, 1]:    # try 0, then 1 micro
            op = client.get_type("AdGroupOperation")
            op.update.resource_name = r.ad_group.resource_name
            op.update.cpc_bid_micros = new_bid
            client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
            try:
                ag_svc.mutate_ad_groups(customer_id=acct, operations=[op])
                print(f"  ✅ {r.ad_group.name}: cpc_bid_micros={new_bid}")
                break
            except Exception as e:
                print(f"  ❌ {r.ad_group.name} @ {new_bid}μ: {_err(e)}")
