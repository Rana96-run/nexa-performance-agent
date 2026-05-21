"""Path A execution: add 12 high-volume AR keywords + 1 platform-themed RSA
to FinancialSt_AR ad groups on both accounts.

Final URL: https://lp.qoyod.com/qawaem/
UTM inherits Acc-level customer template.

# KPI-RULE-BYPASS — keyword/RSA add, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

# (account, campaign_id, ad_group_id, ad_group_name)
TARGETS = [
    ("1513020554", "23861837000", "198301170444", "FinancialSt_AR (Acc 1)"),
    ("5753494964", "23870151040", "197282810352", "FinancialSt_AR_Auto (Acc 2)"),
]

# 12 high-volume keywords from research (vol ≥50, LOW comp, buying intent)
NEW_KEYWORDS = [
    # EXACT — head terms, highest intent
    ("[منصة قوائم]",                              "EXACT"),
    ("[قائمة الدخل]",                             "EXACT"),
    ("[قوائم وزارة التجارة]",                     "EXACT"),
    ("[إيداع القوائم المالية]",                   "EXACT"),
    ("[ايداع القوائم المالية للشركات]",           "EXACT"),
    ("[وزارة التجارة قوائم]",                     "EXACT"),
    ("[xbrl]",                                    "EXACT"),
    # PHRASE — inquiry variations
    ('"الاستعلام عن ايداع القوائم المالية"',      "PHRASE"),
    ('"الاستفسار عن ايداع القوائم المالية"',      "PHRASE"),
    ('"التحقق من ايداع القوائم المالية"',         "PHRASE"),
    ('"الاستفسار عن حالة ايداع القوائم المالية"', "PHRASE"),
    ('"برنامج قوائم وزارة التجارة"',              "PHRASE"),
]
# Strip the [...] / "..." brackets — they're already encoded in match_type
def _clean(t):
    t = t.strip()
    if (t.startswith("[") and t.endswith("]")) or \
       (t.startswith('"') and t.endswith('"')):
        return t[1:-1]
    return t

# New platform-themed RSA — 9 headlines (≤30 chars each) + 3 descriptions (≤90)
RSA_HEADLINES = [
    "ربط مباشر مع منصة قوائم",
    "صدّر قائمة الدخل بـ XBRL",
    "قوائم وزارة التجارة",
    "إيداع القوائم في دقائق",
    "متوافق مع قرار 236",
    "قيود — برنامج المحاسبة",
    "تجربة 14 يوم مجاناً",
    "آلاف الشركات السعودية",
    "دعم عربي 24/7",
]
RSA_DESCRIPTIONS = [
    "صدّر قائمة الدخل والميزانية العمومية بصيغة XBRL وأودعها مباشرة على منصة قوائم.",
    "حلول إيداع القوائم المالية المتوافقة مع قرار وزاري 236. ابدأ التجربة المجانية.",
    "آلاف الشركات السعودية تثق بقيود لإدارة محاسبتها وإيداع قوائمها المالية. جرّب الآن.",
]
RSA_PATH1 = "قوائم"
RSA_PATH2 = "ايداع"
RSA_FINAL_URL = "https://lp.qoyod.com/qawaem/"


client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message}" for er in e.failure.errors)
    return str(e)[:300]


for acct, cid, ag_id, label in TARGETS:
    print(f"\n{'=' * 72}")
    print(f"{label}")
    print('=' * 72)

    ag_rn = f"customers/{acct}/adGroups/{ag_id}"

    # 1. Add 12 keywords
    svc_kw = client.get_service("AdGroupCriterionService")
    ops = []
    for text, match in NEW_KEYWORDS:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ag_rn
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = _clean(text)
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
        ops.append(op)

    # Try as a batch first; on failure fall back to per-keyword to isolate
    try:
        r = svc_kw.mutate_ad_group_criteria(customer_id=acct, operations=ops)
        print(f"\n1. Keywords: {len(r.results)}/{len(NEW_KEYWORDS)} added (batch)")
    except Exception as e:
        print(f"\n1. ⚠ Batch failed ({_err(e)[:120]}) — retrying one-by-one")
        ok = 0
        for op in ops:
            try:
                svc_kw.mutate_ad_group_criteria(customer_id=acct, operations=[op])
                ok += 1
                print(f"   ✅ {op.create.keyword.text}")
            except Exception as e1:
                print(f"   ❌ {op.create.keyword.text}: {_err(e1)[:150]}")
        print(f"\n   total kw added: {ok}/{len(NEW_KEYWORDS)}")

    # 2. Add new RSA
    svc_ad = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.ad_group = ag_rn
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(RSA_FINAL_URL)
    for h in RSA_HEADLINES:
        ah = client.get_type("AdTextAsset")
        ah.text = h
        aga.ad.responsive_search_ad.headlines.append(ah)
    for d in RSA_DESCRIPTIONS:
        ad = client.get_type("AdTextAsset")
        ad.text = d
        aga.ad.responsive_search_ad.descriptions.append(ad)
    aga.ad.responsive_search_ad.path1 = RSA_PATH1
    aga.ad.responsive_search_ad.path2 = RSA_PATH2
    try:
        r = svc_ad.mutate_ad_group_ads(customer_id=acct, operations=[op])
        print(f"\n2. ✅ Platform-themed RSA created: {r.results[0].resource_name}")
    except Exception as e:
        print(f"\n2. ❌ RSA create: {_err(e)}")

print(f"\n{'=' * 72}")
print("DONE — Path A applied to both accounts.")
print("Watch impression_share + clicks over next 48-72h; QS will populate ~50 imp.")
print('=' * 72)
