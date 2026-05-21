"""Retry EN RSAs only — descriptions trimmed to ≤90 chars."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

FINAL_URL = "https://lp.qoyod.com/qawaem/"

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

# All ≤90 chars
EN_DESCRIPTIONS = [
    "File Saudi financial statements on Qawaem with one click. XBRL export built in.",  # 79
    "Balance sheet, income statement, cash flow — auto-built and Decision 236 ready.",   # 80
    "Trusted by Saudi businesses for compliance filing. Start your 14-day free trial.",  # 81
    "Avoid Decision 236 fines. Direct Qawaem integration in minutes. No card needed.",   # 80
]

TARGETS = [
    ("1513020554", "199721186547", "Acc 1 FinancialSt_EN"),
    ("5753494964", "205172571548", "Acc 2 FinancialSt_EN_Auto"),
]

# Sanity-check
for d in EN_DESCRIPTIONS:
    assert len(d) <= 90, f"DSC {len(d)} chars: {d}"
for h in EN_HEADLINES:
    assert len(h) <= 30, f"HL {len(h)} chars: {h}"
print(f"✓ Validated: {len(EN_HEADLINES)} headlines, {len(EN_DESCRIPTIONS)} descriptions")

client = get_client()
svc = client.get_service("AdGroupAdService")


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, ag_id, label in TARGETS:
    print(f"\n=== {label} ===")
    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.ad_group = f"customers/{acct}/adGroups/{ag_id}"
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad.final_urls.append(FINAL_URL)
    for h in EN_HEADLINES:
        ah = client.get_type("AdTextAsset"); ah.text = h
        aga.ad.responsive_search_ad.headlines.append(ah)
    for d in EN_DESCRIPTIONS:
        ad = client.get_type("AdTextAsset"); ad.text = d
        aga.ad.responsive_search_ad.descriptions.append(ad)
    aga.ad.responsive_search_ad.path1 = "qawaem"
    aga.ad.responsive_search_ad.path2 = "filing"
    try:
        r = svc.mutate_ad_group_ads(customer_id=acct, operations=[op])
        print(f"  ✅ RSA: {r.results[0].resource_name}")
    except Exception as e:
        print(f"  ❌ {_err(e)}")
