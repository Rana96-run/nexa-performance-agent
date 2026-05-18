"""Step 2: handle what step 1 couldn't.
  1. Create fresh non-shared budgets for C2 + C3 at the new amounts,
     swap them in, then the old shared budgets become orphans (auto-archive).
  2. Now-unshared → strip tCPA on C2/C3.
  3. Now-unshared → set selective_optimization on all 3.
  4. Archive OLD HubSpot - Lead via HIDDEN (not REMOVED).
"""
import sys, time
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

ACCOUNT = "1513020554"
HUBSPOT_LEAD_RN     = f"customers/{ACCOUNT}/conversionActions/7040304673"
OLD_HUBSPOT_LEAD_RN = f"customers/{ACCOUNT}/conversionActions/7037461117"

# Campaigns that need new non-shared budgets (C2 + C3 only — C1 is already non-shared)
SWAP_CAMPS = [
    {"id": "23861101390", "budget_usd": 80.0, "drop_tcpa": True},
    {"id": "23861965426", "budget_usd": 60.0, "drop_tcpa": True},
]

ALL_CAMPS = ["23851270716", "23861101390", "23861965426"]

client     = get_client()
camp_svc   = client.get_service("CampaignService")
budget_svc = client.get_service("CampaignBudgetService")
conv_svc   = client.get_service("ConversionActionService")
ga         = client.get_service("GoogleAdsService")


def mask(*paths):
    return field_mask_pb2.FieldMask(paths=list(paths))


def step(label, fn):
    print(f"\n=== {label} ===")
    try:
        fn()
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {str(e)[:400]}")


# ── 1. Create fresh non-shared budgets for C2 + C3 ─────────────────────────
new_budgets = {}
def s1():
    ops = []
    for c in SWAP_CAMPS:
        op = client.get_type("CampaignBudgetOperation")
        b  = op.create
        b.name              = f"Google_Search_AREN_ZATCA_{c['id']}_dedicated_{int(time.time())}"
        b.amount_micros     = int(c["budget_usd"] * 1_000_000)
        b.delivery_method   = client.enums.BudgetDeliveryMethodEnum.STANDARD
        b.explicitly_shared = False
        ops.append(op)
    r = budget_svc.mutate_campaign_budgets(customer_id=ACCOUNT, operations=ops)
    for c, res in zip(SWAP_CAMPS, r.results):
        new_budgets[c["id"]] = res.resource_name
        print(f"  ✅ {c['id']} → {res.resource_name}")
step("1. Create non-shared budgets for C2 + C3", s1)

# ── 2. Swap budgets on C2 + C3 ─────────────────────────────────────────────
def s2():
    ops = []
    for c in SWAP_CAMPS:
        op = client.get_type("CampaignOperation")
        op.update.resource_name        = f"customers/{ACCOUNT}/campaigns/{c['id']}"
        op.update.campaign_budget      = new_budgets[c["id"]]
        client.copy_from(op.update_mask, mask("campaign_budget"))
        ops.append(op)
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("2. Swap C2/C3 campaigns onto new budgets", s2)

# ── 3. Strip tCPA on C2/C3 ─────────────────────────────────────────────────
def s3():
    ops = []
    for c in SWAP_CAMPS:
        if not c["drop_tcpa"]: continue
        op = client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{c['id']}"
        op.update.maximize_conversions.target_cpa_micros = 0
        client.copy_from(op.update_mask, mask("maximize_conversions.target_cpa_micros"))
        ops.append(op)
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("3. Strip tCPA on C2 + C3", s3)

# ── 4. Set selective_optimization on all 3 ─────────────────────────────────
def s4():
    ops = []
    for cid in ALL_CAMPS:
        op = client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.update.selective_optimization.conversion_actions.append(HUBSPOT_LEAD_RN)
        client.copy_from(op.update_mask, mask("selective_optimization.conversion_actions"))
        ops.append(op)
    r = camp_svc.mutate_campaigns(customer_id=ACCOUNT, operations=ops)
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("4. Lock selective_optimization → HubSpot - Lead", s4)

# ── 5. Hide OLD HubSpot - Lead ─────────────────────────────────────────────
def s5():
    op = client.get_type("ConversionActionOperation")
    op.update.resource_name = OLD_HUBSPOT_LEAD_RN
    op.update.status        = client.enums.ConversionActionStatusEnum.HIDDEN
    client.copy_from(op.update_mask, mask("status"))
    r = conv_svc.mutate_conversion_actions(customer_id=ACCOUNT, operations=[op])
    for res in r.results: print(f"  ✅ {res.resource_name}")
step("5. Hide OLD HubSpot - Lead (HIDDEN, not REMOVED)", s5)

print("\nDONE — re-run audit")
