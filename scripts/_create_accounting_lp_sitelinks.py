"""Create 4 sitelinks anchored on https://lp.qoyod.com/accounting/.

Use case: generic accounting / lead-gen / brand campaigns that aren't
ZATCA-specific. The accounting LP has clean section anchors:
  #features  → product features
  #how       → 3-step onboarding
  #pricing   → 3-tier pricing
  #faq       → FAQs incl. Phase 2 compatibility
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"   # primary — Account 2 needs separate run

SITELINKS = [
    {
        "text":         "مميزات قيود",
        "description1": "كل اللي تحتاجه في مكان واحد",
        "description2": "فاتورة، مخزون، تقارير، API",
        "url":          "https://lp.qoyod.com/accounting/#features",
    },
    {
        "text":         "كيف تبدأ في 3 خطوات",
        "description1": "تسجيل، إعداد، أول فاتورة",
        "description2": "كل العملية في 14 دقيقة",
        "url":          "https://lp.qoyod.com/accounting/#how",
    },
    {
        "text":         "خطط الأسعار",
        "description1": "من 120 ريال شهرياً",
        "description2": "بدون رسوم خفية",
        "url":          "https://lp.qoyod.com/accounting/#pricing",
    },
    {
        "text":         "الأسئلة الشائعة",
        "description1": "كل ما تريد معرفته عن قيود",
        "description2": "متوافق ZATCA المرحلة 2",
        "url":          "https://lp.qoyod.com/accounting/#faq",
    },
]

# Validate lengths
for sl in SITELINKS:
    assert len(sl["text"]) <= 25, f"text {len(sl['text'])}: {sl['text']}"
    assert len(sl["description1"]) <= 35, f"d1 {len(sl['description1'])}: {sl['description1']}"
    assert len(sl["description2"]) <= 35, f"d2 {len(sl['description2'])}: {sl['description2']}"

client    = get_client()
asset_svc = client.get_service("AssetService")

print("Create 4 sitelinks anchored on /accounting:")
new_rns = []
for sl in SITELINKS:
    op = client.get_type("AssetOperation")
    co = op.create
    co.name = f"Sitelink_accounting_{sl['text'][:20]}"
    co.sitelink_asset.link_text     = sl["text"]
    co.sitelink_asset.description1  = sl["description1"]
    co.sitelink_asset.description2  = sl["description2"]
    co.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    new_rns.append((sl["text"], sl["url"], rn))
    print(f"  ✅ {sl['text']:<22}  {sl['url']}")
    print(f"      → {rn}")

print()
print("All 4 assets created (not yet linked to any campaign).")
print()
print("RECOMMENDED CAMPAIGNS TO LINK (Acc1):")
print("  • Search_AR_Brand  ($600/d)")
print("  • Search_AR_Brand_v2  ($1800/d)")
print("  • ImpressionShare_Search_AR_Brand  ($100/d)")
print()
print("Asset resource names (for next-step linking):")
for text, url, rn in new_rns:
    print(f"  {rn}  ({text})")
