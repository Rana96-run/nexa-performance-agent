"""Apply the same 11 observation audiences (direct + indirect) to the 3
brand campaigns on Acc1. Same logic as ZATCA — zero reach loss, useful
signal layer for Smart Bidding."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"

BRAND_CAMPS = {
    "22221111741": "ImpressionShare_Search_AR_Brand",
    "22434988923": "Search_AR_Brand",
    "23032247671": "Search_AR_Brand_v2",
}

# Same 11 as ZATCA (after removing Network & Enterprise Security)
AUDIENCES = {
    # Direct fit (6)
    "80133": "Financial Planning",
    "80137": "Tax Preparation Services & Software",
    "80281": "Accounting Software",
    "80463": "Business Services",
    "80530": "Enterprise Software",
    "80536": "ERP Solutions",
    # Indirect (5)
    "80279": "Business & Productivity Software",
    "80518": "Business Financial Services",
    "80538": "Hosted Data & Cloud Storage",
    "92913": "Business Professionals (AFFINITY)",
    "92931": "Cloud Services Power Users (AFFINITY)",
}

client    = get_client()
camp_svc  = client.get_service("CampaignService")
cc_svc    = client.get_service("CampaignCriterionService")


# 1. Set targeting_setting → AUDIENCE bid_only=True on each brand campaign
print("1. Set AUDIENCE bid_only=True (observation mode) on 3 brand campaigns")
ops = []
for cid in BRAND_CAMPS:
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
    tr = client.get_type("TargetRestriction")
    tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
    tr.bid_only            = True
    op.update.targeting_setting.target_restrictions.append(tr)
    client.copy_from(op.update_mask,
        field_mask_pb2.FieldMask(paths=["targeting_setting.target_restrictions"]))
    ops.append(op)
r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ {res.resource_name}")

# 2. Link audiences
print("\n2. Link 11 audiences to each brand campaign")
ops = []
for cid in BRAND_CAMPS:
    for aid in AUDIENCES:
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_interest.user_interest_category = (
            f"customers/{ACCOUNT}/userInterests/{aid}"
        )
        ops.append(op)
r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
print(f"  ✅ added {len(r.results)} associations  (11 audiences × 3 campaigns)")
