"""Add 5 indirect-but-effective audiences as observation to all 3 ZATCA
campaigns. Total audiences per campaign goes from 6 → 11."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

INDIRECT = {
    "80279": "Business & Productivity Software (IN_MARKET)",
    "80518": "Business Financial Services (IN_MARKET)",
    "80538": "Hosted Data & Cloud Storage (IN_MARKET)",
    "92913": "Business Professionals (AFFINITY)",
    "92931": "Cloud Services Power Users (AFFINITY)",
}

client = get_client()
cc_svc = client.get_service("CampaignCriterionService")

ops = []
for cid in CAMPS:
    for aid in INDIRECT:
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_interest.user_interest_category = (
            f"customers/{ACCOUNT}/userInterests/{aid}"
        )
        ops.append(op)

for aid, name in INDIRECT.items():
    print(f"  + {aid}  {name}")

r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"\n✅ added {len(r.results)} associations  (5 audiences × 3 campaigns)")
