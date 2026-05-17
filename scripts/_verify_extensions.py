"""Verify all extensions are linked to both ZATCA Phase 2 campaigns."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client
client = get_client()
ga = client.get_service("GoogleAdsService")
ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]

q = f"""
SELECT campaign.id, campaign.name,
       campaign_asset.field_type,
       asset.type,
       asset.sitelink_asset.link_text,
       asset.callout_asset.callout_text,
       asset.structured_snippet_asset.header,
       asset.call_asset.phone_number
FROM campaign_asset
WHERE campaign.id IN ({",".join(CAMP_IDS)})
"""
by_camp = {}
for r in ga.search(customer_id=ACCOUNT, query=q):
    cid = str(r.campaign.id)
    ft  = r.campaign_asset.field_type.name
    by_camp.setdefault(cid, {}).setdefault(ft, []).append(r)

for cid in CAMP_IDS:
    print(f"\n=== Campaign {cid} ===")
    if cid not in by_camp:
        print("  ❌ no extensions")
        continue
    for ft, items in sorted(by_camp[cid].items()):
        labels = []
        for it in items:
            a = it.asset
            if a.sitelink_asset.link_text:
                labels.append(a.sitelink_asset.link_text)
            elif a.callout_asset.callout_text:
                labels.append(a.callout_asset.callout_text)
            elif a.structured_snippet_asset.header:
                labels.append(a.structured_snippet_asset.header)
            elif a.call_asset.phone_number:
                labels.append(a.call_asset.phone_number)
        print(f"  {ft}: {len(items)}")
        for lbl in labels:
            print(f"    - {lbl}")
