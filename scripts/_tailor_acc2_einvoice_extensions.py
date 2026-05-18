"""Acc2: add ZATCA Phase 2-themed callouts + 2 structured snippets to all
e-invoice / generic accounting campaigns. Pure ADDITIVE — doesn't remove
existing callouts. Google rotates and shows the best per auction."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"

CAMPS = {
    "1624813104":  "Search AR CPA Best Converters",
    "13910658414": "Leads-Search-Arabic-Jul#1-(EXP)",
    "13913291987": "E-Invoice-Search-Arabic(EXP)",          # 0 callouts/snippets
    "14051112466": "E-Invoice-Search-Arabic(EXP2)",         # 0 callouts/snippets
    "14051278536": "Leads-Search-Arabic-Jul#2(EXP2)",
    "14054086994": "Leads-Search-Arabic-Jul#1(EXP2)",
    "14353048311": "Leads-Arabic-Search-Aug-1(Exp)",
    "14353071777": "Leads-Arabic-Search-Aug-2(Exp)",
    "14354680547": "Leads-E-invoice-Arabic-Search-Aug-4(Exp)",
    "16851344135": "Search_E-invoice_AR",                   # $200/d
    "22790330091": "PMax_AR_Invoice",                       # $100/d
    "23348517003": "ImpressionShare_Search_AR_Invoice",     # $400/d
    "23835392373": "Search_E-invoice_AR_Test",
}

# 8 ZATCA-themed callouts (max 25 chars each)
CALLOUTS = [
    "متوافق ZATCA المرحلة 2",       # 22
    "REST API + XML + PDF/A-3",     # 24
    "ربط في دقائق",                # 12
    "آلاف الشركات السعودية",       # 21
    "بدون بطاقة ائتمان",           # 18
    "تجربة 14 يوم مجانية",         # 20
    "دعم عربي 24/7",              # 13
    "ضمان الامتثال أو استرداد",    # 24
]

# 2 snippets (Types + Service catalog)
SNIPPETS = [
    {"header": "Types",           "values": ["XML", "PDF/A-3", "REST API", "QR Code", "ختم مشفر"]},
    {"header": "Service catalog", "values": ["فوترة إلكترونية", "محاسبة", "مخزون", "تقارير", "نقاط بيع"]},
]

# Validate
for c in CALLOUTS:
    assert len(c) <= 25, f"callout {len(c)}: {c}"
for s in SNIPPETS:
    for v in s["values"]:
        assert len(v) <= 25, v

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# ── 1. Create callout assets ───────────────────────────────────────────────
print(f"1. Create {len(CALLOUTS)} ZATCA-themed callouts on Acc2")
callout_rns = []
for text in CALLOUTS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Callout_zatca_{text[:18]}"
    op.create.callout_asset.callout_text = text
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    callout_rns.append(r.results[0].resource_name)
    print(f"  ✅ {text}")

# ── 2. Create snippet assets ───────────────────────────────────────────────
print(f"\n2. Create {len(SNIPPETS)} structured snippets on Acc2")
snippet_rns = []
for sn in SNIPPETS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Snippet_{sn['header']}_zatca_v2"
    op.create.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        op.create.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    snippet_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sn['header']}: {', '.join(sn['values'])}")

# ── 3. Link to all 13 campaigns ────────────────────────────────────────────
print(f"\n3. Link {len(CALLOUTS) + len(SNIPPETS)} new assets × {len(CAMPS)} campaigns")
ops = []
for cid in CAMPS:
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
print(f"  ✅ created {len(r.results)} associations")
