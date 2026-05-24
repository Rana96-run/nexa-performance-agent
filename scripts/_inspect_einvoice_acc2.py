"""Inspect Search_E-invoice_AR (16851344135) on Acc 2 — list ad groups,
their ads' final URLs, and current sitelinks at campaign + ad-group level."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACCT = "5753494964"
CID  = "16851344135"

client = get_client()
ga = client.get_service("GoogleAdsService")

# Ad groups + their ads' final URLs
print("=" * 78)
print("AD GROUPS + DESTINATION URLS")
print("=" * 78)
for r in ga.search(customer_id=ACCT, query=f"""
    SELECT ad_group.id, ad_group.name, ad_group.status
    FROM ad_group
    WHERE campaign.id = {CID} AND ad_group.status = 'ENABLED'
"""):
    ag_id = r.ad_group.id
    print(f"\n  AG {r.ad_group.name} ({ag_id})")
    urls = set()
    for r2 in ga.search(customer_id=ACCT, query=f"""
        SELECT ad_group_ad.ad.final_urls, ad_group_ad.status,
               ad_group_ad.ad.responsive_search_ad.headlines
        FROM ad_group_ad
        WHERE ad_group.id = {ag_id}
          AND ad_group_ad.status = 'ENABLED'
    """):
        for u in r2.ad_group_ad.ad.final_urls:
            urls.add(u)
    for u in sorted(urls):
        print(f"    URL: {u}")
    # Existing ad-group sitelinks
    n_ag_sl = 0
    for r2 in ga.search(customer_id=ACCT, query=f"""
        SELECT campaign.id, ad_group.id, ad_group_asset.asset,
               asset.sitelink_asset.link_text, asset.final_urls
        FROM ad_group_asset
        WHERE ad_group.id = {ag_id}
          AND ad_group_asset.field_type = 'SITELINK'
          AND ad_group_asset.status = 'ENABLED'
    """):
        n_ag_sl += 1
        sl_url = list(r2.asset.final_urls)[0] if r2.asset.final_urls else ""
        print(f"    AG-sitelink: {r2.asset.sitelink_asset.link_text:<26} → {sl_url}")
    if n_ag_sl == 0:
        print(f"    (no ad-group sitelinks)")

# Campaign-level sitelinks
print(f"\n{'=' * 78}")
print(f"CAMPAIGN-LEVEL SITELINKS")
print('=' * 78)
n = 0
for r in ga.search(customer_id=ACCT, query=f"""
    SELECT campaign.id, campaign_asset.resource_name,
           asset.sitelink_asset.link_text, asset.final_urls
    FROM campaign_asset
    WHERE campaign.id = {CID}
      AND campaign_asset.field_type = 'SITELINK'
      AND campaign_asset.status = 'ENABLED'
"""):
    n += 1
    sl_url = list(r.asset.final_urls)[0] if r.asset.final_urls else ""
    print(f"  {r.asset.sitelink_asset.link_text:<28} → {sl_url}")
print(f"\n  total at campaign level: {n}")
