"""Create Campaign 3 — ZATCA × Competitor conquesting.

Bids on competitor brand × ZATCA crossover queries (Daftra ZATCA, Wafeq Phase 2,
Rewaa فاتورة, Qoyod vs Daftra). Campaign name MUST contain `Competitor` so the
keyword policy in executors/keyword_policy.py permits competitor brand terms.

Created PAUSED. Same LP, same Phase-2 messaging, lower budget (conquesting is
narrower), slightly higher tCPA (these clicks cost more).
"""
import os
import sys
from pprint import pprint

os.environ["FORCE_LAUNCH"] = "1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import create_full_campaign

ACCOUNT_ID  = "1513020554"
LANDING_URL = "https://lp.qoyod.com/einvoice-integration/"

PRODUCT = "ZATCACompetitor"   # → name contains "Competitor" → competitor terms allowed

KEYWORDS = [
    # EXACT — competitor brand × ZATCA crossover (high-intent comparison)
    {"text": "دفترة فاتورة الكترونية",              "match_type": "EXACT"},
    {"text": "وافق المرحلة الثانية",                 "match_type": "EXACT"},
    {"text": "ريوي فاتورة الكترونية",               "match_type": "EXACT"},
    {"text": "بديل دفترة معتمد",                     "match_type": "EXACT"},
    {"text": "Daftra ZATCA integration",             "match_type": "EXACT"},
    {"text": "Wafeq Phase 2",                        "match_type": "EXACT"},
    # PHRASE — broader comparison + alternative-to queries
    {"text": "مقارنة قيود ودفترة",                   "match_type": "PHRASE"},
    {"text": "مقارنة قيود ووافق",                    "match_type": "PHRASE"},
    {"text": "بديل وافق",                            "match_type": "PHRASE"},
    {"text": "بديل دفترة",                           "match_type": "PHRASE"},
    {"text": "Qoyod vs Daftra",                      "match_type": "PHRASE"},
    {"text": "Qoyod vs Wafeq",                       "match_type": "PHRASE"},
    {"text": "Daftra vs Qoyod",                      "match_type": "PHRASE"},
    {"text": "Wafeq vs Qoyod",                       "match_type": "PHRASE"},
    {"text": "Rewaa ZATCA",                          "match_type": "PHRASE"},
    {"text": "Zoho ZATCA Saudi",                     "match_type": "PHRASE"},
]

NEGATIVES = [
    # Informational / how-to seekers
    {"text": "كيف",                       "match_type": "BROAD"},
    {"text": "ما هي",                     "match_type": "BROAD"},
    {"text": "ما هو",                     "match_type": "BROAD"},
    {"text": "شرح",                       "match_type": "BROAD"},
    {"text": "what is",                   "match_type": "PHRASE"},
    {"text": "how to",                    "match_type": "PHRASE"},
    {"text": "tutorial",                  "match_type": "PHRASE"},
    # Review-readers, not buyers (but keep "vs" — that IS the buyer query)
    {"text": "review",                    "match_type": "PHRASE"},
    {"text": "مراجعة",                    "match_type": "PHRASE"},
    # Always-negative belt-and-braces
    {"text": "free download",             "match_type": "PHRASE"},
    {"text": "تحميل مجاني",               "match_type": "PHRASE"},
    {"text": "course",                    "match_type": "PHRASE"},
    {"text": "training",                  "match_type": "PHRASE"},
    {"text": "دورة",                      "match_type": "BROAD"},
    {"text": "كورس",                      "match_type": "BROAD"},
    {"text": "وظيفة",                     "match_type": "BROAD"},
    {"text": "github",                    "match_type": "PHRASE"},
    {"text": "open source",               "match_type": "PHRASE"},
]

HEADLINES = [
    "البديل المعتمد لدفترة ووافق",
    "Qoyod مقابل المنافسين",
    "متوافق ZATCA - أفضل من دفترة",
    "لماذا تنتقل الشركات إلينا",
    "ربط المرحلة الثانية في دقائق",
    "دعم عربي 24/7 - محلي",
    "50,000+ شركة سعودية اختارتنا",
    "تجربة مجانية 14 يوماً",
    "بدون بطاقة ائتمانية",
    "ضمان الامتثال أو استرداد",
    "REST API + XML + PDF/A-3",
    "Qoyod - الحل الأول للسعودية",
]

DESCRIPTIONS = [
    "تبحث عن بديل لدفترة أو وافق؟ Qoyod معتمد من هيئة الزكاة، سعودي بالكامل، أسرع تكامل.",
    "قارن قيود بالمنافسين: دعم عربي 24/7، تكامل أسهل، خدمة محلية. ابدأ مجاناً اليوم.",
    "أكثر من 50,000 شركة سعودية انتقلت إلى Qoyod. تجربة 14 يوم بدون بطاقة. اكتشف لماذا.",
    "الموجة 24 تنتهي 30 يونيو 2026. تكامل أسهل وأسرع من أي منافس - أو نسترد رسومك.",
]


def main():
    print("=" * 78)
    print("CAMPAIGN 3 — Google_Search_AR_ZATCACompetitor_Broad")
    print("=" * 78)
    print(f"  Account:       {ACCOUNT_ID}")
    print(f"  Bidding:       TARGET_CPA $110")
    print(f"  Daily budget:  $25")
    print(f"  Landing URL:   {LANDING_URL}")
    print(f"  Keywords:      {len(KEYWORDS)} "
          f"({sum(1 for k in KEYWORDS if k['match_type']=='EXACT')} EXACT, "
          f"{sum(1 for k in KEYWORDS if k['match_type']=='PHRASE')} PHRASE)")
    print(f"  Negatives:     {len(NEGATIVES)}")
    print(f"  Headlines:     {len(HEADLINES)} / 15 max")
    print(f"  Descriptions:  {len(DESCRIPTIONS)} / 4 max")
    print()

    result = create_full_campaign(
        product             = PRODUCT,
        campaign_type       = "Search",
        language            = "AR",
        audience_type       = "Broad",
        daily_budget_usd    = 25.0,
        landing_url         = LANDING_URL,
        headlines           = HEADLINES,
        descriptions        = DESCRIPTIONS,
        keywords            = KEYWORDS,
        negative_keywords   = NEGATIVES,
        bidding_strategy    = "TARGET_CPA",
        target_cpa_usd      = 110.0,
        cpc_bid_usd         = 4.0,
        advertising_channel = "SEARCH",
        customer_id         = ACCOUNT_ID,
    )
    print("\nRESULT:")
    pprint(result)
    return result


if __name__ == "__main__":
    main()
