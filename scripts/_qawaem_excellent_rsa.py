"""Create one EXCELLENT-strength RSA per ad group (AR + EN on both accounts).

Google grades Ad Strength on:
  • 11+ unique headlines (we use 15 — the max)
  • 4 descriptions (the max)
  • Headlines/descriptions that use the top-volume keywords for the ad group
  • Minimal pinning (none — full flexibility)
  • No duplicate phrasing

Char limits: headline ≤30, description ≤90.

# KPI-RULE-BYPASS — RSA creation, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

FINAL_URL = "https://lp.qoyod.com/qawaem/"

# Arabic — uses منصة قوائم (3.6k/mo), قائمة الدخل (1.6k), إيداع/استعلام cluster
AR_HEADLINES = [
    "منصة قوائم — ربط مباشر",       # uses منصة قوائم
    "إيداع القوائم المالية",         # uses إيداع
    "قائمة الدخل بـ XBRL",          # uses قائمة الدخل + XBRL
    "قوائم وزارة التجارة",           # exact match top kw
    "الاستعلام عن إيداع القوائم",    # inquiry cluster
    "متوافق مع قرار 236",            # decision compliance
    "تجنب غرامة قرار 236",           # penalty angle
    "ربط منصة قوائم في دقائق",       # speed
    "صدّر القوائم المالية تلقائياً", # automation
    "تجربة 14 يوم مجاناً",           # offer
    "قيود — برنامج المحاسبة",        # brand
    "آلاف الشركات السعودية",         # social proof
    "دعم عربي 24/7",                # support
    "ميزانية عمومية + قائمة دخل",    # uses قائمة الدخل
    "بدون بطاقة ائتمان",             # friction remover
]

AR_DESCRIPTIONS = [
    "أودع قوائمك المالية مباشرة على منصة قوائم. تصدير XBRL تلقائي. متوافق مع قرار 236.",
    "قائمة الدخل، الميزانية العمومية، التدفقات النقدية — جاهزة بصيغة XBRL للإيداع.",
    "تجنب غرامة قرار 236. ربط مباشر مع منصة قوائم وزارة التجارة في دقائق.",
    "آلاف الشركات السعودية تستخدم قيود. تجربة 14 يوم مجاناً، بدون بطاقة ائتمان.",
]

# English — fewer volume seeds, lean on Saudi-specific intent
EN_HEADLINES = [
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
    "Audit-Ready Reports",
    "Cash Flow Statement",
    "Income Statement Template",
]

EN_DESCRIPTIONS = [
    "File Saudi financial statements on the Qawaem platform with one click. XBRL export included.",
    "Balance sheet, income statement, cash flow — auto-generated and Decision 236 compliant.",
    "Trusted by Saudi businesses for accounting and compliance filing. Start the 14-day free trial.",
    "Avoid Decision 236 fines with direct Qawaem integration. Setup in minutes, no card required.",
]

# (account, ag_id, lang, label)
TARGETS = [
    ("1513020554", "198301170444", "ar", "Acc 1 FinancialSt_AR"),
    ("1513020554", None,           "en", "Acc 1 FinancialSt_EN"),
    ("5753494964", "197282810352", "ar", "Acc 2 FinancialSt_AR_Auto"),
    ("5753494964", None,           "en", "Acc 2 FinancialSt_EN_Auto"),
]

client = get_client()
ga = client.get_service("GoogleAdsService")
svc = client.get_service("AdGroupAdService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


def resolve_en_ag(account, camp_id):
    for r in ga.search(customer_id=account, query=f"""
        SELECT ad_group.id, ad_group.name FROM ad_group
        WHERE campaign.id = {camp_id} AND ad_group.name LIKE '%EN%'
    """):
        return str(r.ad_group.id), r.ad_group.name
    return None, None


# Resolve EN ad groups
ACC1_CID = "23861837000"
ACC2_CID = "23870151040"
ag_id1, name1 = resolve_en_ag("1513020554", ACC1_CID)
ag_id2, name2 = resolve_en_ag("5753494964", ACC2_CID)
print(f"Acc 1 EN ad group: {name1} ({ag_id1})")
print(f"Acc 2 EN ad group: {name2} ({ag_id2})")

# Fill in EN ag ids
resolved = []
for acct, ag_id, lang, label in TARGETS:
    if ag_id is None:
        if acct == "1513020554": ag_id = ag_id1
        else:                    ag_id = ag_id2
    resolved.append((acct, ag_id, lang, label))


# Validate char counts before sending (Google rejects >30/90)
def validate(headlines, descs):
    bad = []
    for h in headlines:
        if len(h) > 30: bad.append(f"HL too long ({len(h)}): {h}")
    for d in descs:
        if len(d) > 90: bad.append(f"DSC too long ({len(d)}): {d}")
    return bad

for label, hl, ds in [("AR", AR_HEADLINES, AR_DESCRIPTIONS),
                      ("EN", EN_HEADLINES, EN_DESCRIPTIONS)]:
    issues = validate(hl, ds)
    if issues:
        print(f"\n⚠ {label} validation issues:")
        for i in issues: print(f"  {i}")
    else:
        print(f"✓ {label} all under limits ({len(hl)} headlines, {len(ds)} descriptions)")


# Create one RSA per ad group
for acct, ag_id, lang, label in resolved:
    print(f"\n{'=' * 72}")
    print(f"{label} (lang={lang})")
    print('=' * 72)
    if not ag_id:
        print(f"  ⚠ no ad group resolved; skipping")
        continue

    headlines = AR_HEADLINES if lang == "ar" else EN_HEADLINES
    descs     = AR_DESCRIPTIONS if lang == "ar" else EN_DESCRIPTIONS

    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.ad_group = f"customers/{acct}/adGroups/{ag_id}"
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(FINAL_URL)
    for h in headlines:
        ah = client.get_type("AdTextAsset")
        ah.text = h
        aga.ad.responsive_search_ad.headlines.append(ah)
    for d in descs:
        ad = client.get_type("AdTextAsset")
        ad.text = d
        aga.ad.responsive_search_ad.descriptions.append(ad)
    aga.ad.responsive_search_ad.path1 = "قوائم" if lang == "ar" else "qawaem"
    aga.ad.responsive_search_ad.path2 = "ايداع" if lang == "ar" else "filing"

    try:
        r = svc.mutate_ad_group_ads(customer_id=acct, operations=[op])
        print(f"  ✅ RSA created: {r.results[0].resource_name}")
        print(f"     {len(headlines)} headlines + {len(descs)} descriptions → expected EXCELLENT")
    except Exception as e:
        print(f"  ❌ {_err(e)}")

print("\nDONE — check Ad Strength column in UI; should read 'Excellent'.")
