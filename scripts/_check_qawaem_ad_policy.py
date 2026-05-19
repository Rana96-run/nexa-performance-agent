"""Check the policy review status of the Qawaem RSAs."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23861837000"

c = get_client(); ga = c.get_service("GoogleAdsService")
q = f"""
SELECT ad_group.name,
       ad_group_ad.ad.id,
       ad_group_ad.status,
       ad_group_ad.policy_summary.review_status,
       ad_group_ad.policy_summary.approval_status,
       ad_group_ad.policy_summary.policy_topic_entries,
       ad_group_ad.ad.final_urls
FROM ad_group_ad
WHERE campaign.id = {CAMP_ID} AND ad_group_ad.status != 'REMOVED'
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    print(f"\n{r.ad_group.name}  (ad_id={r.ad_group_ad.ad.id})")
    print(f"  ad_status        : {r.ad_group_ad.status.name}")
    print(f"  review_status    : {r.ad_group_ad.policy_summary.review_status.name}")
    print(f"  approval_status  : {r.ad_group_ad.policy_summary.approval_status.name}")
    urls = list(r.ad_group_ad.ad.final_urls)
    print(f"  final_url        : {urls[0] if urls else '(none)'}")
    topics = list(r.ad_group_ad.policy_summary.policy_topic_entries)
    if topics:
        print(f"  policy_topics:")
        for t in topics:
            print(f"     - type={t.type_.name}  topic={t.topic}")
    else:
        print(f"  policy_topics    : (none — clean)")
