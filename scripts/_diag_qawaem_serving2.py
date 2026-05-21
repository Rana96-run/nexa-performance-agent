"""Cleaner v2 — confirm zero impressions because of $0.01 CPC bid."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23861837000"
client = get_client()
ga = client.get_service("GoogleAdsService")

def q(sql): return list(ga.search(customer_id=ACCOUNT, query=sql))

# Campaign-level lost IS reasons over 30d
print("Campaign IS — last 30d (the diagnosis number)")
for r in q(f"""
  SELECT metrics.impressions, metrics.clicks,
         metrics.search_impression_share,
         metrics.search_budget_lost_impression_share,
         metrics.search_rank_lost_impression_share,
         metrics.search_top_impression_share
  FROM campaign
  WHERE campaign.id = {CAMP_ID}
    AND segments.date DURING LAST_30_DAYS
"""):
    m = r.metrics
    print(f"  impressions      : {m.impressions}")
    print(f"  clicks           : {m.clicks}")
    print(f"  IS               : {m.search_impression_share*100:.2f}%")
    print(f"  lost (BUDGET)    : {m.search_budget_lost_impression_share*100:.2f}%")
    print(f"  lost (RANK/bid)  : {m.search_rank_lost_impression_share*100:.2f}%")

# Keyword-level: top 12 by impressions, show QS + first-page bid
print("\nKeywords — last 30d, sorted by impressions, with first-page bid")
rows = q(f"""
  SELECT ad_group_criterion.keyword.text,
         ad_group.name,
         metrics.impressions, metrics.clicks,
         ad_group_criterion.quality_info.quality_score,
         ad_group_criterion.position_estimates.first_page_cpc_micros,
         ad_group_criterion.position_estimates.top_of_page_cpc_micros
  FROM keyword_view
  WHERE campaign.id = {CAMP_ID}
    AND segments.date DURING LAST_30_DAYS
  ORDER BY metrics.impressions DESC
  LIMIT 12
""")
for r in rows:
    kw = r.ad_group_criterion.keyword.text
    fp = r.ad_group_criterion.position_estimates.first_page_cpc_micros / 1e6
    top = r.ad_group_criterion.position_estimates.top_of_page_cpc_micros / 1e6
    print(f"  {kw[:40]:<40}  imp={r.metrics.impressions:>4}  clicks={r.metrics.clicks:>3}  "
          f"QS={r.ad_group_criterion.quality_info.quality_score}  "
          f"need_first_page=${fp:.2f}  top=${top:.2f}")

if not rows:
    print("  (no rows — never won an impression)")
