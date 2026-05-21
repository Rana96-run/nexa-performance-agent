"""Verify FinancialStatement bid settings on both accounts after manual edit."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "23861837000", "Acc 1"),
    ("5753494964", "23870151040", "Acc 2"),
]

client = get_client()
ga = client.get_service("GoogleAdsService")

for acct, cid, label in TARGETS:
    print(f"\n=== {label} ({acct}) campaign {cid} ===")
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.name, campaign.status,
               campaign.bidding_strategy_type,
               campaign.target_spend.cpc_bid_ceiling_micros,
               campaign_budget.amount_micros
        FROM campaign WHERE campaign.id = {cid}
    """):
        c = r.campaign
        ceiling = c.target_spend.cpc_bid_ceiling_micros / 1e6
        print(f"  status      : {c.status.name}")
        print(f"  bidding     : {c.bidding_strategy_type.name}")
        print(f"  CPC ceiling : ${ceiling:.2f}" + ("  (no limit)" if ceiling == 0 else ""))
        print(f"  budget      : ${r.campaign_budget.amount_micros/1e6:.2f}/d")

    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.name, ad_group.status, ad_group.cpc_bid_micros
        FROM ad_group WHERE campaign.id = {cid}
    """):
        ag = r.ad_group
        print(f"  AG {ag.name:<22} status={ag.status.name}  default_max_cpc=${ag.cpc_bid_micros/1e6:.2f}")
