"""Full audit of the 3 ZATCA campaigns — checks every setting we've discussed."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

c = get_client()
ga = c.get_service("GoogleAdsService")

# Campaign
q = f"""
SELECT campaign.id, campaign.name, campaign.status,
       campaign.network_settings.target_content_network,
       campaign_budget.amount_micros, campaign_budget.explicitly_shared,
       campaign.bidding_strategy_type,
       campaign.maximize_conversions.target_cpa_micros,
       campaign.final_url_suffix,
       campaign.url_custom_parameters,
       campaign.selective_optimization.conversion_actions
FROM campaign WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    cp = r.campaign
    print(f"\n{cp.name} [{cp.status.name}]")
    print(f"  budget       : ${r.campaign_budget.amount_micros/1_000_000:.2f}/d  shared={r.campaign_budget.explicitly_shared}")
    print(f"  bidding      : {cp.bidding_strategy_type.name}  tCPA=${cp.maximize_conversions.target_cpa_micros/1_000_000:.2f}")
    print(f"  display_off  : {not cp.network_settings.target_content_network}")
    print(f"  suffix_set   : {'YES' if cp.final_url_suffix else 'NO'}")
    print(f"  custom_params: {len(cp.url_custom_parameters)}")
    print(f"  conv_actions : {len(cp.selective_optimization.conversion_actions)}  (0 = uses account default blend)")

# Ad-group level
print("\n--- AD GROUPS ---")
q2 = f"""
SELECT campaign.name, ad_group.id, ad_group.name, ad_group.cpc_bid_micros
FROM ad_group WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q2):
    cpc = r.ad_group.cpc_bid_micros / 1_000_000 if r.ad_group.cpc_bid_micros else 0
    print(f"  {r.ad_group.name}  cpc_bid=${cpc:.2f}")

# RSA headlines (count + pinning)
print("\n--- RSA ASSETS (headlines / descriptions / final_urls) ---")
q3 = f"""
SELECT campaign.name,
       ad_group_ad.ad.responsive_search_ad.headlines,
       ad_group_ad.ad.responsive_search_ad.descriptions,
       ad_group_ad.ad.final_urls
FROM ad_group_ad WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q3):
    rsa = r.ad_group_ad.ad.responsive_search_ad
    print(f"\n  {r.campaign.name}")
    print(f"    final_urls : {list(r.ad_group_ad.ad.final_urls)}")
    pins = sum(1 for h in rsa.headlines if h.pinned_field)
    print(f"    headlines  : {len(rsa.headlines)} (pinned: {pins})")
    print(f"    desc       : {len(rsa.descriptions)}")

# OLD HubSpot - Lead status
print("\n--- ACCOUNT-LEVEL CONVERSION ACTIONS ---")
q4 = """
SELECT conversion_action.id, conversion_action.name, conversion_action.status,
       conversion_action.primary_for_goal, conversion_action.category
FROM conversion_action
WHERE conversion_action.name LIKE '%HubSpot%' OR conversion_action.name LIKE '%Lead%'
"""
for r in ga.search(customer_id=ACCOUNT, query=q4):
    a = r.conversion_action
    pri = "★" if a.primary_for_goal else " "
    print(f"  {pri} [{a.status.name:<8}] [{a.category.name:<15}] {a.name}  (id={a.id})")
