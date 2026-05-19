"""Locate the new FinancialStatemnt campaign + its ad groups on both accounts."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

NAME_PATTERN = "Google_Search_AR_FinancialStatemnt"
c = get_client()
ga = c.get_service("GoogleAdsService")

for acct in ["1513020554", "5753494964"]:
    print(f"\n=== Account {acct} ===")
    q = """
    SELECT campaign.id, campaign.name, campaign.status,
           campaign.advertising_channel_type,
           campaign.bidding_strategy_type,
           campaign_budget.amount_micros
    FROM campaign
    WHERE campaign.name REGEXP_MATCH '(?i).*(FinancialStatem|Qawaem|قوائم).*'
    """
    found = False
    for r in ga.search(customer_id=acct, query=q):
        found = True
        print(f"  cid={r.campaign.id}  [{r.campaign.status.name}]  {r.campaign.name}")
        print(f"    channel={r.campaign.advertising_channel_type.name}  bidding={r.campaign.bidding_strategy_type.name}")
        print(f"    budget=${r.campaign_budget.amount_micros/1_000_000:.2f}/d")

        # Ad groups
        q2 = f"SELECT ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.id = {r.campaign.id}"
        for ag in ga.search(customer_id=acct, query=q2):
            print(f"    ag={ag.ad_group.id}  {ag.ad_group.name}  [{ag.ad_group.status.name}]")
    if not found:
        print("  (no match)")
