"""Verify all BROAD keywords are present and ENABLED."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

TARGETS = [
    ("1513020554", "23861837000", "Acc 1 FinancialStatement"),
    ("5753494964", "23870151040", "Acc 2 FinancialStatement"),
    ("5753494964", "23865711095", "Acc 2 ZATCAPhase2"),
]
client = get_client()
ga = client.get_service("GoogleAdsService")

for acct, cid, label in TARGETS:
    print(f"\n=== {label} ===")
    for r in ga.search(customer_id=acct, query=f"""
        SELECT ad_group.name,
               ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.status
        FROM ad_group_criterion
        WHERE campaign.id = {cid}
          AND ad_group_criterion.type = 'KEYWORD'
          AND ad_group_criterion.keyword.match_type = 'BROAD'
          AND ad_group_criterion.negative = FALSE
          AND ad_group_criterion.status != 'REMOVED'
    """):
        kw = r.ad_group_criterion.keyword.text
        st = r.ad_group_criterion.status.name
        print(f"  [BROAD/{st}] {kw}  ({r.ad_group.name})")
