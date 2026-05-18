"""Final state of Campaign 3 (Google_Search_AR_ZATCACompetitor_Broad)."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CID     = "23861965426"

client = get_client()
ga = client.get_service("GoogleAdsService")

# Campaign
q1 = f"""
SELECT campaign.id, campaign.name, campaign.status,
       campaign.advertising_channel_type,
       campaign.network_settings.target_content_network,
       campaign.network_settings.target_partner_search_network,
       campaign_budget.amount_micros,
       campaign.bidding_strategy_type
FROM campaign
WHERE campaign.id = {CID}
"""
for r in ga.search(customer_id=ACCOUNT, query=q1):
    c = r.campaign
    print(f"Campaign : {c.name}  [{c.status.name}]")
    print(f"Channel  : {c.advertising_channel_type.name}")
    print(f"Display  : {c.network_settings.target_content_network}")
    print(f"Partners : {c.network_settings.target_partner_search_network}")
    print(f"Budget   : ${r.campaign_budget.amount_micros/1_000_000:.2f}/day")
    print(f"Bidding  : {c.bidding_strategy_type.name}")

# Criteria
print("\nGeo + Language:")
q2 = f"""
SELECT campaign_criterion.type,
       campaign_criterion.location.geo_target_constant,
       campaign_criterion.language.language_constant
FROM campaign_criterion
WHERE campaign.id = {CID}
"""
for r in ga.search(customer_id=ACCOUNT, query=q2):
    t = r.campaign_criterion.type_.name
    if t in ("LOCATION", "LANGUAGE"):
        val = (r.campaign_criterion.location.geo_target_constant
               or r.campaign_criterion.language.language_constant)
        print(f"  {t}: {val}")

# Keywords
q3 = f"""
SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
       ad_group_criterion.negative
FROM ad_group_criterion
WHERE campaign.id = {CID} AND ad_group_criterion.type = 'KEYWORD'
"""
pos, neg = 0, 0
for r in ga.search(customer_id=ACCOUNT, query=q3):
    if r.ad_group_criterion.negative:
        neg += 1
    else:
        pos += 1
print(f"\nKeywords  : {pos} positive, {neg} negative")

# Extensions
print("\nExtensions:")
q5 = f"""
SELECT campaign.id, campaign_asset.field_type
FROM campaign_asset
WHERE campaign.id = {CID}
"""
ext = {}
for r in ga.search(customer_id=ACCOUNT, query=q5):
    ft = r.campaign_asset.field_type.name
    ext[ft] = ext.get(ft, 0) + 1
for ft, n in sorted(ext.items()):
    print(f"  {ft}: {n}")

# Ads
print("\nAds:")
q6 = f"""
SELECT ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.ad.type
FROM ad_group_ad
WHERE campaign.id = {CID}
"""
for r in ga.search(customer_id=ACCOUNT, query=q6):
    print(f"  {r.ad_group_ad.ad.type_.name}  [{r.ad_group_ad.status.name}]  id={r.ad_group_ad.ad.id}")
