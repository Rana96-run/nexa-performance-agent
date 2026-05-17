"""Create the 2 E-Invoice / ZATCA Phase 2 campaigns in Google Ads
Account 1 (1513020554), per the May 2026 ZATCA strategy.

Campaigns created in PAUSED state. After creation:
  1. Team reviews each in Google Ads UI
  2. Adds sitelinks / callouts / structured snippets (manual, ~5 min/campaign)
  3. Verifies location targeting = Saudi Arabia only
  4. Verifies language = Arabic + English (for ZATCA Phase 2 English terms)
  5. Enables when satisfied

CLAUDE.md compliance:
- User gave explicit in-chat approval to create
- launch_policy 7d cooldown bypassed via FORCE_LAUNCH=1 (user-approved override)
- Campaigns start PAUSED — no spend until team enables
"""
import os
import sys
from pprint import pprint

# Force-bypass launch_policy cooldown — user explicitly approved
os.environ["FORCE_LAUNCH"] = "1"

# Force utf-8 stdout for Arabic
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import create_full_campaign

ACCOUNT_ID = "1513020554"   # Account 1 — better performer per analysis
LANDING_URL = "https://lp.qoyod.com/einvoice-integration/"


# ──────────────────────────────────────────────────────────────────────────
# CAMPAIGN 1 — Phase 2 Integration (direct buyer intent)
# ──────────────────────────────────────────────────────────────────────────
CAMPAIGN_1_NAME_PARTS = {
    "campaign_type": "Search",
    "language":      "AR",
    "product":       "ZATCAPhase2",   # explicit — avoids E-Invoice→Invoice normalization
    "audience_type": "Broad",
}

CAMPAIGN_1_KEYWORDS = [
    # EXACT — proven high-intent Phase 2 buyer terms (from our BQ data)
    {"text": "ربط المرحلة الثانية للفاتورة الإلكترونية", "match_type": "EXACT"},
    {"text": "الربط مع هيئة الزكاة",                      "match_type": "EXACT"},
    {"text": "ربط الفاتورة الإلكترونية",                  "match_type": "EXACT"},
    {"text": "المرحلة الثانية للفاتورة الإلكترونية",      "match_type": "EXACT"},
    {"text": "تكامل المرحلة الثانية",                     "match_type": "EXACT"},
    {"text": "ربط منصة فاتورة",                            "match_type": "EXACT"},
    # PHRASE — broader buyer variations
    {"text": "منصة فاتورة",                                "match_type": "PHRASE"},
    {"text": "ZATCA Phase 2",                              "match_type": "PHRASE"},
    {"text": "ZATCA integration",                          "match_type": "PHRASE"},
    {"text": "fatoora portal",                             "match_type": "PHRASE"},
    {"text": "fatoora platform",                           "match_type": "PHRASE"},
    {"text": "برنامج الفاتورة الإلكترونية",                "match_type": "PHRASE"},
    {"text": "نظام فوترة إلكترونية",                       "match_type": "PHRASE"},
    {"text": "ZATCA e-invoicing",                          "match_type": "PHRASE"},
]

CAMPAIGN_1_NEGATIVES = [
    # Research / informational intent — not buyers
    {"text": "استخراج رقم ضريبي",       "match_type": "PHRASE"},   # tax-number extractors, not buyers
    {"text": "فاتورة جاهزة للتعديل",    "match_type": "PHRASE"},   # editable invoice researchers
    {"text": "كيف",                       "match_type": "BROAD"},    # "how" — how-to seekers
    {"text": "ما هي",                     "match_type": "BROAD"},    # "what is" — researchers
    {"text": "ما هو",                     "match_type": "BROAD"},
    {"text": "متى",                       "match_type": "BROAD"},    # "when" — informational
    {"text": "أين",                       "match_type": "BROAD"},    # "where"
    {"text": "شرح",                       "match_type": "BROAD"},    # "explain"
    {"text": "دليل",                      "match_type": "BROAD"},    # "guide"
    {"text": "tutorial",                   "match_type": "PHRASE"},
    {"text": "explanation",                "match_type": "PHRASE"},
    {"text": "guide",                      "match_type": "PHRASE"},
    {"text": "what is",                    "match_type": "PHRASE"},
    {"text": "how to",                     "match_type": "PHRASE"},
    # ALWAYS_NEGATIVE patterns already handled by keyword_policy.py
    # (login, free, course, training, download, loan, job)
    # but let's belt-and-braces:
    {"text": "free download",              "match_type": "PHRASE"},
    {"text": "تحميل مجاني",                "match_type": "PHRASE"},
    {"text": "غرامة",                     "match_type": "BROAD"},    # fear searchers — separate campaign idea
    {"text": "مخالفة",                    "match_type": "BROAD"},
]

CAMPAIGN_1_HEADLINES = [
    "ZATCA المرحلة الثانية | متوافق",
    "ربط الفاتورة الإلكترونية بسهولة",
    "تكامل مع منصة فاتورة في دقائق",
    "معتمد من هيئة الزكاة والضريبة",
    "متوافق مع المرحلة الثانية",
    "REST API + XML + PDF/A-3",
    "أكثر من 50 ألف شركة سعودية",
    "تجربة مجانية 14 يوم",
    "بدون بطاقة ائتمانية",
    "متوافق في 7 أيام أو استرداد",
    "الموجة 24 - الموعد 30 يونيو 2026",
    "Qoyod - الحل المعتمد للسعودية",
]

CAMPAIGN_1_DESCRIPTIONS = [
    "اربط نظامك بمنصة فاتورة بسهولة. XML، PDF/A-3، REST API. معتمد من هيئة الزكاة.",
    "أكثر من 50,000 شركة سعودية تستخدم Qoyod. تجربة مجانية 14 يوماً. ابدأ الآن.",
    "الموجة 24 من المرحلة الثانية تنتهي 30 يونيو 2026. اربط نظامك في 7 أيام.",
    "خدمة عملاء عربية على مدار الساعة. متخصص في السوق السعودي. مرحلة أولى وثانية.",
]


# ──────────────────────────────────────────────────────────────────────────
# CAMPAIGN 2 — Vendor Discovery (buyers shopping comparison)
# ──────────────────────────────────────────────────────────────────────────
CAMPAIGN_2_NAME_PARTS = {
    "campaign_type": "Search",
    "language":      "AR",
    "product":       "E-Invoice",
    "audience_type": "Broad",  # Same audience token requirement
    # Differentiator: this name will need a suffix variant since same parts as #1
}

CAMPAIGN_2_KEYWORDS = [
    # EXACT — vendor shopping intent
    {"text": "البرامج المحاسبية المعتمدة من هيئة الزكاة", "match_type": "EXACT"},
    {"text": "أفضل برنامج فاتورة إلكترونية",              "match_type": "EXACT"},
    {"text": "شركات الفاتورة الإلكترونية المعتمدة",       "match_type": "EXACT"},
    {"text": "أفضل برنامج محاسبة في السعودية",            "match_type": "EXACT"},
    {"text": "برنامج فاتورة إلكترونية معتمد",              "match_type": "EXACT"},
    {"text": "ZATCA approved software",                    "match_type": "EXACT"},
    # PHRASE — broader comparison variations
    {"text": "أفضل برنامج فاتورة",                        "match_type": "PHRASE"},
    {"text": "أفضل برنامج محاسبة",                        "match_type": "PHRASE"},
    {"text": "مقارنة برامج الفاتورة",                     "match_type": "PHRASE"},
    {"text": "مقارنة برامج المحاسبة",                     "match_type": "PHRASE"},
    {"text": "best e-invoice software saudi",              "match_type": "PHRASE"},
    {"text": "best accounting software saudi",             "match_type": "PHRASE"},
    {"text": "ZATCA certified",                            "match_type": "PHRASE"},
    {"text": "برنامج محاسبة سعودي",                       "match_type": "PHRASE"},
    {"text": "نظام محاسبة معتمد",                          "match_type": "PHRASE"},
]

CAMPAIGN_2_NEGATIVES = [
    {"text": "كيف",                       "match_type": "BROAD"},
    {"text": "ما هي",                     "match_type": "BROAD"},
    {"text": "ما هو",                     "match_type": "BROAD"},
    {"text": "شرح",                       "match_type": "BROAD"},
    {"text": "what is",                   "match_type": "PHRASE"},
    {"text": "how to",                    "match_type": "PHRASE"},
    {"text": "tutorial",                  "match_type": "PHRASE"},
    {"text": "review",                    "match_type": "PHRASE"},   # review-readers, not buyers
    {"text": "مراجعة",                    "match_type": "PHRASE"},
    {"text": "free download",             "match_type": "PHRASE"},
    {"text": "تحميل مجاني",               "match_type": "PHRASE"},
    {"text": "vs free",                   "match_type": "PHRASE"},
    {"text": "open source",               "match_type": "PHRASE"},
    {"text": "github",                    "match_type": "PHRASE"},
    {"text": "course",                    "match_type": "PHRASE"},
    {"text": "training",                  "match_type": "PHRASE"},
    {"text": "دورة",                      "match_type": "BROAD"},
    {"text": "كورس",                      "match_type": "BROAD"},
]

CAMPAIGN_2_HEADLINES = [
    "أفضل برنامج فاتورة | 2026",
    "برنامج محاسبي معتمد من ZATCA",
    "مقارنة أفضل برامج الفوترة",
    "Qoyod - الحل الأول للسعودية",
    "متوافق مرحلة أولى وثانية",
    "أكثر من 50,000 شركة سعودية",
    "تجربة مجانية 14 يوماً",
    "دعم عربي 24/7",
    "تكامل سهل + خدمة سريعة",
    "خبراء سعوديون",
    "ضمان الامتثال أو استرداد",
    "ابدأ مجاناً | بدون بطاقة",
]

CAMPAIGN_2_DESCRIPTIONS = [
    "مقارنة أفضل برامج الفوترة الإلكترونية في السعودية. Qoyod: معتمد، سعودي، متخصص.",
    "اكتشف لماذا 50,000+ شركة سعودية اختارت Qoyod. تجربة مجانية كاملة. ابدأ الآن.",
    "ضمان الامتثال للمرحلة الثانية. تكامل في 7 أيام أو استرداد كامل للرسوم.",
    "الفرق بين Qoyod ومنافسيه: معتمد محلياً، عربي بالكامل، مدعوم على مدار الساعة.",
]


# ──────────────────────────────────────────────────────────────────────────
# EXECUTE
# ──────────────────────────────────────────────────────────────────────────

def create_campaign_1():
    print("=" * 78)
    print("CAMPAIGN 1 — Search_AR_E-Invoice_Broad — Phase 2 Integration")
    print("=" * 78)
    print(f"  Account:       {ACCOUNT_ID}")
    print(f"  Bidding:       TARGET_CPA $90")
    print(f"  Daily budget:  $50")
    print(f"  Landing URL:   {LANDING_URL}")
    print(f"  Keywords:      {len(CAMPAIGN_1_KEYWORDS)} ({sum(1 for k in CAMPAIGN_1_KEYWORDS if k['match_type']=='EXACT')} EXACT, "
          f"{sum(1 for k in CAMPAIGN_1_KEYWORDS if k['match_type']=='PHRASE')} PHRASE)")
    print(f"  Negatives:     {len(CAMPAIGN_1_NEGATIVES)}")
    print(f"  Headlines:     {len(CAMPAIGN_1_HEADLINES)} / 15 max")
    print(f"  Descriptions:  {len(CAMPAIGN_1_DESCRIPTIONS)} / 4 max")
    print()

    result = create_full_campaign(
        product             = CAMPAIGN_1_NAME_PARTS["product"],
        campaign_type       = CAMPAIGN_1_NAME_PARTS["campaign_type"],
        language            = CAMPAIGN_1_NAME_PARTS["language"],
        audience_type       = CAMPAIGN_1_NAME_PARTS["audience_type"],
        daily_budget_usd    = 50.0,
        landing_url         = LANDING_URL,
        headlines           = CAMPAIGN_1_HEADLINES,
        descriptions        = CAMPAIGN_1_DESCRIPTIONS,
        keywords            = CAMPAIGN_1_KEYWORDS,
        negative_keywords   = CAMPAIGN_1_NEGATIVES,
        bidding_strategy    = "TARGET_CPA",
        target_cpa_usd      = 90.0,
        cpc_bid_usd         = 3.0,    # initial keyword bid (overridden by tCPA)
        advertising_channel = "SEARCH",
        customer_id         = ACCOUNT_ID,
    )
    print()
    print("CAMPAIGN 1 RESULT:")
    pprint(result)
    return result


def create_campaign_2():
    print()
    print("=" * 78)
    print("CAMPAIGN 2 — Search_AR_E-Invoice_VendorDiscovery_Broad")
    print("=" * 78)
    print(f"  Account:       {ACCOUNT_ID}")
    print(f"  Bidding:       TARGET_CPA $100")
    print(f"  Daily budget:  $35")
    print(f"  Landing URL:   {LANDING_URL}")
    print(f"  Keywords:      {len(CAMPAIGN_2_KEYWORDS)}")
    print(f"  Negatives:     {len(CAMPAIGN_2_NEGATIVES)}")
    print(f"  Headlines:     {len(CAMPAIGN_2_HEADLINES)} / 15 max")
    print(f"  Descriptions:  {len(CAMPAIGN_2_DESCRIPTIONS)} / 4 max")
    print()

    result = create_full_campaign(
        product             = "ZATCAVendorShop",
        campaign_type       = CAMPAIGN_2_NAME_PARTS["campaign_type"],
        language            = CAMPAIGN_2_NAME_PARTS["language"],
        audience_type       = CAMPAIGN_2_NAME_PARTS["audience_type"],
        daily_budget_usd    = 35.0,
        landing_url         = LANDING_URL,
        headlines           = CAMPAIGN_2_HEADLINES,
        descriptions        = CAMPAIGN_2_DESCRIPTIONS,
        keywords            = CAMPAIGN_2_KEYWORDS,
        negative_keywords   = CAMPAIGN_2_NEGATIVES,
        bidding_strategy    = "TARGET_CPA",
        target_cpa_usd      = 100.0,
        cpc_bid_usd         = 3.5,
        advertising_channel = "SEARCH",
        customer_id         = ACCOUNT_ID,
    )
    print()
    print("CAMPAIGN 2 RESULT:")
    pprint(result)
    return result


if __name__ == "__main__":
    print("\n" + "█" * 78)
    print("█  CREATING 2 E-INVOICE / ZATCA PHASE 2 CAMPAIGNS — PAUSED STATE")
    print("█  Account 1 (1513020554) — better-performing of our 2 accounts")
    print("█  Force-bypassing 7d launch_policy cooldown via user-approved FORCE_LAUNCH")
    print("█" * 78 + "\n")

    r1 = create_campaign_1()
    r2 = create_campaign_2()

    print("\n" + "█" * 78)
    print("█  BOTH CAMPAIGNS CREATED IN PAUSED STATE")
    print("█" * 78)
    print()
    print("MANUAL STEPS REMAINING (Google Ads UI — ~10 min total):")
    print("  1. Open each campaign in Google Ads UI")
    print("  2. Verify location targeting = Saudi Arabia only")
    print("  3. Verify language targeting = Arabic + English")
    print("  4. Add Sitelink Extensions (4 minimum):")
    print("     - حاسبة موعد المرحلة الثانية → /einvoice-integration/#deadline")
    print("     - Qoyod مقابل Wafeq → (build comparison page first)")
    print("     - خطط الأسعار → /pricing")
    print("     - احجز مكالمة مع المبيعات → calendar booking link")
    print("  5. Add Callout Extensions (8):")
    print("     متوافق مع ZATCA · REST API · XML + PDF/A-3 · دعم 24/7 بالعربية ·")
    print("     بدون بطاقة ائتمان · تجربة 14 يوم · ربط في دقائق · آلاف الشركات السعودية")
    print("  6. Add Structured Snippet Extensions:")
    print("     - Header: Features → XML, PDF/A-3, REST API, QR Code, Encrypted Seal")
    print("  7. Add Call Extension with Saudi 800 number")
    print("  8. Review each RSA — ensure pinning isn't needed")
    print("  9. Enable campaigns when satisfied")
