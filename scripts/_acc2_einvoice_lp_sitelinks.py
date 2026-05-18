"""Final Acc2 gap: replicate the 5 /einvoice-integration LP-anchored
sitelinks (the ones used by our 3 ZATCA campaigns on Acc1) and link to
the e-invoice generic campaigns on Acc2."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"

# E-invoice campaigns that should carry the /einvoice-integration LP anchors
TARGET_CAMPS = {
    "16851344135": "Search_E-invoice_AR",
    "22790330091": "PMax_AR_Invoice",
    "23348517003": "ImpressionShare_Search_AR_Invoice",
    "23835392373": "Search_E-invoice_AR_Test",
}

SITELINKS = [
    {"text": "أسعار الفاتورة",
     "d1":   "خطط شفافة بدون رسوم خفية",
     "d2":   "تجربة 14 يوم مجاناً",
     "url":  "https://lp.qoyod.com/einvoice-integration/#pricing"},
    {"text": "اربط منشأتك بـ4 خطوات",
     "d1":   "خطوات الربط في دقائق",
     "d2":   "REST API + XML + PDF/A-3",
     "url":  "https://lp.qoyod.com/einvoice-integration/#integration"},
    {"text": "مميزات الفاتورة",
     "d1":   "متوافق ZATCA + REST API",
     "d2":   "كل ما تحتاجه للامتثال",
     "url":  "https://lp.qoyod.com/einvoice-integration/#features"},
    {"text": "قصص نجاح العملاء",
     "d1":   "تجارب 50,000+ شركة سعودية",
     "d2":   "اقرأها قبل اتخاذ القرار",
     "url":  "https://lp.qoyod.com/einvoice-integration/#testimonials"},
    {"text": "دليل المرحلة الثانية",
     "d1":   "كل ما تحتاجه عن Phase 2",
     "d2":   "متى ينتهي إلزامك؟",
     "url":  "https://lp.qoyod.com/einvoice-integration/#faq"},
]

# Validate
for sl in SITELINKS:
    assert len(sl["text"]) <= 25, sl
    assert len(sl["d1"])    <= 35, sl
    assert len(sl["d2"])    <= 35, sl

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

print(f"1. Create {len(SITELINKS)} einvoice-integration sitelinks on Acc2")
new_rns = []
for sl in SITELINKS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Sitelink_einvoice_{sl['text'][:18]}"
    op.create.sitelink_asset.link_text     = sl["text"]
    op.create.sitelink_asset.description1  = sl["d1"]
    op.create.sitelink_asset.description2  = sl["d2"]
    op.create.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    new_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sl['text']:<22}  {sl['url']}")

print(f"\n2. Link to {len(TARGET_CAMPS)} e-invoice campaigns")
ops = []
for cid, name in TARGET_CAMPS.items():
    for arn in new_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} associations  (5 sitelinks × 4 campaigns)")
