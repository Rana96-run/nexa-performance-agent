"""Add BROAD variants of 2 head terms to both AR ad groups.
EXACT versions stay (high-intent literal); BROAD versions added for
Smart Bidding to discover variations.

Acc 1 AR: 25 → 27 keywords
Acc 2 AR: 28 → 30 keywords (at cap)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client
from google.ads.googleads.errors import GoogleAdsException

TARGETS = [
    ("1513020554", "198301170444", "Acc 1 FinancialSt_AR"),
    ("5753494964", "197282810352", "Acc 2 FinancialSt_AR_Auto"),
]
# Head terms get BROAD added. Existing EXACT stays for high-intent.
BROAD_KEYWORDS = [
    "منصة قوائم",     # 3,600/mo — Google AI matches variations
    "قائمة الدخل",    # 1,600/mo — broadens to ميزانية, قائمة الدخل الشامل, etc.
]

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, ag_id, label in TARGETS:
    print(f"\n=== {label} ===")
    svc = client.get_service("AdGroupCriterionService")
    for kw in BROAD_KEYWORDS:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = f"customers/{acct}/adGroups/{ag_id}"
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = kw
        c.keyword.match_type = client.enums.KeywordMatchTypeEnum.BROAD
        try:
            svc.mutate_ad_group_criteria(customer_id=acct, operations=[op])
            print(f"  ✅ BROAD: {kw}")
        except Exception as e:
            print(f"  ❌ BROAD: {kw} — {_err(e)[:150]}")
