"""Force-retry the dedup with explicit per-operation error handling."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client
from collections import defaultdict

ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]
WRONG_PHONE = "+966112345678"

client = get_client()
ga = client.get_service("GoogleAdsService")
cas_svc = client.get_service("CampaignAssetService")

# Pull current state RIGHT NOW
q = f"""
SELECT campaign.id, campaign_asset.resource_name, campaign_asset.field_type,
       asset.sitelink_asset.link_text,
       asset.callout_asset.callout_text,
       asset.structured_snippet_asset.header,
       asset.call_asset.phone_number
FROM campaign_asset
WHERE campaign.id IN ({",".join(CAMP_IDS)})
"""
grouped = defaultdict(list)
to_remove_rns = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    cid = str(r.campaign.id)
    ft  = r.campaign_asset.field_type.name
    a   = r.asset
    text = (a.sitelink_asset.link_text or a.callout_asset.callout_text
            or a.structured_snippet_asset.header or a.call_asset.phone_number)
    grouped[(cid, ft, text)].append(r.campaign_asset.resource_name)
    if a.call_asset.phone_number == WRONG_PHONE:
        to_remove_rns.append(r.campaign_asset.resource_name)

# Find duplicates again
for key, rns in grouped.items():
    if len(rns) > 1:
        cid, ft, text = key
        for extra in rns[1:]:
            if extra not in to_remove_rns:
                to_remove_rns.append(extra)

print(f"Found {len(to_remove_rns)} links to remove")
for rn in to_remove_rns[:5]:
    print(f"  {rn}")
print()

# Try removing ONE AT A TIME with explicit error reporting
removed = 0
for rn in to_remove_rns:
    op = client.get_type("CampaignAssetOperation")
    op.remove = rn
    try:
        r = cas_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=[op])
        if r.results:
            removed += 1
        else:
            print(f"  ⚠ no result for {rn}")
    except Exception as e:
        print(f"  ❌ {rn[-40:]}: {e}")

print(f"\nRemoved {removed} / {len(to_remove_rns)} links")
