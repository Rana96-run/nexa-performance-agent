"""Recreate the 3 disapproved Qawaem sitelinks to force fresh policy review.
The main RSAs passed re-review at the same time so the LP is now considered
working — these sitelinks should pass too on a fresh review.

Steps:
  1. Find current campaign_asset RNs for the 3 disapproved sitelinks
  2. Unlink them from the campaign
  3. Create 3 new sitelink assets (same text, same anchors)
  4. Link them to the campaign
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23861837000"

# 3 disapproved sitelinks — same texts/URLs as originally created
TARGETS = [
    {"text": "موعد الإيداع",   "d1": "ينتهي 30 يونيو 2026",         "d2": "أيام معدودة قبل الغرامة",
     "url": "https://lp.qoyod.com/qawaem/#deadline"},
    {"text": "خطوات الإيداع",  "d1": "من قيود إلى منصة قوائم",     "d2": "في 4 خطوات بسيطة",
     "url": "https://lp.qoyod.com/qawaem/#integration"},
    {"text": "شروط الإعفاء",   "d1": "هل شركتك معفاة من التدقيق؟", "d2": "احسب الآن",
     "url": "https://lp.qoyod.com/qawaem/#exemption"},
]
TARGET_TEXTS = {t["text"] for t in TARGETS}

client    = get_client()
ga        = client.get_service("GoogleAdsService")
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# 1. Find current campaign_asset RNs for disapproved sitelinks
q = f"""
SELECT campaign.id, campaign_asset.resource_name, asset.sitelink_asset.link_text
FROM campaign_asset
WHERE campaign.id = {CAMP_ID} AND campaign_asset.field_type = 'SITELINK'
  AND campaign_asset.status = 'ENABLED'
"""
to_unlink = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    text = r.asset.sitelink_asset.link_text
    if text in TARGET_TEXTS:
        to_unlink.append((text, r.campaign_asset.resource_name))

print(f"1. Found {len(to_unlink)} disapproved sitelinks to unlink + recreate:")
for text, rn in to_unlink:
    print(f"   {text}")

# 2. Unlink them
print("\n2. Unlink disapproved sitelinks")
ops = []
for _, rn in to_unlink:
    op = client.get_type("CampaignAssetOperation")
    op.remove = rn
    ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"   ✅ unlinked {len(r.results)}")

# 3. Create 3 fresh sitelink assets
print("\n3. Create fresh sitelink assets")
new_rns = []
for sl in TARGETS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Sitelink_qawaem_{sl['text'][:18]}_v2"
    op.create.sitelink_asset.link_text     = sl["text"]
    op.create.sitelink_asset.description1  = sl["d1"]
    op.create.sitelink_asset.description2  = sl["d2"]
    op.create.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    new_rns.append(r.results[0].resource_name)
    print(f"   ✅ {sl['text']:<18} → {sl['url']}")

# 4. Link new sitelinks to campaign
print("\n4. Link fresh sitelinks to campaign")
ops = []
for arn in new_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"   ✅ linked {len(r.results)} new sitelinks")

print("\nDone — fresh policy review pending on the 3 recreated sitelinks.")
