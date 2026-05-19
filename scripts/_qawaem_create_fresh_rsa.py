"""Force fresh policy review on the Qawaem campaign by creating NEW RSAs
(slightly different content) on each ad group. New ads go through full
policy review instead of inheriting the cached DESTINATION_NOT_WORKING
verdict from the existing disapproved ads."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
LP_URL  = "https://lp.qoyod.com/qawaem/"

AR_AG_ID = "198301170444"
EN_AG_ID = "199721186547"

# Slight variation from the existing disapproved RSA — bust any content-cache
AR_HEADLINES = [
    "إيداع القوائم المالية | قيود",
    "تجنب غرامة قرار 236 الشخصية",
    "30 يونيو 2026 - الموعد النهائي",
    "غرامة شخصية تصل 20,000 ريال",
    "أودع على منصة قوائم بسرعة",
    "تصدير XBRL تلقائياً",
    "50,000+ شركة سعودية",
    "متوافق ZATCA وقوائم معاً",
    "تجربة 14 يوم مجانية",
    "إعداد سريع في 14 دقيقة",
    "مسؤوليتك الشخصية كمدير",
    "احمِ شركتك من قرار 236",
    "ابدأ مجاناً بدون بطاقة",
    "قيود لحلول الفوترة السعودية",
    "أسعار من 120 ريال شهرياً",
]
AR_DESCRIPTIONS = [
    "إيداع القوائم المالية في منصة قوائم بسهولة. تجنب غرامة قرار 236 الشخصية. ابدأ مجاناً.",
    "أكثر من 50,000 شركة سعودية تستخدم قيود. تجربة كاملة 14 يوم. لا تحتاج بطاقة ائتمان.",
    "موعد إيداع قوائم 2025 ينتهي 30 يونيو 2026. غرامة المدير حتى 20,000 ريال.",
    "تكامل قيود مع منصة قوائم وفاتورة. دعم عربي 24/7. متخصص في السوق السعودي.",
]

EN_HEADLINES = [
    "Qoyod for Decision 236",
    "Avoid Personal Director Fines",
    "Deadline: June 30, 2026",
    "Fines Up to SAR 20,000",
    "File to Qawaem Quickly",
    "Built-In XBRL Export",
    "50,000+ Saudi Businesses",
    "ZATCA + Qawaem Compatible",
    "14-Day Free Trial",
    "Protect Directors",
    "Setup in 14 Minutes",
    "Compliance Guaranteed",
    "Start Free - No Card Needed",
]
EN_DESCRIPTIONS = [
    "Decision 236 puts personal fines on directors. Qoyod files to Qawaem fast. Start free.",
    "Export financial statements as XBRL to Qawaem with one click. ZATCA-aligned. Audit-ready.",
    "Deadline June 30, 2026 for 2025 statements. Up to SAR 20,000 per director. Start now.",
    "50,000+ Saudi businesses use Qoyod. ISO 27001 certified. 14-day free trial, no card.",
]


client = get_client()
agad_svc = client.get_service("AdGroupAdService")


def build_rsa(ag_id, headlines, descriptions):
    op = client.get_type("AdGroupAdOperation")
    op.create.ad_group = f"customers/{ACCOUNT}/adGroups/{ag_id}"
    op.create.status   = client.enums.AdGroupAdStatusEnum.ENABLED
    op.create.ad.final_urls.append(LP_URL)
    for h in headlines:
        a = client.get_type("AdTextAsset"); a.text = h
        op.create.ad.responsive_search_ad.headlines.append(a)
    for d in descriptions:
        a = client.get_type("AdTextAsset"); a.text = d
        op.create.ad.responsive_search_ad.descriptions.append(a)
    return op


# Validate lengths
for h in AR_HEADLINES + EN_HEADLINES:
    assert len(h) <= 30, f"too long ({len(h)}): {h}"
for d in AR_DESCRIPTIONS + EN_DESCRIPTIONS:
    assert len(d) <= 90, f"too long ({len(d)}): {d}"

print("Creating fresh RSAs on both ad groups to force new policy review")
ops = [build_rsa(AR_AG_ID, AR_HEADLINES, AR_DESCRIPTIONS),
       build_rsa(EN_AG_ID, EN_HEADLINES, EN_DESCRIPTIONS)]

try:
    r = agad_svc.mutate_ad_group_ads(customer_id=ACCOUNT, operations=ops)
    for res in r.results:
        print(f"  ✅ new RSA: {res.resource_name}")
    print("\nFresh RSAs created. They'll go through policy review (~1-24h).")
    print("Once they're APPROVED, pause the old disapproved ads:")
    print("  AR old:  customers/1513020554/adGroupAds/198301170444~809297773356")
    print("  EN old:  customers/1513020554/adGroupAds/199721186547~809299010076")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:5]:
        print(f"  ❌ {m}")
