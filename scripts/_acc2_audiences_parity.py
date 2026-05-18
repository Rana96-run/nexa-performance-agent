"""Bring Acc2 prospecting campaigns to parity with Acc1's audience treatment.

Adds 3 layers to the 13 Acc2 prospecting Search campaigns:
  1. AUDIENCE bid_only=True (observation mode on targeting_setting)
  2. 11 in-market + affinity observation audiences (same set as Acc1)
  3. 3 customer exclusions (HubSpot - All Customers, Premium/Pro Subscribers, Active SaaS Users)
  4. 3 warm observation lists (HubSpot All Marketing Contacts, All Converters, Ad Video Viewers)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "5753494964"
SEARCH_PROSPECTING = [
    "1624813104", "13910658414", "13913291987", "14051112466", "14051278536",
    "14054086994", "14353048311", "14353071777", "14353925266", "14354680547",
    "16851344135", "23348517003", "23835392373",
]

# User-interest IDs (global, same as Acc1)
IN_MARKET_AUDIENCES = {
    "80133": "Financial Planning",
    "80137": "Tax Preparation Services & Software",
    "80281": "Accounting Software",
    "80463": "Business Services",
    "80530": "Enterprise Software",
    "80536": "ERP Solutions",
    "80279": "Business & Productivity Software",
    "80518": "Business Financial Services",
    "80538": "Hosted Data & Cloud Storage",
    "92913": "Business Professionals (AFFINITY)",
    "92931": "Cloud Services Power Users (AFFINITY)",
}

# CRM lists to EXCLUDE (don't pay to re-acquire current payers)
EXCLUDE_LIST_NAMES = [
    "HubSpot - All Customers",
    "HubSpot - Advanced/Premium/Pro Subscribers",
    "Active SaaS Users",
]

# Warm lists to OBSERVE
OBSERVE_LIST_NAMES = [
    "HubSpot - All Marketing Contacts",
    "All Converters",
    "Ad Video Viewers",
    "Channel Video Viewers",
]

client    = get_client()
ga        = client.get_service("GoogleAdsService")
camp_svc  = client.get_service("CampaignService")
cc_svc    = client.get_service("CampaignCriterionService")


# ── 1. Set AUDIENCE bid_only=True on each campaign ─────────────────────────
print("1. Set AUDIENCE bid_only=True (observation mode) on 13 campaigns")
ops = []
for cid in SEARCH_PROSPECTING:
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
    tr = client.get_type("TargetRestriction")
    tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
    tr.bid_only            = True
    op.update.targeting_setting.target_restrictions.append(tr)
    client.copy_from(op.update_mask,
        field_mask_pb2.FieldMask(paths=["targeting_setting.target_restrictions"]))
    ops.append(op)

try:
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ updated {len(r.results)} campaign targeting_setting(s)")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:3]: print(f"  ❌ {m}")


# ── 2. Resolve user_list resource names ────────────────────────────────────
exclude_rns = {}
observe_rns = {}
q = """
SELECT user_list.resource_name, user_list.name, user_list.size_for_search
FROM user_list
WHERE user_list.size_for_search >= 1000
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    n = r.user_list.name
    if n in EXCLUDE_LIST_NAMES and n not in exclude_rns:
        exclude_rns[n] = (r.user_list.resource_name, r.user_list.size_for_search)
    if n in OBSERVE_LIST_NAMES and n not in observe_rns:
        observe_rns[n] = (r.user_list.resource_name, r.user_list.size_for_search)

print(f"\n2. Resolved CRM/site lists:")
print("   EXCLUDE:")
for n, (rn, sz) in exclude_rns.items():
    print(f"     {n:<50} size={sz:>8,}")
print("   OBSERVE:")
for n, (rn, sz) in observe_rns.items():
    print(f"     {n:<50} size={sz:>8,}")


# ── 3. Build all campaign-criterion ops ────────────────────────────────────
ops = []
for cid in SEARCH_PROSPECTING:
    # In-market + affinity audiences (observation)
    for aid in IN_MARKET_AUDIENCES:
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_interest.user_interest_category = \
            f"customers/{ACCOUNT}/userInterests/{aid}"
        ops.append(op)
    # User-list exclusions
    for n, (rn, _) in exclude_rns.items():
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_list.user_list = rn
        op.create.negative = True
        ops.append(op)
    # User-list observations
    for n, (rn, _) in observe_rns.items():
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_list.user_list = rn
        op.create.negative = False
        ops.append(op)

print(f"\n3. Apply {len(ops)} operations  "
      f"(per campaign: {len(IN_MARKET_AUDIENCES)} audiences + "
      f"{len(exclude_rns)} excludes + {len(observe_rns)} observes)")

try:
    r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ added {len(r.results)} associations")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:8]: print(f"  ❌ {m}")
