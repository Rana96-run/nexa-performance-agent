"""Diagnose Search_AR_Brand_v2 (22434988923 — Acc 1) leakage.

Checks:
  1. Campaign settings: network (Search Partners, Display), bidding
  2. Keyword list with match type + 14d performance (impressions per kw)
  3. Top search terms by impressions (where the 104k is coming from)
  4. Current negatives
  5. Ad-group settings (DSA toggles, etc.)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACCT = "1513020554"
CID  = "23032247671"   # Search_AR_Brand_v2

client = get_client()
ga = client.get_service("GoogleAdsService")


def q(sql):
    return list(ga.search(customer_id=ACCT, query=sql))


# 1. Campaign settings
print("=" * 78)
print("1. CAMPAIGN SETTINGS")
print("=" * 78)
for r in q(f"""
    SELECT campaign.id, campaign.name, campaign.status,
           campaign.advertising_channel_type,
           campaign.advertising_channel_sub_type,
           campaign.bidding_strategy_type,
           campaign.network_settings.target_google_search,
           campaign.network_settings.target_search_network,
           campaign.network_settings.target_content_network,
           campaign.network_settings.target_partner_search_network,
           campaign.target_spend.cpc_bid_ceiling_micros,
           campaign_budget.amount_micros,
           campaign.dynamic_search_ads_setting.domain_name,
           campaign.dynamic_search_ads_setting.use_supplied_urls_only
    FROM campaign WHERE campaign.id = {CID}
"""):
    c = r.campaign
    print(f"  name              : {c.name}")
    print(f"  channel           : {c.advertising_channel_type.name}")
    print(f"  sub_type          : {c.advertising_channel_sub_type.name}")
    print(f"  bidding           : {c.bidding_strategy_type.name}")
    print(f"  budget            : ${r.campaign_budget.amount_micros/1e6:.0f}/d")
    print(f"  network: google_search={c.network_settings.target_google_search}")
    print(f"           search_partners={c.network_settings.target_search_network}")
    print(f"           content/display={c.network_settings.target_content_network}")
    print(f"           partner_search ={c.network_settings.target_partner_search_network}")
    print(f"  cpc ceiling       : ${c.target_spend.cpc_bid_ceiling_micros/1e6:.2f}")
    print(f"  DSA domain        : {c.dynamic_search_ads_setting.domain_name or '(none)'}")
    print(f"  DSA supplied_only : {c.dynamic_search_ads_setting.use_supplied_urls_only}")


# 2. Keywords + 14d performance
print(f"\n{'=' * 78}")
print(f"2. KEYWORDS — last 14d (sorted by impressions desc)")
print('=' * 78)
rows = q(f"""
    SELECT ad_group.name,
           ad_group_criterion.keyword.text,
           ad_group_criterion.keyword.match_type,
           ad_group_criterion.status,
           ad_group_criterion.quality_info.quality_score,
           metrics.impressions,
           metrics.clicks,
           metrics.cost_micros
    FROM keyword_view
    WHERE campaign.id = {CID}
      AND segments.date DURING LAST_14_DAYS
    ORDER BY metrics.impressions DESC
""")
print(f"  {'kw text':<42} {'match':<8} {'AG':<22} {'imp':>7} {'clk':>5} "
      f"{'spend':>7} {'QS':>3} {'CTR%':>6}")
for r in rows[:30]:
    kw = r.ad_group_criterion.keyword.text[:40]
    match = r.ad_group_criterion.keyword.match_type.name[:7]
    ag = r.ad_group.name[:22]
    imp = r.metrics.impressions
    clk = r.metrics.clicks
    cost = r.metrics.cost_micros / 1e6
    qs = r.ad_group_criterion.quality_info.quality_score
    ctr = (clk / imp * 100) if imp else 0
    print(f"  {kw:<42} {match:<8} {ag:<22} {imp:>7} {clk:>5} "
          f"${cost:>6.0f} {qs:>3} {ctr:>5.1f}%")


# 3. Top search terms
print(f"\n{'=' * 78}")
print(f"3. TOP SEARCH TERMS — last 14d (showing where impressions came from)")
print('=' * 78)
rows = q(f"""
    SELECT search_term_view.search_term,
           ad_group.name,
           metrics.impressions, metrics.clicks, metrics.cost_micros
    FROM search_term_view
    WHERE campaign.id = {CID}
      AND segments.date DURING LAST_14_DAYS
    ORDER BY metrics.impressions DESC
    LIMIT 40
""")
print(f"  {'search term':<48} {'AG':<20} {'imp':>7} {'clk':>4} {'CTR%':>6}")
non_brand_imp = 0
brand_imp = 0
for r in rows:
    st = r.search_term_view.search_term
    imp = r.metrics.impressions
    clk = r.metrics.clicks
    ctr = (clk/imp*100) if imp else 0
    is_brand = "قيود" in st or "qoyod" in st.lower()
    if is_brand: brand_imp += imp
    else: non_brand_imp += imp
    flag = "" if is_brand else "  ← NON-BRAND"
    print(f"  {st[:48]:<48} {r.ad_group.name[:20]:<20} {imp:>7} {clk:>4} {ctr:>5.1f}%{flag}")
print(f"\n  brand impressions    : {brand_imp:,}")
print(f"  non-brand impressions: {non_brand_imp:,}  ← LEAKAGE")


# 4. Current negatives
print(f"\n{'=' * 78}")
print(f"4. CAMPAIGN NEGATIVES")
print('=' * 78)
neg = 0
for r in q(f"""
    SELECT campaign_criterion.keyword.text,
           campaign_criterion.keyword.match_type
    FROM campaign_criterion
    WHERE campaign.id = {CID}
      AND campaign_criterion.type = 'KEYWORD'
      AND campaign_criterion.negative = TRUE
"""):
    neg += 1
    print(f"  [{r.campaign_criterion.keyword.match_type.name:<6}] "
          f"{r.campaign_criterion.keyword.text}")
print(f"\n  total: {neg}")
