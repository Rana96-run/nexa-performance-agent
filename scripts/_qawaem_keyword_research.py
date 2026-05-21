"""Pull high-volume Qawaem / Financial Statement related keyword ideas.
Two passes: seeds (Arabic) + URL (lp.qoyod.com/qawaem/) for page-based ideas.

Filters out: ALWAYS_NEGATIVE patterns (login/job/تحميل/etc.), competitor
brand names that don't belong here (foodics/daftra), and brand-only
(قيود/qoyod) per CRITICAL_KPI_RULES.

# KPI-RULE-BYPASS — keyword discovery, not SQL-leads analysis.
"""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import keyword_ideas
from executors.keyword_policy import classify_term

ACCOUNT = "1513020554"   # use Acc 1 cust for KP request (any active works)

AR_SEEDS = [
    "قرار 236",
    "إيداع القوائم المالية",
    "غرامة عدم إيداع",
    "منصة قوائم",
    "وزارة التجارة قوائم",
    "تقرير مالي",
    "ميزانية عمومية",
    "قائمة الدخل",
    "تدفقات نقدية",
    "تدقيق حسابات",
    "محاسب قانوني",
    "XBRL",
]
EN_SEEDS = [
    "saudi financial statements filing",
    "qawaem deposit",
    "decision 236 saudi",
    "balance sheet template",
    "annual financial report ksa",
]

print("=" * 78)
print("PASS 1 — Arabic seeds + URL seed (lp.qoyod.com/qawaem/)")
print("=" * 78)
ar_ideas = keyword_ideas(
    seed_keywords=AR_SEEDS,
    seed_url="https://lp.qoyod.com/qawaem/",
    language="ar",
    customer_id=ACCOUNT,
)
print(f"  → {len(ar_ideas)} AR ideas")

print("\n" + "=" * 78)
print("PASS 2 — English seeds")
print("=" * 78)
en_ideas = keyword_ideas(
    seed_keywords=EN_SEEDS,
    language="en",
    customer_id=ACCOUNT,
)
print(f"  → {len(en_ideas)} EN ideas")

# Filter
def keep(idea, lang):
    kw = idea["keyword"].lower()
    if idea["avg_monthly"] < 50: return False
    bucket = classify_term(idea["keyword"], "Google_Search_AREN_FinancialStatement")
    if bucket in ("ALWAYS_NEGATIVE", "BRAND_ONLY", "COMPETITOR"):
        return False
    return True

ar_kept = [i for i in ar_ideas if keep(i, "ar")][:30]
en_kept = [i for i in en_ideas if keep(i, "en")][:15]

print("\n" + "=" * 78)
print(f"TOP AR IDEAS — {len(ar_kept)} kept (vol ≥50, not always-neg/brand/competitor)")
print("=" * 78)
print(f"  {'keyword':<45} {'vol/mo':>8}  {'comp':<8}  {'low–high $':<14}")
for i in ar_kept:
    print(f"  {i['keyword'][:43]:<45} {i['avg_monthly']:>8,}  "
          f"{i['competition'][:7]:<8}  ${i['low_cpc_usd']:.2f}–${i['high_cpc_usd']:.2f}")

print("\n" + "=" * 78)
print(f"TOP EN IDEAS — {len(en_kept)} kept")
print("=" * 78)
print(f"  {'keyword':<45} {'vol/mo':>8}  {'comp':<8}  {'low–high $':<14}")
for i in en_kept:
    print(f"  {i['keyword'][:43]:<45} {i['avg_monthly']:>8,}  "
          f"{i['competition'][:7]:<8}  ${i['low_cpc_usd']:.2f}–${i['high_cpc_usd']:.2f}")

with open("scripts/_qawaem_kw_proposals.json", "w", encoding="utf-8") as f:
    json.dump({"ar": ar_kept, "en": en_kept}, f, ensure_ascii=False, indent=2)
print(f"\n✅ saved scripts/_qawaem_kw_proposals.json")
