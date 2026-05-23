"""Deploy keyword-rich RSA to Search_AR_Brand v1 (the winner).

Target: Acc 1 Search_AR_Brand (22434988923) → AG قيود (179440336713)
Added ALONGSIDE existing ads (not replacing — v1 is already at 36% CTR).

# KPI-RULE-BYPASS — RSA creation, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

ACCT  = "1513020554"
AG_ID = "179440336713"   # Search_AR_Brand / قيود

# 15 headlines built around the 4 brand-keyword variations + value props
HEADLINES = [
    "نظام قيود المحاسبي",          # H1 — covers "نظام قيود"
    "برنامج قيود المحاسبي",         # H2 — covers "برنامج قيود المحاسبي"
    "منصة قيود الكاملة",            # H3 — covers "منصة قيود"
    "برنامج قيود لإدارة منشأتك",    # H4 — covers "برنامج قيود"
    "قيود — الأكثر استخداماً",
    "فوترة إلكترونية ZATCA",
    "تقارير مالية احترافية",
    "إدارة المخزون والرواتب",
    "آلاف الشركات السعودية",
    "تجربة 14 يوم مجاناً",
    "متوافق ZATCA + قوائم",
    "دعم عربي 24/7",
    "بدون بطاقة ائتمان",
    "ابدأ مع قيود اليوم",
    "حلول محاسبية متكاملة",
]

DESCRIPTIONS = [
    "برنامج قيود المحاسبي — نظام شامل لإدارة محاسبتك وفواتيرك ومخزونك وتقاريرك المالية.",
    "منصة قيود — الكل في برنامج واحد. متوافق ZATCA + قوائم وزارة التجارة. تجربة 14 يوم.",
    "نظام قيود — الأكثر استخداماً بين الشركات السعودية. دعم عربي 24/7. بدون بطاقة ائتمان.",
    "ابدأ مع قيود اليوم. تجربة مجانية 14 يوم. لا التزامات، لا بطاقات ائتمان. سجّل الآن.",
]

# Brand campaigns benefit from pinning the brand-keyword variants to
# Position 1 so they're always shown when the exact brand term is searched.
# This is the brand-only exception to the "minimal pinning" rule.
PIN_TO_POS1 = {
    "نظام قيود المحاسبي",
    "برنامج قيود المحاسبي",
    "منصة قيود الكاملة",
    "برنامج قيود لإدارة منشأتك",
}

# Validate
for h in HEADLINES:
    assert len(h) <= 30, f"HL too long ({len(h)}): {h}"
for d in DESCRIPTIONS:
    assert len(d) <= 90, f"DSC too long ({len(d)}): {d}"
print(f"✓ Validated {len(HEADLINES)} headlines, {len(DESCRIPTIONS)} descriptions")

client = get_client()
svc = client.get_service("AdGroupAdService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


op = client.get_type("AdGroupAdOperation")
aga = op.create
aga.ad_group = f"customers/{ACCT}/adGroups/{AG_ID}"
aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
aga.ad.final_urls.append("https://www.qoyod.com/")  # brand → main site
for h in HEADLINES:
    ah = client.get_type("AdTextAsset"); ah.text = h
    # Pin 4 brand-keyword headlines to Position 1 so any brand search shows
    # the exact-match variant in the top headline slot
    if h in PIN_TO_POS1:
        ah.pinned_field = client.enums.ServedAssetFieldTypeEnum.HEADLINE_1
    aga.ad.responsive_search_ad.headlines.append(ah)
for d in DESCRIPTIONS:
    ad = client.get_type("AdTextAsset"); ad.text = d
    aga.ad.responsive_search_ad.descriptions.append(ad)
aga.ad.responsive_search_ad.path1 = "قيود"
aga.ad.responsive_search_ad.path2 = "محاسبة"

try:
    r = svc.mutate_ad_group_ads(customer_id=ACCT, operations=[op])
    print(f"\n✅ RSA created: {r.results[0].resource_name}")
    print(f"   {len(HEADLINES)} headlines (4 pinned to Pos 1) + {len(DESCRIPTIONS)} descriptions")
    print(f"   final URL: https://www.qoyod.com/")
    print(f"   pinned headlines (always shown in slot 1, rotates among them):")
    for h in PIN_TO_POS1:
        print(f"     - {h}")
except Exception as e:
    print(f"\n❌ {_err(e)}")
