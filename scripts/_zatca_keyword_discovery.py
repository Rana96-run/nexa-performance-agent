"""Pull live keyword ideas (avg monthly searches + competition) from Google
Ads Keyword Planner for each of the 3 ZATCA campaigns, in AR + EN separately.
Filter for high-volume + low/medium competition. Propose the AR/EN ad-group
split as JSON so we can review before executing structure changes."""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import keyword_ideas

ACCOUNT = "1513020554"
LP_URL  = "https://lp.qoyod.com/einvoice-integration/"

# Seeds = current keywords (split into AR + EN by script detection)
CAMPAIGNS = {
    "C1_ZATCAPhase2": {
        "ar_seeds": [
            "ربط المرحلة الثانية للفاتورة الإلكترونية",
            "الربط مع هيئة الزكاة",
            "ربط الفاتورة الإلكترونية",
            "المرحلة الثانية للفاتورة الإلكترونية",
            "تكامل المرحلة الثانية",
            "ربط منصة فاتورة",
            "برنامج الفاتورة الإلكترونية",
            "نظام فوترة إلكترونية",
        ],
        "en_seeds": [
            "ZATCA Phase 2",
            "ZATCA integration",
            "fatoora portal",
            "fatoora platform",
            "ZATCA e-invoicing",
        ],
    },
    "C2_ZATCAVendorShop": {
        "ar_seeds": [
            "البرامج المحاسبية المعتمدة من هيئة الزكاة",
            "أفضل برنامج فاتورة إلكترونية",
            "شركات الفاتورة الإلكترونية المعتمدة",
            "أفضل برنامج محاسبة في السعودية",
            "برنامج فاتورة إلكترونية معتمد",
            "أفضل برنامج فاتورة",
            "أفضل برنامج محاسبة",
            "مقارنة برامج الفاتورة",
            "مقارنة برامج المحاسبة",
            "برنامج محاسبة سعودي",
            "نظام محاسبة معتمد",
        ],
        "en_seeds": [
            "ZATCA approved software",
            "best e-invoice software saudi",
            "best accounting software saudi",
            "ZATCA certified",
        ],
    },
    "C3_ZATCACompetitor": {
        "ar_seeds": [
            "دفترة فاتورة الكترونية",
            "وافق المرحلة الثانية",
            "ريوي فاتورة الكترونية",
            "بديل دفترة معتمد",
            "مقارنة قيود ودفترة",
            "مقارنة قيود ووافق",
            "بديل وافق",
            "بديل دفترة",
        ],
        "en_seeds": [
            "Daftra ZATCA integration",
            "Wafeq Phase 2",
            "Qoyod vs Daftra",
            "Qoyod vs Wafeq",
            "Rewaa ZATCA",
            "Zoho ZATCA Saudi",
        ],
    },
}

# Quality thresholds
AR_MIN_VOL = 100   # AR queries in KSA: 100+/month is meaningful
EN_MIN_VOL = 30    # EN queries in KSA: smaller universe
MAX_KEEP   = 15    # top N per ad group


def fetch(seeds, language, label):
    print(f"\n  Pulling {label} ideas ({len(seeds)} seeds, language={language}) ...")
    try:
        ideas = keyword_ideas(seed_keywords=seeds, seed_url=LP_URL,
                              language=language, customer_id=ACCOUNT)
    except Exception as e:
        print(f"    ❌ {str(e)[:200]}")
        return []
    # Quality filter
    min_vol = AR_MIN_VOL if language == "ar" else EN_MIN_VOL
    filtered = [i for i in ideas
                if i["avg_monthly"] >= min_vol
                and i["competition"] in ("LOW", "MEDIUM")
                and len(i["keyword"]) <= 80]
    return filtered[:MAX_KEEP]


def main():
    proposal = {}
    for camp, cfg in CAMPAIGNS.items():
        print(f"\n========== {camp} ==========")
        ar = fetch(cfg["ar_seeds"], "ar", "AR")
        en = fetch(cfg["en_seeds"], "en", "EN")
        proposal[camp] = {"ar": ar, "en": en}

        print(f"\n  TOP {len(ar)} AR (filtered: vol≥{AR_MIN_VOL}, comp≤MED):")
        for i in ar[:12]:
            print(f"    {i['avg_monthly']:>6}/mo  {i['competition']:<6}  ${i['low_cpc_usd']:.2f}-{i['high_cpc_usd']:.2f}  {i['keyword']}")
        print(f"\n  TOP {len(en)} EN (filtered: vol≥{EN_MIN_VOL}, comp≤MED):")
        for i in en[:12]:
            print(f"    {i['avg_monthly']:>6}/mo  {i['competition']:<6}  ${i['low_cpc_usd']:.2f}-{i['high_cpc_usd']:.2f}  {i['keyword']}")

    # Save proposal
    out_path = "scripts/_zatca_keyword_proposal.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ proposal saved → {out_path}")


if __name__ == "__main__":
    main()
