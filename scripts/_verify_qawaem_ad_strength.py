"""Verify Ad Strength rating on all 4 newly-created Qawaem RSAs."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ADS = [
    ("1513020554", "809536878672", "Acc 1 AR v2"),
    ("1513020554", "809536882206", "Acc 1 EN v2"),
    ("5753494964", "809652538922", "Acc 2 AR v2"),
    ("5753494964", "809573209408", "Acc 2 EN v2"),
]

client = get_client()
ga = client.get_service("GoogleAdsService")

for acct, ad_id, label in ADS:
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.ad_strength,
               ad_group_ad.policy_summary.approval_status
        FROM ad_group_ad WHERE ad_group_ad.ad.id = {ad_id}
    """):
        a = r.ad_group_ad
        print(f"  {label:<12} ad_strength={a.ad_strength.name:<10} "
              f"approval={a.policy_summary.approval_status.name}")
