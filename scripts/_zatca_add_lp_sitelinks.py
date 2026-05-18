"""Create 2 new sitelinks anchored on the e-invoice LP, link to all 3 ZATCA
campaigns:
  1. أسعار الفاتورة         → /einvoice-integration/#pricing
  2. كيف تربط نظامك          → /einvoice-integration/#integration
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

SITELINKS = [
    {
        "text":         "أسعار الفاتورة",
        "description1": "خطط شفافة بدون رسوم خفية",
        "description2": "تجربة 14 يوم مجاناً",
        "url":          "https://lp.qoyod.com/einvoice-integration/#pricing",
    },
    {
        "text":         "كيف تربط نظامك",
        "description1": "خطوات الربط في دقائق",
        "description2": "REST API + XML + PDF/A-3",
        "url":          "https://lp.qoyod.com/einvoice-integration/#integration",
    },
]

# Validate lengths
for sl in SITELINKS:
    assert len(sl["text"]) <= 25, f"text too long: {sl['text']} ({len(sl['text'])})"
    assert len(sl["description1"]) <= 35, f"desc1 too long: {sl['description1']}"
    assert len(sl["description2"]) <= 35, f"desc2 too long: {sl['description2']}"

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# ── 1. Create the 2 sitelink assets ────────────────────────────────────────
print("=" * 70)
print("1. Create sitelink assets")
print("=" * 70)
new_rns = []
for sl in SITELINKS:
    op = client.get_type("AssetOperation")
    co = op.create
    co.name = f"Sitelink_{sl['text']}_einvoice"
    co.sitelink_asset.link_text     = sl["text"]
    co.sitelink_asset.description1  = sl["description1"]
    co.sitelink_asset.description2  = sl["description2"]
    co.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    new_rns.append(rn)
    print(f"  ✅ {sl['text']}  →  {sl['url']}")
    print(f"     rn={rn}")


# ── 2. Link both new sitelinks to all 3 campaigns ──────────────────────────
print()
print("=" * 70)
print("2. Link to all 3 ZATCA campaigns")
print("=" * 70)
ops = []
for cid in CAMPS:
    for arn in new_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} sitelink associations  ({len(new_rns)} sitelinks × {len(CAMPS)} campaigns)")
