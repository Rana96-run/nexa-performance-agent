"""Dedupe overlapping sitelinks across the 3 ZATCA campaigns.

Pairs (same URL, different wording):
  #pricing      :  خطط الأسعار  vs  أسعار الفاتورة         → keep أسعار الفاتورة
  #integration  :  كيف تربط نظامك  vs  اربط منشأتك بـ4 خطوات  → keep اربط منشأتك بـ4 خطوات

Steps:
  1. Find asset RN for the winners
  2. Link اربط منشأتك بـ4 خطوات to C1 + C2 (currently only on C3)
  3. Unlink losers (خطط الأسعار + كيف تربط نظامك) from all 3 campaigns
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

LOSERS  = {"خطط الأسعار", "كيف تربط نظامك"}
WINNER_TO_BROADCAST = "اربط منشأتك بـ4 خطوات"

client    = get_client()
ga        = client.get_service("GoogleAdsService")
ca_svc    = client.get_service("CampaignAssetService")

# Find: losers' campaign_asset RNs (to remove) + winner's asset RN (to link)
q = f"""
SELECT campaign.id, campaign.name,
       campaign_asset.resource_name,
       campaign_asset.status,
       asset.resource_name,
       asset.sitelink_asset.link_text
FROM campaign_asset
WHERE campaign.id IN ({",".join(CAMPS)})
  AND campaign_asset.field_type = 'SITELINK'
  AND campaign_asset.status = 'ENABLED'
"""
to_remove = []            # list of campaign_asset RNs
winner_asset_rn = None
already_linked = set()    # which campaign IDs already have the winner

for r in ga.search(customer_id=ACCOUNT, query=q):
    text = r.asset.sitelink_asset.link_text
    if text in LOSERS:
        to_remove.append((r.campaign.name, text, r.campaign_asset.resource_name))
    if text == WINNER_TO_BROADCAST:
        winner_asset_rn = r.asset.resource_name
        already_linked.add(str(r.campaign.id))

assert winner_asset_rn, f"Could not find winner asset for '{WINNER_TO_BROADCAST}'"
print(f"Winner asset RN: {winner_asset_rn}")
print(f"Already linked on campaign IDs: {already_linked}")

# 1. Link winner to campaigns that don't have it yet
need_to_link = [cid for cid in CAMPS if cid not in already_linked]
if need_to_link:
    ops = []
    for cid in need_to_link:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = winner_asset_rn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        ops.append(op)
    r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
    print(f"\n✅ linked winner to {len(r.results)} new campaigns: {need_to_link}")
else:
    print("\n(winner already on all campaigns)")

# 2. Remove losers
print(f"\nUnlinking {len(to_remove)} loser association(s):")
for cn, text, _ in to_remove:
    print(f"  {cn}  ::  {text}")

if to_remove:
    ops = []
    for _, _, rn in to_remove:
        op = client.get_type("CampaignAssetOperation")
        op.remove = rn
        ops.append(op)
    r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
    print(f"\n✅ removed {len(r.results)} association(s)")
