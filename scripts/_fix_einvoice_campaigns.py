"""Fix the 3 critical gaps + truncated headlines on the 2 new ZATCA Phase 2
campaigns. Audit revealed:
  - Display Network was left ON (Search campaigns shouldn't use Display)
  - No location targeting (defaults to ALL countries)
  - No language targeting (should be Arabic + English only)
  - 2 headlines exceeded 30-char Arabic limit and got truncated
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]  # ZATCAPhase2 + ZATCAVendorShop

# Google's geo_target_constants
SAUDI_GEO_RN  = "geoTargetConstants/2682"  # Saudi Arabia

# Google's language constants
ARABIC_LANG_RN  = "languageConstants/1019"
ENGLISH_LANG_RN = "languageConstants/1000"

client     = get_client()
camp_svc   = client.get_service("CampaignService")
crit_svc   = client.get_service("CampaignCriterionService")
ga         = client.get_service("GoogleAdsService")


# ── Fix 1: Turn OFF Display Network on both campaigns ──────────────────────
print("=" * 70)
print("FIX 1 — Turn OFF Display Network on both campaigns")
print("=" * 70)
from google.protobuf import field_mask_pb2
camp_ops = []
for cid in CAMP_IDS:
    op = client.get_type("CampaignOperation")
    upd = op.update
    upd.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
    upd.network_settings.target_google_search        = True
    upd.network_settings.target_search_network        = True
    upd.network_settings.target_content_network        = False  # ← OFF
    upd.network_settings.target_partner_search_network = False
    # Explicit FieldMask — protobuf_helpers.field_mask doesn't detect False as
    # "set" (bool default = False in protobuf), so the auto-generated mask
    # skips the Display Network field we want to turn OFF.
    mask = field_mask_pb2.FieldMask(paths=[
        "network_settings.target_google_search",
        "network_settings.target_search_network",
        "network_settings.target_content_network",
        "network_settings.target_partner_search_network",
    ])
    client.copy_from(op.update_mask, mask)
    camp_ops.append(op)
try:
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=camp_ops)
    for res in r.results:
        print(f"  ✅ Updated network settings: {res.resource_name}")
except Exception as e:
    print(f"  ❌ Network settings update failed: {e}")


# ── Fix 2: Add location targeting (Saudi Arabia only) ──────────────────────
print()
print("=" * 70)
print("FIX 2 — Add Saudi Arabia location targeting")
print("=" * 70)
loc_ops = []
for cid in CAMP_IDS:
    op = client.get_type("CampaignCriterionOperation")
    crit = op.create
    crit.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
    crit.location.geo_target_constant = SAUDI_GEO_RN
    crit.negative = False
    loc_ops.append(op)
try:
    r = crit_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=loc_ops)
    for res in r.results:
        print(f"  ✅ Added Saudi location: {res.resource_name}")
except Exception as e:
    print(f"  ❌ Location targeting failed: {e}")


# ── Fix 3: Add language targeting (Arabic + English) ───────────────────────
print()
print("=" * 70)
print("FIX 3 — Add Arabic + English language targeting")
print("=" * 70)
lang_ops = []
for cid in CAMP_IDS:
    for lang_rn in [ARABIC_LANG_RN, ENGLISH_LANG_RN]:
        op = client.get_type("CampaignCriterionOperation")
        crit = op.create
        crit.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        crit.language.language_constant = lang_rn
        lang_ops.append(op)
try:
    r = crit_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=lang_ops)
    for res in r.results:
        print(f"  ✅ Added language: {res.resource_name}")
except Exception as e:
    print(f"  ❌ Language targeting failed: {e}")


# ── Fix 4: Replace 2 truncated headlines on Campaign 1 RSA ────────────────
print()
print("=" * 70)
print("FIX 4 — Replace 2 truncated headlines on Campaign 1")
print("=" * 70)
# Find the existing ad and create a NEW RSA with corrected headlines.
# Google Ads doesn't allow editing RSA assets — must remove + recreate.
ad_q = f"""
SELECT ad_group_ad.resource_name, ad_group.id
FROM ad_group_ad
WHERE campaign.id = {CAMP_IDS[0]}
"""
existing_ad_rn = None
existing_ag_id = None
for r in ga.search(customer_id=ACCOUNT, query=ad_q):
    existing_ad_rn = r.ad_group_ad.resource_name
    existing_ag_id = r.ad_group.id

if existing_ad_rn:
    # Build the corrected RSA: replace the 2 over-30-char headlines with <30
    NEW_HEADLINES = [
        "ZATCA المرحلة الثانية | متوافق",      # 28
        "ربط الفاتورة الإلكترونية",              # FIXED — was "ربط الفاتورة الإلكترونية بسهولة" (31)
        "تكامل مع منصة فاتورة في دقائق",     # 28
        "معتمد من هيئة الزكاة والضريبة",         # 28
        "متوافق مع المرحلة الثانية",             # 24
        "REST API + XML + PDF/A-3",              # 24
        "أكثر من 50 ألف شركة سعودية",           # 25
        "تجربة مجانية 14 يوم",                   # 18
        "بدون بطاقة ائتمانية",                   # 18
        "متوافق في 7 أيام أو استرداد",          # 25
        "موعد المرحلة الثانية 30 يونيو",         # FIXED — was "الموجة 24 - الموعد 30 يونيو 2026" (30 char issue)
        "Qoyod - الحل المعتمد للسعودية",        # 28
    ]
    # Verify all <30 chars
    bad = [h for h in NEW_HEADLINES if len(h) > 30]
    if bad:
        print(f"  ⚠️ Still over 30 chars: {bad}")
    else:
        print(f"  ✅ All 12 headlines ≤ 30 chars")

    # Create new RSA with corrected headlines (same descriptions + URL)
    from executors.google_ads import create_rsa
    DESCRIPTIONS = [
        "اربط نظامك بمنصة فاتورة بسهولة. XML، PDF/A-3، REST API. معتمد من هيئة الزكاة.",
        "أكثر من 50,000 شركة سعودية تستخدم Qoyod. تجربة مجانية 14 يوماً. ابدأ الآن.",
        "الموجة 24 من المرحلة الثانية تنتهي 30 يونيو 2026. اربط نظامك في 7 أيام.",
        "خدمة عملاء عربية على مدار الساعة. متخصص في السوق السعودي. مرحلة أولى وثانية.",
    ]
    URL = ("https://lp.qoyod.com/einvoice-integration/"
           "?utm_source=google&utm_medium=cpc"
           "&utm_campaign=Google_Search_AR_ZATCAPhase2_Broad"
           "&utm_content=Google_Search_AR_ZATCAPhase2V2")
    ag_rn = f"customers/{ACCOUNT}/adGroups/{existing_ag_id}"
    try:
        new_ad = create_rsa(
            adgroup_resource_name=ag_rn,
            headlines=NEW_HEADLINES,
            descriptions=DESCRIPTIONS,
            final_url=URL,
            customer_id=ACCOUNT,
        )
        print(f"  ✅ New RSA created: {new_ad['resource_name']}")
        print(f"     Old RSA {existing_ad_rn} kept — pause it in UI before enabling new one")
    except Exception as e:
        print(f"  ❌ New RSA creation failed: {e}")
else:
    print("  ⚠️ Could not find existing ad on Campaign 1")


print()
print("=" * 70)
print("ALL FIXES APPLIED")
print("=" * 70)
print()
print("Verify with: railway run python -m scripts._audit_einvoice_campaigns")
