"""See every system_serving_status on C3 keywords."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

c = get_client(); ga = c.get_service("GoogleAdsService")

q = """
SELECT ad_group.name,
       ad_group_criterion.keyword.text,
       ad_group_criterion.status,
       ad_group_criterion.system_serving_status,
       ad_group_criterion.approval_status,
       ad_group_criterion.negative
FROM ad_group_criterion
WHERE campaign.id = 23861965426
  AND ad_group_criterion.type = 'KEYWORD'
  AND ad_group_criterion.status != 'REMOVED'
ORDER BY ad_group.name
"""
for r in ga.search(customer_id="1513020554", query=q):
    if r.ad_group_criterion.negative: continue
    print(f"  [{r.ad_group_criterion.status.name:<8}] "
          f"[{r.ad_group_criterion.system_serving_status.name:<20}] "
          f"[{r.ad_group_criterion.approval_status.name:<15}] "
          f"{r.ad_group_criterion.keyword.text}")
