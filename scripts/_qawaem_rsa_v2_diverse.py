"""Round 2: replace previous RSAs with more diverse-themed headlines to push
ad strength from GOOD → EXCELLENT.

Strategy: keep volume keywords represented but reduce "قوائم"-root repetition
(was 7/15). New mix:
  - 3 headlines with "قوائم" / "قوائم وزارة التجارة"
  - 3 headlines with "قائمة الدخل" / "ميزانية"
  - 2 headlines with "إيداع"
  - 2 headlines with "قرار 236"
  - 5 headlines with diverse value-prop angles (no overlap)

Approach: pause the previous RSAs and add fresh ones. Old RSAs remain in the
ad group archive but stop serving.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

FINAL_URL = "https://lp.qoyod.com/qawaem/"

# Diverse AR — only 3 "قوائم" + 2 "قائمة" + spread across themes
AR_HEADLINES_V2 = [
    "منصة قوائم — ربط مباشر",        # قوائم #1
    "قوائم وزارة التجارة",            # قوائم #2 — exact-match phrase
    "إيداع تلقائي في قوائم",          # قوائم #3
    "قائمة الدخل بـ XBRL",            # قائمة #1
    "ميزانية عمومية جاهزة",           # ميزانية
    "تقاريرك المالية بضغطة زر",       # أمتمتة
    "متوافق مع قرار 236",             # قرار #1
    "تجنب غرامات قرار 236",           # قرار #2
    "إيداع آمن وسريع",               # إيداع
    "صدّر بصيغة XBRL",                # XBRL
    "قيود — برنامج المحاسبة الأول",   # برنامج
    "تجربة مجانية 14 يوم",            # عرض
    "آلاف الشركات السعودية",          # دليل اجتماعي
    "دعم عربي على مدار الساعة",       # دعم
    "بدون بطاقة ائتمان",             # احتكاك
]

AR_DESCRIPTIONS_V2 = [
    "أودع قوائمك المالية مباشرة على منصة قوائم. تصدير XBRL تلقائي. متوافق مع قرار 236.",
    "قائمة الدخل، الميزانية العمومية، التدفقات النقدية — جاهزة بصيغة XBRL للإيداع.",
    "تجنب غرامة قرار 236. ربط مباشر مع منصة قوائم وزارة التجارة في دقائق.",
    "آلاف الشركات السعودية تستخدم قيود. تجربة 14 يوم مجاناً، بدون بطاقة ائتمان.",
]

EN_HEADLINES_V2 = [
    "Saudi Financial Statements",
    "File on Qawaem Platform",
    "Decision 236 Compliance",
    "XBRL Export Made Easy",
    "Balance Sheet & Income Stmt",
    "Direct Qawaem Integration",
    "Avoid Late Filing Fines",
    "14-Day Free Trial",
    "Trusted by Saudi SMEs",
    "ZATCA + Qawaem Ready",
    "Arabic Support 24/7",
    "No Credit Card Required",
    "One-Click Filing",
    "Audit-Ready Reports",
    "Cash Flow Statement",
]

EN_DESCRIPTIONS_V2 = [
    "File Saudi financial statements on Qawaem with one click. XBRL export built in.",
    "Balance sheet, income statement, cash flow — auto-built and Decision 236 ready.",
    "Trusted by Saudi businesses for compliance filing. Start your 14-day free trial.",
    "Avoid Decision 236 fines. Direct Qawaem integration in minutes. No card needed.",
]

# (account, ag_id, old_ad_id, lang, label)
TARGETS = [
    ("1513020554", "198301170444", "809535863652", "ar", "Acc 1 AR"),
    ("1513020554", "199721186547", "809536604151", "en", "Acc 1 EN"),
    ("5753494964", "197282810352", "809535850062", "ar", "Acc 2 AR"),
    ("5753494964", "205172571548", "809536567098", "en", "Acc 2 EN"),
]

# Validation
for h in AR_HEADLINES_V2 + EN_HEADLINES_V2:
    assert len(h) <= 30, f"HL too long ({len(h)}): {h}"
for d in AR_DESCRIPTIONS_V2 + EN_DESCRIPTIONS_V2:
    assert len(d) <= 90, f"DSC too long ({len(d)}): {d}"
print(f"✓ Validated all lengths")

client = get_client()
svc = client.get_service("AdGroupAdService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, ag_id, old_ad_id, lang, label in TARGETS:
    print(f"\n=== {label} ===")

    # 1. Pause the old v1 ad
    op_p = client.get_type("AdGroupAdOperation")
    op_p.update.resource_name = f"customers/{acct}/adGroupAds/{ag_id}~{old_ad_id}"
    op_p.update.status = client.enums.AdGroupAdStatusEnum.PAUSED
    op_p.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    try:
        svc.mutate_ad_group_ads(customer_id=acct, operations=[op_p])
        print(f"  ⊘ paused v1 ad {old_ad_id}")
    except Exception as e:
        print(f"  ⚠ pause v1 failed: {_err(e)[:120]}")

    # 2. Create v2 ad with diverse headlines
    hl = AR_HEADLINES_V2 if lang == "ar" else EN_HEADLINES_V2
    ds = AR_DESCRIPTIONS_V2 if lang == "ar" else EN_DESCRIPTIONS_V2

    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.ad_group = f"customers/{acct}/adGroups/{ag_id}"
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(FINAL_URL)
    for h in hl:
        ah = client.get_type("AdTextAsset"); ah.text = h
        aga.ad.responsive_search_ad.headlines.append(ah)
    for d in ds:
        ad = client.get_type("AdTextAsset"); ad.text = d
        aga.ad.responsive_search_ad.descriptions.append(ad)
    aga.ad.responsive_search_ad.path1 = "قوائم" if lang == "ar" else "qawaem"
    aga.ad.responsive_search_ad.path2 = "ايداع" if lang == "ar" else "filing"

    try:
        r = svc.mutate_ad_group_ads(customer_id=acct, operations=[op])
        print(f"  ✅ v2 RSA: {r.results[0].resource_name}")
    except Exception as e:
        print(f"  ❌ v2 create: {_err(e)}")

print("\nDONE — ad strength will compute over 5-30 min. Run "
      "_verify_qawaem_ad_strength.py after to check.")
