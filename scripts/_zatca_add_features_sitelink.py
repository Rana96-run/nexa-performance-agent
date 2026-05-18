"""Create the #features sitelink + link to all 3 ZATCA campaigns."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

SITELINK = {
    "text":         "مميزات الفاتورة",
    "description1": "متوافق ZATCA + REST API",
    "description2": "كل ما تحتاجه للامتثال",
    "url":          "https://lp.qoyod.com/einvoice-integration/#features",
}

assert len(SITELINK["text"]) <= 25
assert len(SITELINK["description1"]) <= 35
assert len(SITELINK["description2"]) <= 35

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# Create asset
op = client.get_type("AssetOperation")
co = op.create
co.name = f"Sitelink_{SITELINK['text']}_einvoice"
co.sitelink_asset.link_text     = SITELINK["text"]
co.sitelink_asset.description1  = SITELINK["description1"]
co.sitelink_asset.description2  = SITELINK["description2"]
co.final_urls.append(SITELINK["url"])
r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
arn = r.results[0].resource_name
print(f"✅ asset created: {arn}")

# Link to all 3 campaigns
ops = []
for cid in CAMPS:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"✅ linked to {len(r.results)} campaigns")
