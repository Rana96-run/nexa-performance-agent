"""Acc1: add brand-themed callouts + snippets to the 3 Brand campaigns.

Brand search intent = "I want Qoyod." Extensions should:
- Reinforce official-ness, scale, trust signals
- Emphasize free trial / no card / fast onboarding
- NOT lean heavily on features (the user already knows the product)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"

BRAND_CAMPS = {
    "22221111741": "ImpressionShare_Search_AR_Brand",
    "22434988923": "Search_AR_Brand",
    "23032247671": "Search_AR_Brand_v2",
}

# 8 brand-themed callouts (≤25 chars)
BRAND_CALLOUTS = [
    "الموقع الرسمي لقيود",         # 19
    "أكثر من 50,000 شركة",          # 19
    "ISO 27001 معتمد",            # 15
    "تشفير AES-256",              # 13
    "متوافق ZATCA المرحلة 2",       # 22
    "تجربة 14 يوم بدون بطاقة",     # 23
    "دعم عربي 24/7",              # 13
    "إعداد في 14 دقيقة",           # 18
]

BRAND_SNIPPETS = [
    {"header": "Service catalog",
     "values": ["محاسبة", "فوترة إلكترونية", "نقاط بيع", "إدارة المخزون", "تقارير مالية"]},
    {"header": "Types",
     "values": ["سحابي", "تطبيق جوال", "REST API", "متعدد العملات", "متعدد الفروع"]},
]

for c in BRAND_CALLOUTS:
    assert len(c) <= 25, c
for s in BRAND_SNIPPETS:
    for v in s["values"]:
        assert len(v) <= 25, v

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# Create callouts
print("1. Create 8 brand-themed callouts on Acc1")
callout_rns = []
for text in BRAND_CALLOUTS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Callout_brand_{text[:18]}"
    op.create.callout_asset.callout_text = text
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    callout_rns.append(r.results[0].resource_name)
    print(f"  ✅ {text}")

# Create snippets
print("\n2. Create 2 brand-themed snippets on Acc1")
snippet_rns = []
for sn in BRAND_SNIPPETS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Snippet_brand_{sn['header']}"
    op.create.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        op.create.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    snippet_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sn['header']}: {', '.join(sn['values'])}")

# Link to all 3 brand campaigns
print(f"\n3. Link to 3 brand campaigns")
ops = []
for cid in BRAND_CAMPS:
    for arn in callout_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
        ops.append(op)
    for arn in snippet_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
        ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} associations  (10 assets × 3 campaigns)")
