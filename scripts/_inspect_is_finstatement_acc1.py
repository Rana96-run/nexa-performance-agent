"""Inspect Google_ImpressionShare_AREN_FinancialStatement (Acc 1, camp
23865358505) — find gaps vs Acc 1 main FinStatement campaign.

Also inspect Phase2 EN ad group on Acc 2 to plan BROAD adds there."""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACC1, IS_CID = "1513020554", "23865358505"
ACC2, P2_CID = "5753494964", "23865711095"

client = get_client()
ga = client.get_service("GoogleAdsService")

# 1. IS campaign on Acc 1 — full state
print("=" * 78)
print(f"Acc 1 IS_FinancialStatement ({IS_CID})")
print("=" * 78)

# Ad groups + per-ag keywords
ag_count = {}
for r in ga.search(customer_id=ACC1, query=f"""
    SELECT ad_group.id, ad_group.name, ad_group.status
    FROM ad_group WHERE campaign.id = {IS_CID}
"""):
    print(f"  AG {r.ad_group.name} ({r.ad_group.id}) status={r.ad_group.status.name}")
    ag_count[r.ad_group.name] = {"id": str(r.ad_group.id), "kw": [], "ads": 0}

# Keywords per ad group
for r in ga.search(customer_id=ACC1, query=f"""
    SELECT ad_group.name,
           ad_group_criterion.keyword.text,
           ad_group_criterion.keyword.match_type,
           ad_group_criterion.status
    FROM ad_group_criterion
    WHERE campaign.id = {IS_CID}
      AND ad_group_criterion.type = 'KEYWORD'
      AND ad_group_criterion.negative = FALSE
      AND ad_group_criterion.status != 'REMOVED'
"""):
    ag_count[r.ad_group.name]["kw"].append(
        f"[{r.ad_group_criterion.keyword.match_type.name}] {r.ad_group_criterion.keyword.text}")

# Ads per ad group
for r in ga.search(customer_id=ACC1, query=f"""
    SELECT ad_group.name, ad_group_ad.ad.id, ad_group_ad.status,
           ad_group_ad.ad.responsive_search_ad.headlines
    FROM ad_group_ad
    WHERE campaign.id = {IS_CID} AND ad_group_ad.status != 'REMOVED'
"""):
    ag_count[r.ad_group.name]["ads"] += 1
    n_hl = len(list(r.ad_group_ad.ad.responsive_search_ad.headlines))
    print(f"    ad {r.ad_group_ad.ad.id} status={r.ad_group_ad.status.name} headlines={n_hl}")

for ag, d in ag_count.items():
    print(f"\n  {ag}: {len(d['kw'])} kw, {d['ads']} ads")
    for k in d["kw"]:
        print(f"    {k}")

# Campaign assets
print(f"\n  --- assets/audiences/negatives on IS campaign ---")
assets = {"SITELINK":0,"CALLOUT":0,"STRUCTURED_SNIPPET":0,"CALL":0,"PROMOTION":0}
for r in ga.search(customer_id=ACC1, query=f"""
    SELECT campaign.id, campaign_asset.field_type, campaign_asset.status
    FROM campaign_asset
    WHERE campaign.id = {IS_CID} AND campaign_asset.status = 'ENABLED'
"""):
    ft = r.campaign_asset.field_type.name
    assets[ft] = assets.get(ft,0) + 1
print(f"  assets: {assets}")

neg = sum(1 for _ in ga.search(customer_id=ACC1, query=f"""
    SELECT campaign_criterion.keyword.text
    FROM campaign_criterion
    WHERE campaign.id = {IS_CID}
      AND campaign_criterion.type='KEYWORD' AND campaign_criterion.negative=TRUE
"""))
aud = sum(1 for _ in ga.search(customer_id=ACC1, query=f"""
    SELECT campaign_criterion.type
    FROM campaign_criterion
    WHERE campaign.id = {IS_CID}
      AND campaign_criterion.type IN ('USER_LIST','USER_INTEREST')
"""))
print(f"  negatives: {neg}  audiences: {aud}")


# 2. Phase 2 Acc 2 EN ad group state
print(f"\n{'=' * 78}")
print(f"Acc 2 ZATCAPhase2 EN ad group state")
print('=' * 78)
for r in ga.search(customer_id=ACC2, query=f"""
    SELECT ad_group.id, ad_group.name FROM ad_group
    WHERE campaign.id = {P2_CID} AND ad_group.name LIKE '%EN%'
"""):
    print(f"  AG {r.ad_group.name} ({r.ad_group.id})")
    for r2 in ga.search(customer_id=ACC2, query=f"""
        SELECT ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type
        FROM ad_group_criterion
        WHERE ad_group.id = {r.ad_group.id}
          AND ad_group_criterion.type='KEYWORD'
          AND ad_group_criterion.negative=FALSE
          AND ad_group_criterion.status != 'REMOVED'
    """):
        print(f"    [{r2.ad_group_criterion.keyword.match_type.name:<6}] "
              f"{r2.ad_group_criterion.keyword.text}")
