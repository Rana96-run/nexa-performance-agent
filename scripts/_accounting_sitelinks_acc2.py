"""Account 2 (5753494964):
  1. Create the same 4 /accounting sitelinks as assets (assets are per-account)
  2. Link to all relevant lead-gen + e-invoice generic campaigns
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"

# Lead-gen + generic-accounting ENABLED campaigns from the audit.
# Excluded: PMax_AR_Invoice_Technology (will get sector-tailored set in P2),
#           PMax_AR_Invoice (already has 8 sitelinks — leave for now),
#           Search_E-invoice_AR / Test / Aug-4 / ImpressionShare_Search_AR_Invoice
#                (will get ZATCA-themed set in P2 phase)
TARGET_CAMPS = {
    "1624813104":  "Search AR CPA Best Converters",
    "13910658414": "Leads-Search-Arabic-Jul#1-(EXP)",
    "14051112466": "E-Invoice-Search-Arabic(EXP2)",     # currently NO callouts/snippets
    "13913291987": "E-Invoice-Search-Arabic(EXP)",
    "14051278536": "Leads-Search-Arabic-Jul#2(EXP2)",   # currently 0 sitelinks
    "14054086994": "Leads-Search-Arabic-Jul#1(EXP2)",
    "14353048311": "Leads-Arabic-Search-Aug-1(Exp)",
    "14353071777": "Leads-Arabic-Search-Aug-2(Exp)",
    "14354680547": "Leads-E-invoice-Arabic-Search-Aug-4(Exp)",
}

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

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# ── 1. Create the 4 assets on Acc2 ─────────────────────────────────────────
print("=" * 70)
print("1. Create sitelink assets on Account 2")
print("=" * 70)
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
    new_rns.append(rn)
    print(f"  ✅ {sl['text']:<22}  {rn}")

# ── 2. Link to each target campaign ────────────────────────────────────────
print()
print("=" * 70)
print(f"2. Link 4 sitelinks × {len(TARGET_CAMPS)} campaigns")
print("=" * 70)
ops = []
for cid, name in TARGET_CAMPS.items():
    for arn in new_rns:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ created {len(r.results)} associations")
