"""Full audience + extension bundle for Google_Search_AR_FinancialStatemnt:

  1. Apply canonical UTM final_url_suffix + custom params
  2. Set targeting_setting AUDIENCE bid_only=True (observation mode)
  3. Create 6 sitelinks anchored on lp.qoyod.com/qawaem/
  4. Create 8 callouts themed to Decision 236
  5. Create 2 structured snippets (Types + Service catalog) in Arabic
  6. Link new sitelinks + callouts + snippets + call extension (8004330088)
  7. Attach 11 in-market + affinity observation audiences
  8. Attach 3 customer EXCLUSIONS
  9. Attach 4 warm observation user lists
 10. Attach domain visitor list (9390701826 from earlier)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client, STANDARD_UTM_SUFFIX

ACCOUNT  = "1513020554"
CAMP_ID  = "23861837000"
AG_ID    = "198301170444"
LP_URL   = "https://lp.qoyod.com/qawaem/"

CAMPAIGN_NAME = "Google_Search_AR_FinancialStatemnt"
AD_NAME       = "Google_Search_AR_FinancialStatemntV1"
AG_NAME       = "FinancialSt_AR"

# ── Asset definitions ──────────────────────────────────────────────────────
SITELINKS = [
    {"text": "حاسبة الغرامة",      "d1": "احسب غرامتك حسب رأس المال",   "d2": "حتى 20,000 ريال شخصياً",
     "url": "https://lp.qoyod.com/qawaem/#penalty"},
    {"text": "موعد الإيداع",        "d1": "ينتهي 30 يونيو 2026",         "d2": "أيام معدودة قبل الغرامة",
     "url": "https://lp.qoyod.com/qawaem/#deadline"},
    {"text": "خطوات الإيداع",       "d1": "من قيود إلى منصة قوائم",     "d2": "في 4 خطوات بسيطة",
     "url": "https://lp.qoyod.com/qawaem/#integration"},
    {"text": "شروط الإعفاء",        "d1": "هل شركتك معفاة من التدقيق؟", "d2": "احسب الآن",
     "url": "https://lp.qoyod.com/qawaem/#exemption"},
    {"text": "خطط الأسعار",         "d1": "من 120 ريال شهرياً",          "d2": "بدون رسوم خفية",
     "url": "https://lp.qoyod.com/qawaem/#pricing"},
    {"text": "الأسئلة الشائعة",     "d1": "كل ما تحتاج عن قرار 236",     "d2": "إجابات من خبراء",
     "url": "https://lp.qoyod.com/qawaem/#faq"},
]

CALLOUTS = [
    "تجنب غرامة قرار 236",            # 19
    "إيداع في دقائق",                # 14
    "متوافق منصة قوائم",             # 17
    "تصدير XBRL تلقائي",            # 17
    "متوافق ZATCA + قوائم",          # 19
    "حماية المدير من الغرامة",        # 21
    "دعم عربي 24/7",                # 13
    "50,000+ شركة سعودية",          # 20
]

SNIPPETS = [
    {"header": "Types",
     "values": ["قوائم مالية", "ميزانية عمومية", "قائمة دخل", "تدفقات نقدية", "XBRL"]},
    {"header": "Service catalog",
     "values": ["محاسبة", "فوترة إلكترونية", "تقارير", "تدقيق", "امتثال"]},
]

QOYOD_PHONE = "8004330088"

# Audiences (global IDs)
IN_MARKET = ["80133","80137","80281","80463","80530","80536","80279","80518","80538","92913","92931"]

# User lists by name
EXCLUDE_LIST_NAMES = [
    "HubSpot - All Customers",
    "HubSpot - Advanced/Premium/Pro Subscribers",
    "Active SaaS Users",
]
OBSERVE_LIST_NAMES = [
    "HubSpot - All Marketing Contacts",
    "All Converters",
    "Ad Video Viewers",
    "Channel Video Viewers",
    "e-invoice page",   # bonus: e-invoice page visitors are likely 236 buyers too
]
DOMAIN_VISITOR_RN = "customers/1513020554/userLists/9390701826"


client    = get_client()
camp_svc  = client.get_service("CampaignService")
asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")
cc_svc    = client.get_service("CampaignCriterionService")
ga        = client.get_service("GoogleAdsService")


def mask(*p): return field_mask_pb2.FieldMask(paths=list(p))


# ── 1. UTM final_url_suffix + custom params + AUDIENCE bid_only ───────────
print("=" * 70)
print("1. Apply canonical UTM suffix + custom params + AUDIENCE bid_only")
print("=" * 70)
op = client.get_type("CampaignOperation")
u = op.update
u.resource_name    = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
u.final_url_suffix = STANDARD_UTM_SUFFIX
for k, v in [
    ("campaign", CAMPAIGN_NAME),
    ("adname",   AD_NAME),
    ("adgroupname", AG_NAME),
    ("adgroupid",   AG_ID),
]:
    p = client.get_type("CustomParameter")
    p.key = k; p.value = v
    u.url_custom_parameters.append(p)
tr = client.get_type("TargetRestriction")
tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
tr.bid_only            = True
u.targeting_setting.target_restrictions.append(tr)
client.copy_from(op.update_mask, mask(
    "final_url_suffix",
    "url_custom_parameters",
    "targeting_setting.target_restrictions",
))
r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=[op])
print(f"  ✅ {r.results[0].resource_name}")


# ── 2. Create sitelinks ───────────────────────────────────────────────────
print("\n2. Create 6 sitelinks")
sitelink_rns = []
for sl in SITELINKS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Sitelink_qawaem_{sl['text'][:18]}"
    op.create.sitelink_asset.link_text     = sl["text"]
    op.create.sitelink_asset.description1  = sl["d1"]
    op.create.sitelink_asset.description2  = sl["d2"]
    op.create.final_urls.append(sl["url"])
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    sitelink_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sl['text']:<22} → {sl['url']}")


# ── 3. Create callouts ────────────────────────────────────────────────────
print("\n3. Create 8 callouts")
callout_rns = []
for text in CALLOUTS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Callout_qawaem_{text[:18]}"
    op.create.callout_asset.callout_text = text
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    callout_rns.append(r.results[0].resource_name)
    print(f"  ✅ {text}")


# ── 4. Create snippets ────────────────────────────────────────────────────
print("\n4. Create 2 structured snippets (AR values)")
snippet_rns = []
for sn in SNIPPETS:
    op = client.get_type("AssetOperation")
    op.create.name = f"Snippet_qawaem_{sn['header']}"
    op.create.structured_snippet_asset.header = sn["header"]
    for v in sn["values"]:
        op.create.structured_snippet_asset.values.append(v)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    snippet_rns.append(r.results[0].resource_name)
    print(f"  ✅ {sn['header']}: {', '.join(sn['values'])}")


# ── 5. Create call extension (or reuse existing) ──────────────────────────
print("\n5. Find or create call extension (8004330088)")
q = """
SELECT asset.resource_name, asset.call_asset.phone_number
FROM asset
WHERE asset.type = 'CALL' AND asset.call_asset.phone_number = '8004330088'
"""
call_rn = None
for r in ga.search(customer_id=ACCOUNT, query=q):
    call_rn = r.asset.resource_name
    break
if not call_rn:
    op = client.get_type("AssetOperation")
    op.create.name = f"Call_Qoyod_{QOYOD_PHONE}_qawaem"
    op.create.call_asset.country_code = "SA"
    op.create.call_asset.phone_number = QOYOD_PHONE
    op.create.call_asset.call_conversion_reporting_state = (
        client.enums.CallConversionReportingStateEnum
        .USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION
    )
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    call_rn = r.results[0].resource_name
    print(f"  ✅ created: {call_rn}")
else:
    print(f"  reusing: {call_rn}")


# ── 6. Link all extensions to campaign ────────────────────────────────────
print(f"\n6. Link 6 sitelinks + 8 callouts + 2 snippets + 1 call to campaign")
ops = []
for arn in sitelink_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
    ops.append(op)
for arn in callout_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.CALLOUT
    ops.append(op)
for arn in snippet_rns:
    op = client.get_type("CampaignAssetOperation")
    op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.asset      = arn
    op.create.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET
    ops.append(op)
op = client.get_type("CampaignAssetOperation")
op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
op.create.asset      = call_rn
op.create.field_type = client.enums.AssetFieldTypeEnum.CALL
ops.append(op)
r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ linked {len(r.results)} assets")


# ── 7. Resolve user list RNs ──────────────────────────────────────────────
print("\n7. Resolve user list resource names")
exclude_rns = {}
observe_rns = {}
q = """
SELECT user_list.resource_name, user_list.name, user_list.size_for_search
FROM user_list
WHERE user_list.size_for_search >= 1000
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    n = r.user_list.name
    if n in EXCLUDE_LIST_NAMES and n not in exclude_rns:
        exclude_rns[n] = r.user_list.resource_name
    if n in OBSERVE_LIST_NAMES and n not in observe_rns:
        observe_rns[n] = r.user_list.resource_name
print(f"  excludes: {len(exclude_rns)}  observes: {len(observe_rns)}")


# ── 8. Attach all audience signals ────────────────────────────────────────
print(f"\n8. Attach audiences: {len(IN_MARKET)} in-market + "
      f"{len(exclude_rns)} excludes + {len(observe_rns)} observes + 1 domain-visitor")
ops = []
# In-market + affinity (observation)
for aid in IN_MARKET:
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.user_interest.user_interest_category = f"customers/{ACCOUNT}/userInterests/{aid}"
    ops.append(op)
# Customer exclusions
for n, rn in exclude_rns.items():
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.user_list.user_list = rn
    op.create.negative = True
    ops.append(op)
# Warm observation
for n, rn in observe_rns.items():
    op = client.get_type("CampaignCriterionOperation")
    op.create.campaign = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
    op.create.user_list.user_list = rn
    op.create.negative = False
    ops.append(op)
# Domain visitor list
op = client.get_type("CampaignCriterionOperation")
op.create.campaign = f"customers/{ACCOUNT}/campaigns/{CAMP_ID}"
op.create.user_list.user_list = DOMAIN_VISITOR_RN
op.create.negative = False
ops.append(op)

r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ added {len(r.results)} audience associations")

print("\n" + "=" * 70)
print("DONE — full bundle applied to Google_Search_AR_FinancialStatemnt")
print("=" * 70)
