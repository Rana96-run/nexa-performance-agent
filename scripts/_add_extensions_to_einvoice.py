"""Add the 4 missing extension assets to both ZATCA Phase 2 campaigns:
  1. Sitelink extensions (4 per campaign)
  2. Callout extensions (8 per campaign)
  3. Structured snippet extension (Features)
  4. Call extension (Saudi 800 number)

Google Ads API pattern for extensions (v23):
  - Create Asset of type SitelinkAsset / CalloutAsset / StructuredSnippetAsset / CallAsset
  - Link Asset to Campaign via CampaignAsset with field_type matching the asset type
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client

ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]   # ZATCAPhase2 + ZATCAVendorShop

# Saudi phone — placeholder, replace with real Qoyod sales number
SAUDI_PHONE = "+966112345678"

client     = get_client()
asset_svc  = client.get_service("AssetService")
camp_asset_svc = client.get_service("CampaignAssetService")
ga         = client.get_service("GoogleAdsService")


def create_asset(asset_op_builder, label: str) -> str:
    """Create one asset, return resource_name."""
    op = client.get_type("AssetOperation")
    asset_op_builder(op.create)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    print(f"    ✅ asset {label}: {rn}")
    return rn


def link_assets_to_campaigns(asset_rns: list[str], field_type_name: str):
    """Link each asset to each campaign with the given field_type."""
    ops = []
    field_type = getattr(client.enums.AssetFieldTypeEnum, field_type_name)
    for cid in CAMP_IDS:
        for arn in asset_rns:
            op = client.get_type("CampaignAssetOperation")
            ca = op.create
            ca.campaign  = f"customers/{ACCOUNT}/campaigns/{cid}"
            ca.asset     = arn
            ca.field_type = field_type
            ops.append(op)
    r = camp_asset_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
    print(f"    ✅ linked {len(r.results)} asset-to-campaign association(s) as {field_type_name}")


# ── 1. SITELINK extensions (4) ──────────────────────────────────────────────
print("=" * 70)
print("1. SITELINK extensions")
print("=" * 70)
SITELINKS = [
    {
        "text":          "حاسبة المرحلة الثانية",   # was 26 chars — Google limit is 25
        "description1":  "احسب موعد إلزامك",
        "description2":  "حسب إيرادات شركتك",
        "final_url":     "https://lp.qoyod.com/einvoice-integration/#deadline",
    },
    {
        "text":          "خطط الأسعار",
        "description1":  "ابدأ من 49 ريال شهرياً",
        "description2":  "بدون رسوم خفية",
        "final_url":     "https://www.qoyod.com/pricing",
    },
    {
        "text":          "احجز عرض توضيحي",
        "description1":  "30 دقيقة مع فريقنا",
        "description2":  "اعرف الموعد المناسب لك",
        "final_url":     "https://lp.qoyod.com/einvoice-integration/#demo",
    },
    {
        "text":          "تواصل مع المبيعات",
        "description1":  "متاحون 24/7",
        "description2":  "دعم سعودي محلي",
        "final_url":     "https://lp.qoyod.com/einvoice-integration/#contact",
    },
]
sitelink_rns = []
for sl in SITELINKS:
    def build(create_obj, sl=sl):
        create_obj.name = f"Sitelink_{sl['text'][:20]}"
        sitelink = create_obj.sitelink_asset
        sitelink.link_text     = sl["text"]
        sitelink.description1  = sl["description1"]
        sitelink.description2  = sl["description2"]
        create_obj.final_urls.append(sl["final_url"])
    sitelink_rns.append(create_asset(build, sl["text"]))
link_assets_to_campaigns(sitelink_rns, "SITELINK")


# ── 2. CALLOUT extensions (8) ──────────────────────────────────────────────
print()
print("=" * 70)
print("2. CALLOUT extensions")
print("=" * 70)
CALLOUTS = [
    "متوافق مع ZATCA",
    "REST API",
    "XML + PDF/A-3",
    "دعم 24/7 بالعربية",
    "بدون بطاقة ائتمان",
    "تجربة 14 يوم",
    "ربط في دقائق",
    "آلاف الشركات السعودية",
]
callout_rns = []
for c in CALLOUTS:
    def build(create_obj, c=c):
        create_obj.name = f"Callout_{c[:20]}"
        create_obj.callout_asset.callout_text = c
    callout_rns.append(create_asset(build, c))
link_assets_to_campaigns(callout_rns, "CALLOUT")


# ── 3. STRUCTURED SNIPPET extension (Features) ──────────────────────────────
print()
print("=" * 70)
print("3. STRUCTURED SNIPPET extension")
print("=" * 70)
SNIPPET_HEADER = "Features"
SNIPPET_VALUES = ["XML", "PDF/A-3", "REST API", "QR Code", "Encrypted Seal"]

def build_snippet(create_obj):
    create_obj.name = f"StructuredSnippet_{SNIPPET_HEADER}"
    ss = create_obj.structured_snippet_asset
    ss.header = SNIPPET_HEADER
    for v in SNIPPET_VALUES:
        ss.values.append(v)

snippet_rn = create_asset(build_snippet, f"{SNIPPET_HEADER}/{','.join(SNIPPET_VALUES)}")
link_assets_to_campaigns([snippet_rn], "STRUCTURED_SNIPPET")


# ── 4. CALL extension (Saudi 800 number) ────────────────────────────────────
print()
print("=" * 70)
print("4. CALL extension")
print("=" * 70)

def build_call(create_obj):
    create_obj.name = f"Call_{SAUDI_PHONE}"
    call = create_obj.call_asset
    call.country_code = "SA"
    call.phone_number = SAUDI_PHONE
    call.call_conversion_reporting_state = (
        client.enums.CallConversionReportingStateEnum.DISABLED
    )

call_rn = create_asset(build_call, SAUDI_PHONE)
link_assets_to_campaigns([call_rn], "CALL")


print()
print("=" * 70)
print("ALL 4 EXTENSION TYPES ADDED TO BOTH CAMPAIGNS")
print("=" * 70)
print()
print("Verify with: railway run python -m scripts._audit_einvoice_campaigns")
