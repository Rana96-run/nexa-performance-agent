"""Add audiences + age ranges as OBSERVATION (not targeting) to all 3 ZATCA
campaigns. Observation = no reach loss; gives Smart Bidding bid-adjustment signal.

Two steps per campaign:
  1. Flip targeting_setting → AUDIENCE bid_only=True, AGE_RANGE bid_only=True
     (this is what makes added criteria "observation" instead of "targeting")
  2. Add the criteria themselves
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

# Standard Google Ads age-range criterion IDs
AGE_RANGES = {
    "AGE_RANGE_18_24":         503001,
    "AGE_RANGE_25_34":         503002,
    "AGE_RANGE_35_44":         503003,
    "AGE_RANGE_45_54":         503004,
    "AGE_RANGE_55_64":         503005,
    "AGE_RANGE_65_UP":         503006,
    "AGE_RANGE_UNDETERMINED":  503999,
}

client = get_client()
ga         = client.get_service("GoogleAdsService")
camp_svc   = client.get_service("CampaignService")
cc_svc     = client.get_service("CampaignCriterionService")


# ── Step 0: discover relevant in-market audience IDs for B2B / SMB buyers ──
print("=" * 70)
print("0. Discover in-market audience IDs (Business / Software / SMB)")
print("=" * 70)
q = """
SELECT user_interest.user_interest_id, user_interest.name,
       user_interest.taxonomy_type
FROM user_interest
WHERE user_interest.taxonomy_type = 'IN_MARKET'
"""
candidates = []
keywords_to_match = [
    "business services",
    "enterprise software",
    "accounting software",
    "small business",
    "tax preparation",
    "financial planning",
    "business productivity",
    "business management",
    "erp",
    "crm software",
]
all_im = list(ga.search(customer_id=ACCOUNT, query=q))
print(f"  ({len(all_im)} in-market audiences total)")

for r in all_im:
    nl = r.user_interest.name.lower()
    for kw in keywords_to_match:
        if kw in nl:
            candidates.append({
                "id":   r.user_interest.user_interest_id,
                "name": r.user_interest.name,
            })
            break

# Dedupe
seen_ids = set()
unique = []
for c in candidates:
    if c["id"] not in seen_ids:
        seen_ids.add(c["id"])
        unique.append(c)
candidates = unique

print(f"\n  Matched {len(candidates)} relevant in-market audiences:")
for c in candidates[:20]:
    print(f"    {c['id']:>12}  {c['name']}")


# ── Step 1: Flip targeting_setting to bid_only for AUDIENCE + AGE_RANGE ────
print()
print("=" * 70)
print("1. Set targeting_setting → bid_only=True (observation) on AUDIENCE + AGE_RANGE")
print("=" * 70)
ops = []
for cid in CAMPS:
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
    # Only AUDIENCE is a valid TargetRestriction dimension — AGE_RANGE and
    # GENDER are observation by default once added as criteria.
    tr = client.get_type("TargetRestriction")
    tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
    tr.bid_only            = True
    op.update.targeting_setting.target_restrictions.append(tr)
    client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["targeting_setting.target_restrictions"]))
    ops.append(op)
r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
for res in r.results:
    print(f"  ✅ {res.resource_name}  (AUDIENCE bid_only=True)")


# ── Step 2: Add age-range criteria (all 7) to each campaign ────────────────
print()
print("=" * 70)
print("2. Add all 7 age ranges as observation criteria")
print("=" * 70)
ops = []
for cid in CAMPS:
    for name, age_id in AGE_RANGES.items():
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign     = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.negative     = False    # explicit — proto-plus default unclear
        op.create.age_range.type_ = getattr(client.enums.AgeRangeTypeEnum, name)
        ops.append(op)
try:
    r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ added {len(r.results)} age-range criteria")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:5]: print(f"  ❌ {m}")


# ── Step 3: Add matched in-market audiences to each campaign ───────────────
print()
print("=" * 70)
print(f"3. Add {len(candidates)} in-market audiences as observation")
print("=" * 70)
if not candidates:
    print("  (no audiences matched — skipping)")
else:
    ops = []
    for cid in CAMPS:
        for cand in candidates:
            op = client.get_type("CampaignCriterionOperation")
            op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
            op.create.user_interest.user_interest_category = (
                f"customers/{ACCOUNT}/userInterests/{cand['id']}"
            )
            ops.append(op)
    try:
        r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
        print(f"  ✅ added {len(r.results)} audience associations")
    except Exception as e:
        import re
        msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
        for m in msgs[:5]: print(f"  ❌ {m}")


print("\n" + "=" * 70)
print("DONE — audiences + age ranges added as OBSERVATION (no reach loss)")
print("Smart Bidding will use these as bid signals over the next 7-14 days.")
print("=" * 70)
