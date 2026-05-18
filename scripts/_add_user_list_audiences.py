"""Add CRM + site visitor + video viewer audiences to ZATCA + Brand campaigns.

ZATCA (3 campaigns):
  - EXCLUDE: HubSpot All Customers + Advanced/Premium/Pro Subscribers
  - OBSERVE: e-invoice page, GA4 site visitors, All Converters,
             Ad Video Viewers, Channel Video Viewers

Brand (3 campaigns):
  - OBSERVE only (same 5 lists; do NOT exclude customers from brand search)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"

ZATCA_CAMPS = ["23851270716", "23861101390", "23861965426"]
BRAND_CAMPS = ["22221111741", "22434988923", "23032247671"]

# Target lists by exact name (more reliable than ID across re-creations)
EXCLUDE_LIST_NAMES = [
    "HubSpot - All Customers",
    "HubSpot - Advanced/Premium/Pro Subscribers",
]
OBSERVE_LIST_NAMES = [
    "e-invoice page",
    "West Asia Qoyod visitors - GA4",
    "All Converters",
    "Ad Video Viewers",
    "Channel Video Viewers",
]

client = get_client()
ga     = client.get_service("GoogleAdsService")
cc_svc = client.get_service("CampaignCriterionService")

# Resolve list names → resource_names. Lists with >= 1000 Search size only.
q = """
SELECT user_list.resource_name, user_list.name, user_list.size_for_search
FROM user_list
WHERE user_list.size_for_search >= 1000
"""
by_name_exclude = {}
by_name_observe = {}
for r in ga.search(customer_id=ACCOUNT, query=q):
    n = r.user_list.name
    rn = r.user_list.resource_name
    sz = r.user_list.size_for_search
    if n in EXCLUDE_LIST_NAMES and n not in by_name_exclude:
        by_name_exclude[n] = (rn, sz)
    if n in OBSERVE_LIST_NAMES and n not in by_name_observe:
        by_name_observe[n] = (rn, sz)

print("Resolved EXCLUDE lists:")
for n, (rn, sz) in by_name_exclude.items():
    print(f"  {n:<50} size={sz:>8,}")
print("\nResolved OBSERVE lists:")
for n, (rn, sz) in by_name_observe.items():
    print(f"  {n:<50} size={sz:>8,}")

if len(by_name_exclude) != len(EXCLUDE_LIST_NAMES):
    missing = set(EXCLUDE_LIST_NAMES) - set(by_name_exclude)
    print(f"\n⚠ EXCLUDE lists not found / too small: {missing}")
if len(by_name_observe) != len(OBSERVE_LIST_NAMES):
    missing = set(OBSERVE_LIST_NAMES) - set(by_name_observe)
    print(f"\n⚠ OBSERVE lists not found / too small: {missing}")


# ── Build operations ───────────────────────────────────────────────────────
ops = []

# ZATCA: EXCLUDE + OBSERVE
for cid in ZATCA_CAMPS:
    # Exclude
    for n, (rn, _) in by_name_exclude.items():
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_list.user_list = rn
        op.create.negative = True
        ops.append(op)
    # Observe
    for n, (rn, _) in by_name_observe.items():
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_list.user_list = rn
        op.create.negative = False
        ops.append(op)

# Brand: OBSERVE only
for cid in BRAND_CAMPS:
    for n, (rn, _) in by_name_observe.items():
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.user_list.user_list = rn
        op.create.negative = False
        ops.append(op)

print(f"\nApplying {len(ops)} operations:")
print(f"  ZATCA × {len(ZATCA_CAMPS)}: {len(by_name_exclude)} excludes + {len(by_name_observe)} observes per campaign")
print(f"  Brand × {len(BRAND_CAMPS)}: {len(by_name_observe)} observes per campaign")

try:
    r = cc_svc.mutate_campaign_criteria(customer_id=ACCOUNT, operations=ops)
    print(f"\n✅ added {len(r.results)} associations")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:8]:
        print(f"  ❌ {m}")
