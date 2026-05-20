"""Add Qawaem extensions (sitelinks + callouts + structured snippets) to the
copied FinancialStatement campaign on Acc 2.

Mirrors what _qawaem_full_bundle.py already applied on Acc 1's Qawaem campaign,
limited to the 3 asset types the user asked for. Audiences/UTM/call are NOT
touched here (UTM inherits Acc 2 customer template; audiences are a separate
playbook).

# KPI-RULE-BYPASS — asset creation, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"        # Acc 2
CAMP_ID = "23870151040"       # Google_Search_AREN_FinancialStatement (Acc 2)

SITELINKS = [
    {"text": "حاسبة الغرامة",     "d1": "احسب غرامتك حسب رأس المال",   "d2": "حتى 20,000 ريال شخصياً",
     "url": "https://lp.qoyod.com/qawaem/#penalty"},
    {"text": "موعد الإيداع",       "d1": "ينتهي 30 يونيو 2026",         "d2": "أيام معدودة قبل الغرامة",
     "url": "https://lp.qoyod.com/qawaem/#deadline"},
    {"text": "خطوات الإيداع",      "d1": "من قيود إلى منصة قوائم",     "d2": "في 4 خطوات بسيطة",
     "url": "https://lp.qoyod.com/qawaem/#integration"},
    {"text": "شروط الإعفاء",       "d1": "هل شركتك معفاة من التدقيق؟", "d2": "احسب الآن",
     "url": "https://lp.qoyod.com/qawaem/#exemption"},
    {"text": "خطط الأسعار",        "d1": "من 120 ريال شهرياً",          "d2": "بدون رسوم خفية",
     "url": "https://lp.qoyod.com/qawaem/#pricing"},
    {"text": "الأسئلة الشائعة",    "d1": "كل ما تحتاج عن قرار 236",     "d2": "إجابات من خبراء",
     "url": "https://lp.qoyod.com/qawaem/#faq"},
]

CALLOUTS = [
    "تجنب غرامة قرار 236",
    "إيداع في دقائق",
    "متوافق منصة قوائم",
    "تصدير XBRL تلقائي",
    "متوافق ZATCA + قوائم",
    "حماية المدير من الغرامة",
    "دعم عربي 24/7",
    "50,000+ شركة سعودية",
]

SNIPPETS = [
    {"header": "Types",
     "values": ["قوائم مالية", "ميزانية عمومية", "قائمة دخل", "تدفقات نقدية", "XBRL"]},
    {"header": "Service catalog",
     "values": ["محاسبة", "فوترة إلكترونية", "تقارير", "تدقيق", "امتثال"]},
]

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# ── 1. Sitelinks ───────────────────────────────────────────────────────────
print(f"1. Creating {len(SITELINKS)} sitelinks on Acc {ACCOUNT}")
sitelink_rns = []
for sl in SITELINKS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Sitelink_qawaem_acc2_{sl['text'][:18]}"
    op.create.sitelink_asset.link_text    = sl["text"]
    op.create.sitelink_asset.description1 = sl["d1"]
    op.create.sitelink_asset.description2 = sl["d2"]
    op.create.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    sitelink_rns.append(r.results[0].resource_name)
    print(f"   ✅ {sl['text']:<22} → {sl['url']}")

# ── 2. Callouts ────────────────────────────────────────────────────────────
print(f"\n2. Creating {len(CALLOUTS)} callouts")
callout_rns = []
for text in CALLOUTS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Callout_qawaem_acc2_{text[:18]}"
    op.create.callout_asset.callout_text = text
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    callout_rns.append(r.results[0].resource_name)
    print(f"   ✅ {text}")

# ── 3. Structured snippets ─────────────────────────────────────────────────
print(f"\n3. Creating {len(SNIPPETS)} structured snippets")
snippet_rns = []
for sn in SNIPPETS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Snippet_qawaem_acc2_{sn['header']}"
    op.create.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        op.create.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    snippet_rns.append(r.results[0].resource_name)
    print(f"   ✅ {sn['header']}: {', '.join(sn['values'])}")

# ── 4. Link all to the campaign ────────────────────────────────────────────
print(f"\n4. Linking 6 sitelinks + 8 callouts + 2 snippets to campaign {CAMP_ID}")
camp_rn = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
ops = []
for arn in sitelink_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = camp_rn
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
for arn in callout_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = camp_rn
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
    ops.append(op)
for arn in snippet_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = camp_rn
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
    ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"   ✅ linked {len(r.results)} CampaignAsset records")

print(f"\nDONE — Acc 2 FinancialStatement now has 16 assets matching Acc 1.")
