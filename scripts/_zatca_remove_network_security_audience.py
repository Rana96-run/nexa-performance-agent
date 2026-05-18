"""Remove the 'Network & Enterprise Security' audience from all 3 ZATCA
campaigns — poor fit for Phase 2 compliance buyers."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
TARGET_AUDIENCE_ID = "80539"  # Network & Enterprise Security
CAMPS = ["23851270716", "23861101390", "23861965426"]

client = get_client()
ga     = client.get_service("GoogleAdsService")
cc_svc = client.get_service("CampaignCriterionService")

# Find criterion resource names for this audience on the 3 campaigns
q = f"""
SELECT campaign.id, campaign.name,
       campaign_criterion.resource_name,
       campaign_criterion.user_interest.user_interest_category
FROM campaign_criterion
WHERE campaign.id IN ({",".join(CAMPS)})
  AND campaign_criterion.type = 'USER_INTEREST'
"""
to_remove = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    rn = r.campaign_criterion.user_interest.user_interest_category
    if rn.endswith(f"/{TARGET_AUDIENCE_ID}"):
        to_remove.append((r.campaign.name, r.campaign_criterion.resource_name))

print(f"Found {len(to_remove)} associations to remove:")
for name, rn in to_remove:
    print(f"  {name}")

ops = []
for _, rn in to_remove:
    op = client.get_type("CampaignCriterionOperation")
    op.remove = rn
    ops.append(op)
r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"\n✅ removed {len(r.results)} 'Network & Enterprise Security' associations")
