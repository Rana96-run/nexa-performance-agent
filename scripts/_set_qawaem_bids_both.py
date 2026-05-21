"""Apply bid settings on both accounts' FinancialStatement campaigns:
  Acc 1: campaign CPC ceiling → $4.00, ad-group default CPC → 0 (no override)
  Acc 2: campaign CPC ceiling → 0 (no limit),  ad-group default CPC → 0

# KPI-RULE-BYPASS — bid adjustment, not SQL-leads analysis.
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.protobuf import field_mask_pb2
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "23861837000", 4_000_000, "Acc 1"),   # $4 ceiling
    ("5753494964", "23870151040",         0, "Acc 2"),   # no ceiling
]

client = get_client()


def mask(*p): return field_mask_pb2.FieldMask(paths=list(p))


for acct, cid, ceiling, label in TARGETS:
    print(f"\n=== {label} ({acct}) campaign {cid} ===")
    csvc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.update.resource_name = f"customers/{acct}/campaigns/{cid}"
    op.update.target_spend.cpc_bid_ceiling_micros = ceiling
    client.copy_from(op.update_mask, mask("target_spend.cpc_bid_ceiling_micros"))
    try:
        r = csvc.mutate_campaigns(customer_id=acct, operations=[op])
        print(f"  ✅ campaign ceiling → ${ceiling/1e6:.2f}" +
              ("  (no limit)" if ceiling == 0 else ""))
    except Exception as e:
        print(f"  ❌ campaign update: {str(e)[:300]}")
        continue

    # Ad groups: clear default max CPC (set to 0 — no override)
    ag_svc = client.get_service("AdGroupService")
    ga = client.get_service("GoogleAdsService")
    ag_ops = []
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.resource_name, ad_group.name
        FROM ad_group WHERE campaign.id = {cid}
    """):
        ag_op = client.get_type("AdGroupOperation")
        ag_op.update.resource_name = r.ad_group.resource_name
        ag_op.update.cpc_bid_micros = 0
        client.copy_from(ag_op.update_mask, mask("cpc_bid_micros"))
        ag_ops.append((ag_op, r.ad_group.name))

    for ag_op, name in ag_ops:
        try:
            ag_svc.mutate_ad_groups(customer_id=acct, operations=[ag_op])
            print(f"  ✅ {name}: default max CPC cleared (0)")
        except Exception as e:
            print(f"  ❌ {name}: {str(e)[:300]}")

print("\n--- Verify ---")
ga = client.get_service("GoogleAdsService")
for acct, cid, _, label in TARGETS:
    print(f"\n{label}:")
    for r in ga.search(customer_id=acct, query=f"""
        SELECT campaign.target_spend.cpc_bid_ceiling_micros
        FROM campaign WHERE campaign.id = {cid}
    """):
        c = r.campaign.target_spend.cpc_bid_ceiling_micros / 1e6
        print(f"  campaign ceiling: ${c:.2f}" + ("  (no limit)" if c == 0 else ""))
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.name, ad_group.cpc_bid_micros
        FROM ad_group WHERE campaign.id = {cid}
    """):
        print(f"  {r.ad_group.name:<26} default_max_cpc=${r.ad_group.cpc_bid_micros/1e6:.2f}")
