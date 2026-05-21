"""Keyword-only retry of Path A — RSAs were created on first run; this only
adds the 12 keywords to both AR ad groups."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "198301170444", "FinancialSt_AR (Acc 1)"),
    ("5753494964", "197282810352", "FinancialSt_AR_Auto (Acc 2)"),
]

NEW_KEYWORDS = [
    ("منصة قوائم",                              "EXACT"),
    ("قائمة الدخل",                             "EXACT"),
    ("قوائم وزارة التجارة",                     "EXACT"),
    ("إيداع القوائم المالية",                   "EXACT"),
    ("ايداع القوائم المالية للشركات",           "EXACT"),
    ("وزارة التجارة قوائم",                     "EXACT"),
    ("xbrl",                                    "EXACT"),
    ("الاستعلام عن ايداع القوائم المالية",      "PHRASE"),
    ("الاستفسار عن ايداع القوائم المالية",      "PHRASE"),
    ("التحقق من ايداع القوائم المالية",         "PHRASE"),
    ("الاستفسار عن حالة ايداع القوائم المالية", "PHRASE"),
    ("برنامج قوائم وزارة التجارة",              "PHRASE"),
]

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message}" for er in e.failure.errors)
    return str(e)[:200]


for acct, ag_id, label in TARGETS:
    print(f"\n=== {label} ===")
    svc = client.get_service("AdGroupCriterionService")
    ag_rn = f"customers/{acct}/adGroups/{ag_id}"

    ok, dup, err = 0, 0, 0
    for text, match in NEW_KEYWORDS:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ag_rn
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = text
        c.keyword.match_type = getattr(client.enums.KeywordMatchTypeEnum, match)
        try:
            svc.mutate_ad_group_criteria(customer_id=acct, operations=[op])
            ok += 1
            print(f"  ✅ [{match:<6}] {text}")
        except Exception as e:
            msg = _err(e)
            if "DUPLICATE" in msg or "duplicate" in msg or "already" in msg.lower():
                dup += 1
                print(f"  ⊘ [{match:<6}] {text} (already exists)")
            else:
                err += 1
                print(f"  ❌ [{match:<6}] {text}: {msg[:150]}")
    print(f"\n  → added={ok} dup={dup} err={err}")

print("\nDONE")
