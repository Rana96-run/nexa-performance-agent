"""Clean up paused experimental RSAs from the 4 Qawaem ad groups.
Keeps only the v2 production ad + 1 original ad per ad group."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

# (account, camp_id)
CAMPS = [("1513020554", "23861837000"), ("5753494964", "23870151040")]

# v2 production ads to KEEP
V2_PRODUCTION_IDS = {
    "809536878672",  # Acc 1 AR v2
    "809536882206",  # Acc 1 EN v2
    "809652538922",  # Acc 2 AR v2
    "809573209408",  # Acc 2 EN v2
}

client = get_client()
ga = client.get_service("GoogleAdsService")
svc = client.get_service("AdGroupAdService")

for acct, cid in CAMPS:
    print(f"\n=== Acc {acct} ===")
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.name, ad_group_ad.ad.id, ad_group_ad.resource_name,
               ad_group_ad.status
        FROM ad_group_ad
        WHERE campaign.id = {cid}
          AND ad_group_ad.status = 'PAUSED'
    """):
        ad_id = str(r.ad_group_ad.ad.id)
        if ad_id in V2_PRODUCTION_IDS:
            continue   # safety, shouldn't be paused but skip if so
        op = client.get_type("AdGroupAdOperation")
        op.remove = r.ad_group_ad.resource_name
        try:
            svc.mutate_ad_group_ads(customer_id=acct, operations=[op])
            print(f"  ⊘ removed PAUSED ad {ad_id} ({r.ad_group.name})")
        except Exception as e:
            print(f"  ❌ {ad_id}: {str(e)[:200]}")

# Verify
print("\n--- Final ad counts ---")
for acct, cid in CAMPS:
    print(f"\nAcc {acct}:")
    counts = {}
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.name, ad_group_ad.ad.id, ad_group_ad.status
        FROM ad_group_ad
        WHERE campaign.id = {cid}
          AND ad_group_ad.status != 'REMOVED'
    """):
        ag = r.ad_group.name
        counts.setdefault(ag, {"E":0,"P":0})
        if r.ad_group_ad.status.name == "ENABLED": counts[ag]["E"] += 1
        else: counts[ag]["P"] += 1
    for ag, c in counts.items():
        print(f"  {ag:<24}  ENABLED={c['E']}  PAUSED={c['P']}")
