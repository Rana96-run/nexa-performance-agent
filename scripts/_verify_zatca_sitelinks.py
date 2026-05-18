"""List all sitelinks currently linked to each ZATCA campaign + their URLs."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

c = get_client(); ga = c.get_service("GoogleAdsService")
q = f"""
SELECT campaign.id, campaign.name,
       asset.sitelink_asset.link_text,
       asset.final_urls,
       campaign_asset.status
FROM campaign_asset
WHERE campaign.id IN ({",".join(CAMPS)})
  AND campaign_asset.field_type = 'SITELINK'
"""
by_camp = {}
for r in ga.search(customer_id=ACCOUNT, query=q):
    cn = r.campaign.name
    text = r.asset.sitelink_asset.link_text
    urls = list(r.asset.final_urls)
    by_camp.setdefault(cn, []).append((text, urls[0] if urls else "", r.campaign_asset.status.name))

for cn, sl in by_camp.items():
    print(f"\n{cn}  ({len(sl)} sitelinks)")
    for text, url, status in sl:
        print(f"  [{status}]  {text}")
        print(f"            {url}")
