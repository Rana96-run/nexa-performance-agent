"""Find RSA IDs on C1 + HubSpot conversion action IDs."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
c = get_client(); ga = c.get_service("GoogleAdsService")

# C1 RSAs in detail
print("--- C1 (23851270716) RSAs ---")
q = """
SELECT ad_group_ad.resource_name, ad_group_ad.ad.id, ad_group_ad.status,
       ad_group_ad.ad.final_urls
FROM ad_group_ad
WHERE campaign.id = 23851270716
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    print(f"  ad_id={r.ad_group_ad.ad.id}  status={r.ad_group_ad.status.name}")
    print(f"    final_urls: {list(r.ad_group_ad.ad.final_urls)}")
    print(f"    resource  : {r.ad_group_ad.resource_name}")

print("\n--- HubSpot conversion actions ---")
q2 = "SELECT conversion_action.id, conversion_action.name, conversion_action.status, conversion_action.primary_for_goal, conversion_action.resource_name FROM conversion_action WHERE conversion_action.name LIKE '%HubSpot%'"
for r in ga.search(customer_id=ACCOUNT, query=q2):
    a = r.conversion_action
    pri = "★" if a.primary_for_goal else " "
    print(f"  {pri} [{a.status.name}] id={a.id}  {a.name}")
    print(f"      rn: {a.resource_name}")
