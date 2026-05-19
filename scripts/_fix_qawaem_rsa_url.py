"""Fix RSA final_url on FinancialSt_AR — was /accounting/, should be /qawaem/."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT  = "1513020554"
CAMP_ID  = "23861837000"
NEW_URL  = "https://lp.qoyod.com/qawaem/"

c = get_client()
ga = c.get_service("GoogleAdsService")
ad_svc = c.get_service("AdService")

# Find the RSA ad ID
q = f"""
SELECT ad_group_ad.ad.id, ad_group_ad.ad.final_urls
FROM ad_group_ad
WHERE campaign.id = {CAMP_ID} AND ad_group_ad.status = 'ENABLED'
"""
ad_ids = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    ad_ids.append(str(r.ad_group_ad.ad.id))
    print(f"  current url: {list(r.ad_group_ad.ad.final_urls)[0]}")

print(f"  → updating {len(ad_ids)} RSA(s) to: {NEW_URL}")

ops = []
for ad_id in ad_ids:
    op = c.get_type("AdOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/ads/{ad_id}"
    op.update.final_urls.append(NEW_URL)
    c.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["final_urls"]))
    ops.append(op)
r = ad_svc.mutate_ads(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ {res.resource_name}")
