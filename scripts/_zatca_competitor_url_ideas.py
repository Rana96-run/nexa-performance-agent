"""Free competitor research fallback — use Keyword Planner with competitor
URLs as seeds to extract what queries those domains rank for in Saudi.

This is the closest API-accessible substitute for Semrush's "domain paid
keywords" report when Semrush credits are out.

Strategy: feed each competitor LP into url_seed; Google's Keyword Planner
returns ideas based on the URL's content + ranking history.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import keyword_ideas

ACCOUNT = "1513020554"

# Competitor URLs — homepage + e-invoice-specific pages where they exist
COMPETITOR_URLS = {
    "Wafeq":  ["https://wafeq.com/", "https://wafeq.com/sa/e-invoicing"],
    "Daftra": ["https://www.daftra.com/sa/", "https://www.daftra.com/sa/e-invoice"],
    "Rewaa":  ["https://www.rewaa.com/", "https://www.rewaa.com/zatca-phase-2"],
    "Zoho":   ["https://www.zoho.com/sa/books/zatca-e-invoicing/"],
}

# Quality filters
AR_MIN_VOL = 50    # lower than before — we want broader competitor insight
EN_MIN_VOL = 30
MAX_PER_URL = 30


def fetch(url, language, label):
    print(f"\n  → {label} (url={url}, lang={language})")
    try:
        ideas = keyword_ideas(seed_keywords=[], seed_url=url,
                              language=language, customer_id=ACCOUNT)
    except Exception as e:
        msg = str(e)
        if "URL_NOT_REACHABLE" in msg or "NOT_REACHABLE" in msg:
            print(f"    URL not reachable by Keyword Planner")
        else:
            print(f"    ERROR: {msg[:200]}")
        return []
    min_vol = AR_MIN_VOL if language == "ar" else EN_MIN_VOL
    filtered = [i for i in ideas
                if i["avg_monthly"] >= min_vol
                and i["competition"] in ("LOW", "MEDIUM")
                and len(i["keyword"]) <= 80]
    return filtered[:MAX_PER_URL]


def main():
    print("=" * 78)
    print("COMPETITOR URL-SEEDED KEYWORD DISCOVERY (Keyword Planner)")
    print("=" * 78)

    seen_kw = set()      # dedupe across competitors
    by_lang = {"ar": [], "en": []}

    for comp, urls in COMPETITOR_URLS.items():
        print(f"\n========== {comp} ==========")
        for url in urls:
            for lang in ["ar", "en"]:
                ideas = fetch(url, lang, f"{comp} {lang.upper()}")
                for idea in ideas:
                    kw = idea["keyword"].lower()
                    if kw in seen_kw: continue
                    seen_kw.add(kw)
                    idea["source"] = f"{comp} ({lang})"
                    by_lang[lang].append(idea)

    print("\n" + "=" * 78)
    print(f"TOP UNIQUE AR KEYWORDS  (vol ≥ {AR_MIN_VOL}, comp ≤ MED)")
    print("=" * 78)
    by_lang["ar"].sort(key=lambda x: x["avg_monthly"], reverse=True)
    for i in by_lang["ar"][:30]:
        print(f"  {i['avg_monthly']:>6}/mo  {i['competition']:<6}  ${i['low_cpc_usd']:.2f}-{i['high_cpc_usd']:.2f}  [{i['source']}]  {i['keyword']}")

    print("\n" + "=" * 78)
    print(f"TOP UNIQUE EN KEYWORDS  (vol ≥ {EN_MIN_VOL}, comp ≤ MED)")
    print("=" * 78)
    by_lang["en"].sort(key=lambda x: x["avg_monthly"], reverse=True)
    for i in by_lang["en"][:30]:
        print(f"  {i['avg_monthly']:>6}/mo  {i['competition']:<6}  ${i['low_cpc_usd']:.2f}-{i['high_cpc_usd']:.2f}  [{i['source']}]  {i['keyword']}")

    # Save full results
    import json
    out = "scripts/_zatca_competitor_url_ideas.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(by_lang, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ full results → {out}")


if __name__ == "__main__":
    main()
