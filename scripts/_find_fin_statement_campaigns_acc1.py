"""Find any other Financial Statement / Qawaem campaigns on Acc 1."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACC1 = "1513020554"
client = get_client()
ga = client.get_service("GoogleAdsService")

print(f"All ENABLED/PAUSED campaigns on Acc {ACC1} matching financial/statement/qawaem/قوائم/مالي:")
for r in ga.search(customer_id=ACC1, query="""
    SELECT campaign.id, campaign.name, campaign.status,
           campaign.advertising_channel_type,
           campaign.bidding_strategy_type,
           campaign_budget.amount_micros
    FROM campaign
    WHERE campaign.status IN ('ENABLED','PAUSED')
"""):
    n = r.campaign.name.lower()
    if any(k in n for k in ["financial","statement","qawaem","qoyod_qawaem",
                            "financialst","قوائم","مالي","fin_"]):
        print(f"  [{r.campaign.status.name:<8}] {r.campaign.name} ({r.campaign.id})  "
              f"type={r.campaign.advertising_channel_type.name}  "
              f"bidding={r.campaign.bidding_strategy_type.name}  "
              f"budget=${r.campaign_budget.amount_micros/1e6:.0f}/d")
