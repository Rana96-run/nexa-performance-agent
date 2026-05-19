"""Check policy status of sitelinks/extensions for the Qawaem campaign."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23861837000"

c = get_client(); ga = c.get_service("GoogleAdsService")

# Asset policy summary at campaign level
q = f"""
SELECT campaign.id,
       campaign_asset.field_type,
       asset.sitelink_asset.link_text,
       asset.callout_asset.callout_text,
       asset.structured_snippet_asset.header,
       asset.call_asset.phone_number,
       asset.policy_summary.approval_status,
       asset.policy_summary.policy_topic_entries
FROM campaign_asset
WHERE campaign.id = {CAMP_ID}
  AND campaign_asset.status = 'ENABLED'
"""
by_status = {"APPROVED": 0, "APPROVED_LIMITED": 0, "DISAPPROVED": 0, "UNDER_REVIEW": 0}
disapproved = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    a = r.asset
    label = (a.sitelink_asset.link_text or a.callout_asset.callout_text
             or a.structured_snippet_asset.header or a.call_asset.phone_number or "?")
    status = a.policy_summary.approval_status.name
    by_status[status] = by_status.get(status, 0) + 1
    if status in ("DISAPPROVED", "UNDER_REVIEW"):
        topics = [t.topic for t in a.policy_summary.policy_topic_entries]
        disapproved.append((r.campaign_asset.field_type.name, label, status, topics))

print("Asset approval breakdown:")
for s, n in by_status.items():
    print(f"  {s}: {n}")

if disapproved:
    print("\nProblematic assets:")
    for ft, lbl, status, topics in disapproved:
        print(f"  [{status}] {ft}: {lbl}  topics={topics}")
else:
    print("\n  ✅ no disapproved or under-review assets — all clean")
