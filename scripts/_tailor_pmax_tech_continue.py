"""Continue from the failure point: create snippet 2 with valid header,
create call extension, link all to PMax_Tech, then English sitelinks."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"
PMAX_TECH_ID    = "23844719995"
ENGLISH_CAMP_ID = "14353925266"
QOYOD_PHONE = "8004330088"

# Already created in failed run — re-fetch from the campaign-level pool would be
# possible, but simpler: re-create the ones we know succeeded? Actually they
# succeeded so they're already in the account asset pool — we just need to
# find them. Easiest: query by name.

client    = get_client()
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")
ga        = client.get_service("GoogleAdsService")

# Find existing tech callouts + Types snippet from the failed run
print("0. Re-discover tech assets already created on Acc2")
tech_callouts = []
tech_snippets = []
q1 = "SELECT asset.resource_name, asset.callout_asset.callout_text FROM asset WHERE asset.name LIKE 'Callout_tech_%'"
for r in ga.search(customer_id=ACCOUNT, query=q1):
    if r.asset.callout_asset.callout_text:
        tech_callouts.append(r.asset.resource_name)
q2 = "SELECT asset.resource_name, asset.structured_snippet_asset.header FROM asset WHERE asset.name LIKE 'Snippet_tech_%'"
for r in ga.search(customer_id=ACCOUNT, query=q2):
    if r.asset.structured_snippet_asset.header:
        tech_snippets.append(r.asset.resource_name)
print(f"  found {len(tech_callouts)} callouts + {len(tech_snippets)} snippets")

# Create the 2nd snippet with VALID header ("Service catalog" instead of "Featured")
print("\n1. Create Service catalog snippet (replacing failed 'Featured')")
op = client.get_type("AssetOperation")
op.create.name = "Snippet_tech_ServiceCatalog"
op.create.structured_snippet_asset.header = "Service catalog"
for v in ["API Access", "Custom Reports", "Integrations", "Automation", "Audit Logs"]:
    op.create.structured_snippet_asset.values.append(v)
r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
tech_snippets.append(r.results[0].resource_name)
print(f"  ✅ {r.results[0].resource_name}")

# Create call extension
print("\n2. Create call extension")
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
print(f"  ✅ {tech_call_rn}")

# Link everything to PMax_Tech
print(f"\n3. Link {len(tech_callouts)} callouts + {len(tech_snippets)} snippets + 1 call → PMax_AR_Invoice_Technology")
ops = []
for arn in tech_callouts:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{PMAX_TECH_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
    ops.append(op)
for arn in tech_snippets:
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
print(f"  ✅ linked {len(r.results)} associations")


# English sitelinks
print("\n4. Create 4 English sitelinks")
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
    print(f"  ✅ {sl['text']}")

print("\n5. Link to Leads-English-Search-Aug-3(Exp)")
ops = []
for arn in en_sl_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{ENGLISH_CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} EN sitelinks")
