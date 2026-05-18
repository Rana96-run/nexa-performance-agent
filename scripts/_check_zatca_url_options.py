"""Check URL options + CPC bid limits on the 3 ZATCA campaigns."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

client = get_client()
ga = client.get_service("GoogleAdsService")

# Campaign-level URL options + bid ceilings
print("=" * 78)
print("CAMPAIGN-LEVEL — URL options + bid ceiling")
print("=" * 78)
q1 = f"""
SELECT campaign.id, campaign.name,
       campaign.tracking_url_template,
       campaign.final_url_suffix,
       campaign.url_custom_parameters,
       campaign.maximize_conversions.target_cpa_micros,
       campaign.bidding_strategy_type
FROM campaign
WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q1):
    c = r.campaign
    print(f"\n{c.name}")
    print(f"  tracking_url_template : {c.tracking_url_template or '(empty)'}")
    print(f"  final_url_suffix      : {c.final_url_suffix or '(empty)'}")
    custom = list(c.url_custom_parameters)
    print(f"  url_custom_params     : {len(custom)} param(s)")
    for p in custom:
        print(f"     - {p.key}={p.value}")

# Ad-group-level URL options + CPC bids
print()
print("=" * 78)
print("AD-GROUP-LEVEL — URL options + CPC bid")
print("=" * 78)
q2 = f"""
SELECT campaign.name,
       ad_group.id, ad_group.name,
       ad_group.tracking_url_template,
       ad_group.final_url_suffix,
       ad_group.url_custom_parameters,
       ad_group.cpc_bid_micros,
       ad_group.effective_cpc_bid_micros
FROM ad_group
WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q2):
    a = r.ad_group
    print(f"\n{a.name}  (campaign: {r.campaign.name})")
    print(f"  tracking_url_template : {a.tracking_url_template or '(empty)'}")
    print(f"  final_url_suffix      : {a.final_url_suffix or '(empty)'}")
    custom = list(a.url_custom_parameters)
    print(f"  url_custom_params     : {len(custom)} param(s)")
    for p in custom:
        print(f"     - {p.key}={p.value}")
    cpc = a.cpc_bid_micros / 1_000_000 if a.cpc_bid_micros else 0
    eff = a.effective_cpc_bid_micros / 1_000_000 if a.effective_cpc_bid_micros else 0
    print(f"  cpc_bid_micros        : ${cpc:.2f}  (effective: ${eff:.2f})")
