"""Check whether the 3 ZATCA campaigns share a budget, and inspect conversion goal."""
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

print("=" * 75)
print("BUDGETS — is the budget shared across campaigns?")
print("=" * 75)
q = f"""
SELECT campaign.id, campaign.name,
       campaign_budget.id, campaign_budget.name,
       campaign_budget.amount_micros, campaign_budget.explicitly_shared,
       campaign.maximize_conversions.target_cpa_micros,
       campaign.target_cpa.target_cpa_micros,
       campaign.bidding_strategy_type
FROM campaign WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    c = r.campaign
    b = r.campaign_budget
    tcpa = (c.maximize_conversions.target_cpa_micros
            or c.target_cpa.target_cpa_micros) / 1_000_000
    print(f"\n{c.name}")
    print(f"  budget.id           : {b.id}")
    print(f"  budget.name         : {b.name}")
    print(f"  budget.amount       : ${b.amount_micros/1_000_000:.2f}/day")
    print(f"  budget.shared       : {b.explicitly_shared}")
    print(f"  bidding             : {c.bidding_strategy_type.name}")
    print(f"  tCPA                : ${tcpa:.2f}")

# Conversion goals on these campaigns
print()
print("=" * 75)
print("CONVERSION ACTIONS — which conversion event do these optimize for?")
print("=" * 75)
q2 = f"""
SELECT campaign.id, campaign.name,
       campaign.selective_optimization.conversion_actions
FROM campaign WHERE campaign.id IN ({",".join(CAMPS)})
"""
for r in ga.search(customer_id=ACCOUNT, query=q2):
    actions = list(r.campaign.selective_optimization.conversion_actions)
    print(f"\n{r.campaign.name}")
    if actions:
        for a in actions:
            print(f"  campaign-level conv action: {a}")
    else:
        print(f"  (no campaign-level override → uses account-default conversion goals)")

# Account-level default conversions
print()
print("=" * 75)
print("ACCOUNT default conversion actions (Account Goals)")
print("=" * 75)
q3 = """
SELECT conversion_action.id, conversion_action.name, conversion_action.status,
       conversion_action.primary_for_goal, conversion_action.category
FROM conversion_action
WHERE conversion_action.status = 'ENABLED'
"""
for r in ga.search(customer_id=ACCOUNT, query=q3):
    a = r.conversion_action
    primary = "★ PRIMARY" if a.primary_for_goal else " "
    print(f"  {primary} [{a.category.name:<10}] {a.name}")
