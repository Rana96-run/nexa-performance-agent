"""Two targeted fixes on Account 2:

  A. PMax_AR_Invoice_Technology — add tech-stack callouts + snippets + call extension
  B. Leads-English-Search-Aug-3(Exp) — add 4 English sitelinks
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"

PMAX_TECH_ID    = "23844719995"
ENGLISH_CAMP_ID = "14353925266"

QOYOD_PHONE = "8004330088"

# ── A. PMax_AR_Invoice_Technology — tech-stack tailoring ──────────────────
TECH_CALLOUTS = [
    "REST API كامل",                 # 13
    "توثيق للمطورين",                # 14
    "تكامل مع 10+ منصات",            # 19
    "WebHooks في الزمن الحقيقي",     # 25
    "OAuth 2.0 آمن",                # 15
    "JSON + XML",                    # 11
    "بدون قيود على الطلبات",         # 22
    "متعدد العملات والفروع",          # 22
]

TECH_SNIPPETS = [
    {"header": "Types", "values": ["REST API", "WebHooks", "OAuth 2.0", "JSON", "ZATCA SDK"]},
    {"header": "Featured", "values": ["API Access", "Custom Reports", "Integrations", "Automation", "Audit Logs"]},
]

# ── B. English sitelinks for Leads-English-Search-Aug-3 ────────────────────
EN_SITELINKS = [
    {"text": "Features",     "d1": "Everything in one platform",  "d2": "Invoicing, stock, reports",
     "url":  "https://lp.qoyod.com/accounting/#features"},
    {"text": "How it works",  "d1": "Get started in 3 steps",      "d2": "14-minute onboarding",
     "url":  "https://lp.qoyod.com/accounting/#how"},
    {"text": "Pricing",       "d1": "From SAR 120/month",          "d2": "No hidden fees",
     "url":  "https://lp.qoyod.com/accounting/#pricing"},
    {"text": "FAQs",          "d1": "Phase 2 compliance + more",    "d2": "ISO 27001 secure",
     "url":  "https://lp.qoyod.com/accounting/#faq"},
]

# Validation
for c in TECH_CALLOUTS: assert len(c) <= 25, c
for s in TECH_SNIPPETS:
    for v in s["values"]: assert len(v) <= 25, v
for sl in EN_SITELINKS:
    assert len(sl["text"])  <= 25, sl
    assert len(sl["d1"])    <= 35, sl
    assert len(sl["d2"])    <= 35, sl


client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

# ─── A1. Tech callouts ─────────────────────────────────────────────────────
print("A1. Create 8 tech-stack callouts")
tech_callout_rns = []
for text in TECH_CALLOUTS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Callout_tech_{text[:18]}"
    op.create.callout_asset.callout_text = text
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    tech_callout_rns.append(r.results[0].resource_name)
    print(f"  ✅ {text}")

# ─── A2. Tech snippets ─────────────────────────────────────────────────────
print("\nA2. Create 2 tech snippets")
tech_snippet_rns = []
for sn in TECH_SNIPPETS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Snippet_tech_{sn['header']}"
    op.create.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        op.create.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    tech_snippet_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sn['header']}: {', '.join(sn['values'])}")

# ─── A3. Call extension for PMax tech (it has none) ────────────────────────
print("\nA3. Create call extension")
op = client.get_type("AssetOperation")
op.create.name = f"Call_Qoyod_{QOYOD_PHONE}_tech"
op.create.call_asset.country_code = "SA"
op.create.call_asset.phone_number = QOYOD_PHONE
op.create.call_asset.call_conversion_reporting_state = (
    client.enums.CallConversionReportingStateEnum
    .USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION
)
r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
tech_call_rn = r.results[0].resource_name
print(f"  ✅ {QOYOD_PHONE}")

# ─── A4. Link tech assets to PMax_AR_Invoice_Technology ────────────────────
print("\nA4. Link to PMax_AR_Invoice_Technology")
ops = []
for arn in tech_callout_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{PMAX_TECH_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
    ops.append(op)
for arn in tech_snippet_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{PMAX_TECH_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
    ops.append(op)
op = client.get_type("CampaignAssetOperation")
op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{PMAX_TECH_ID}"
op.create.asset      = tech_call_rn
op.create.field_type = client.enums.AssetFieldTypeEnum.CALL
ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} assets to PMax_AR_Invoice_Technology")

# ─── B1. English sitelinks ─────────────────────────────────────────────────
print("\nB1. Create 4 English sitelinks")
en_sl_rns = []
for sl in EN_SITELINKS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Sitelink_EN_{sl['text']}"
    op.create.sitelink_asset.link_text     = sl["text"]
    op.create.sitelink_asset.description1  = sl["d1"]
    op.create.sitelink_asset.description2  = sl["d2"]
    op.create.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    en_sl_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sl['text']:<14}  {sl['url']}")

# ─── B2. Link English sitelinks ────────────────────────────────────────────
print("\nB2. Link to Leads-English-Search-Aug-3(Exp)")
ops = []
for arn in en_sl_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{ENGLISH_CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} EN sitelinks")
