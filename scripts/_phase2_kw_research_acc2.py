"""ZATCAPhase2 on Acc 2 — pull keyword ideas, compare to current set,
propose high-volume adds.

Campaign: Google_Search_AREN_ZATCAPhase2 on Acc 2 (5753494964 / 23865711095)
Topic: ZATCA Phase 2 e-invoice integration.

# KPI-RULE-BYPASS — keyword discovery, not SQL-leads analysis.
"""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import keyword_ideas, get_client
from executors.keyword_policy import classify_term

ACC2     = "5753494964"
CAMP_ID  = "23865711095"
CAMP_NAME = "Google_Search_AREN_ZATCAPhase2"

client = get_client()
ga = client.get_service("GoogleAdsService")

# 1. Pull current keywords on the campaign
print("=" * 78)
print("Current Acc 2 ZATCAPhase2 keywords (positive only)")
print("=" * 78)
current = set()
for r in ga.search(customer_id=ACC2, query=f"""
    SELECT ad_group_criterion.keyword.text,
           ad_group_criterion.keyword.match_type,
           ad_group.name
    FROM ad_group_criterion
    WHERE campaign.id = {CAMP_ID}
      AND ad_group_criterion.type = 'KEYWORD'
      AND ad_group_criterion.negative = FALSE
      AND ad_group_criterion.status != 'REMOVED'
"""):
    text = r.ad_group_criterion.keyword.text.lower()
    current.add(text)
    print(f"  [{r.ad_group_criterion.keyword.match_type.name:<6}] "
          f"{r.ad_group_criterion.keyword.text[:50]:<50} ({r.ad_group.name})")
print(f"\n  total current: {len(current)}")

# 2. Keyword ideas — use the LP + seeds
print("\n" + "=" * 78)
print("Keyword Planner — AR seeds + URL seed (lp.qoyod.com/einvoice-integration/)")
print("=" * 78)
AR_SEEDS = [
    "زاتكا المرحلة الثانية",
    "فاتورة إلكترونية",
    "ZATCA Phase 2",
    "فاتورة الكترونية",
    "ربط زاتكا",
    "فوترة إلكترونية",
    "ZATCA integration",
    "e-invoice Saudi",
    "ZATCA portal",
    "XML invoice",
    "QR code invoice",
    "PDF/A-3",
]
ideas = keyword_ideas(
    seed_keywords=AR_SEEDS,
    seed_url="https://lp.qoyod.com/einvoice-integration/",
    language="ar",
    customer_id=ACC2,
)
print(f"  → {len(ideas)} ideas")

# 3. Filter
def keep(idea):
    txt = idea["keyword"].lower()
    if idea["avg_monthly"] < 100: return False
    if txt in current: return False
    bucket = classify_term(idea["keyword"], CAMP_NAME)
    if bucket in ("ALWAYS_NEGATIVE", "BRAND_ONLY", "COMPETITOR"):
        return False
    return True

new_ideas = [i for i in ideas if keep(i)]
new_ideas.sort(key=lambda x: x["avg_monthly"], reverse=True)

print(f"\n" + "=" * 78)
print(f"TOP CANDIDATES — {min(25, len(new_ideas))} not already on campaign, vol≥100, "
      f"not always-neg/brand/competitor")
print("=" * 78)
print(f"  {'keyword':<45} {'vol/mo':>8}  {'comp':<8}  {'low–high $':<14}")
for i in new_ideas[:25]:
    print(f"  {i['keyword'][:43]:<45} {i['avg_monthly']:>8,}  "
          f"{i['competition'][:7]:<8}  ${i['low_cpc_usd']:.2f}–${i['high_cpc_usd']:.2f}")

with open("scripts/_phase2_kw_proposals.json", "w", encoding="utf-8") as f:
    json.dump({"current": sorted(current), "candidates": new_ideas[:25]},
              f, ensure_ascii=False, indent=2)
print(f"\n✅ saved scripts/_phase2_kw_proposals.json")
