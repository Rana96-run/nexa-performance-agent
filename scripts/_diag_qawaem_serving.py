"""Diagnose why Google_Search_AREN_FinancialStatement (Acc 1) is not serving.

Checks:
  1. Campaign status, budget, bidding
  2. Ad-group statuses, CPC bids
  3. Ad approval / policy state for every RSA (lp.qoyod.com/qawaem/ crawl issues
     surface here as policy_topic_entries)
  4. Last 7d impressions / clicks / spend per ad group
  5. Top search terms / keywords by impressions (to see if anything is even
     entering auctions)
  6. impression_share / lost_is_budget / lost_is_rank metrics

# KPI-RULE-BYPASS — diagnosis, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23861837000"

client = get_client()
ga = client.get_service("GoogleAdsService")


def q(sql):
    return list(ga.search(customer_id=ACCOUNT, query=sql))


# 1. Campaign
print("=" * 72)
print("1. Campaign state")
print("=" * 72)
for r in q(f"""
  SELECT campaign.id, campaign.name, campaign.status,
         campaign.bidding_strategy_type,
         campaign.target_spend.cpc_bid_ceiling_micros,
         campaign_budget.amount_micros,
         campaign.serving_status
  FROM campaign WHERE campaign.id = {CAMP_ID}
"""):
    c = r.campaign
    print(f"  name           : {c.name}")
    print(f"  status         : {c.status.name}")
    print(f"  serving_status : {c.serving_status.name}")
    print(f"  bidding        : {c.bidding_strategy_type.name}")
    print(f"  cpc ceiling    : ${c.target_spend.cpc_bid_ceiling_micros/1e6:.2f}")
    print(f"  budget         : ${r.campaign_budget.amount_micros/1e6:.2f}/d")

# 2. Ad groups
print("\n" + "=" * 72)
print("2. Ad groups")
print("=" * 72)
ag_ids = []
for r in q(f"""
  SELECT ad_group.id, ad_group.name, ad_group.status,
         ad_group.cpc_bid_micros
  FROM ad_group WHERE campaign.id = {CAMP_ID}
"""):
    ag = r.ad_group
    ag_ids.append(str(ag.id))
    print(f"  {ag.name}: status={ag.status.name}  cpc=${ag.cpc_bid_micros/1e6:.2f}")

# 3. Ad policy approval — the key check for crawl issues
print("\n" + "=" * 72)
print("3. Ad approval / policy state (RSA + final URL crawl)")
print("=" * 72)
for r in q(f"""
  SELECT ad_group.name, ad_group_ad.ad.id,
         ad_group_ad.status,
         ad_group_ad.policy_summary.approval_status,
         ad_group_ad.policy_summary.review_status,
         ad_group_ad.policy_summary.policy_topic_entries,
         ad_group_ad.ad.final_urls
  FROM ad_group_ad
  WHERE campaign.id = {CAMP_ID}
    AND ad_group_ad.status != 'REMOVED'
"""):
    a = r.ad_group_ad
    print(f"\n  AG={r.ad_group.name}  ad_id={a.ad.id}")
    print(f"    status         : {a.status.name}")
    print(f"    approval       : {a.policy_summary.approval_status.name}")
    print(f"    review         : {a.policy_summary.review_status.name}")
    print(f"    final_urls     : {list(a.ad.final_urls)}")
    for pt in a.policy_summary.policy_topic_entries:
        print(f"    POLICY[{pt.type_.name}] topic={pt.topic}")
        for e in pt.evidences:
            for u in e.website_list.websites:
                print(f"      evidence url: {u}")

# 4. 7d perf per ad group
print("\n" + "=" * 72)
print("4. Last 7d perf per ad group")
print("=" * 72)
for r in q(f"""
  SELECT ad_group.name,
         metrics.impressions, metrics.clicks, metrics.cost_micros,
         metrics.search_impression_share,
         metrics.search_budget_lost_impression_share,
         metrics.search_rank_lost_impression_share
  FROM ad_group
  WHERE campaign.id = {CAMP_ID}
    AND segments.date DURING LAST_7_DAYS
"""):
    m = r.metrics
    print(f"  {r.ad_group.name}: imp={m.impressions} clicks={m.clicks} "
          f"spend=${m.cost_micros/1e6:.2f}")
    print(f"    IS={m.search_impression_share*100:.0f}%  "
          f"lost(budget)={m.search_budget_lost_impression_share*100:.0f}%  "
          f"lost(rank)={m.search_rank_lost_impression_share*100:.0f}%")

# 5. Keyword impressions
print("\n" + "=" * 72)
print("5. Top 10 keywords by 7d impressions")
print("=" * 72)
rows = q(f"""
  SELECT ad_group_criterion.keyword.text,
         metrics.impressions, metrics.clicks, metrics.cost_micros,
         ad_group_criterion.quality_info.quality_score
  FROM keyword_view
  WHERE campaign.id = {CAMP_ID}
    AND segments.date DURING LAST_7_DAYS
  ORDER BY metrics.impressions DESC
  LIMIT 10
""")
if rows:
    for r in rows:
        kw = r.ad_group_criterion.keyword.text
        m  = r.metrics
        qs = r.ad_group_criterion.quality_info.quality_score
        print(f"  {kw[:50]:<50} imp={m.impressions:>4} clicks={m.clicks:>3} "
              f"QS={qs}")
else:
    print("  (no keyword data in 7d — campaign hasn't entered any auctions)")

# 6. Campaign-level lost IS reasons (crucial diagnosis)
print("\n" + "=" * 72)
print("6. Campaign-level impression share")
print("=" * 72)
for r in q(f"""
  SELECT metrics.search_impression_share,
         metrics.search_budget_lost_impression_share,
         metrics.search_rank_lost_impression_share,
         metrics.search_absolute_top_impression_share
  FROM campaign
  WHERE campaign.id = {CAMP_ID}
    AND segments.date DURING LAST_7_DAYS
"""):
    m = r.metrics
    print(f"  IS               : {m.search_impression_share*100:.1f}%")
    print(f"  lost (budget)    : {m.search_budget_lost_impression_share*100:.1f}%")
    print(f"  lost (rank)      : {m.search_rank_lost_impression_share*100:.1f}%")
    print(f"  abs top IS       : {m.search_absolute_top_impression_share*100:.1f}%")

print("\nDONE")
