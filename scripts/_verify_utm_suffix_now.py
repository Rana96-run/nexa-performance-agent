"""Verify the actual UTM suffix state on critical campaigns."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

client = get_client(); ga = client.get_service("GoogleAdsService")
q = """
SELECT campaign.id, campaign.name, campaign.final_url_suffix
FROM campaign
WHERE campaign.id IN (23851270716, 23861101390, 23861965426, 23861837000)
"""
for r in ga.search(customer_id="1513020554", query=q):
    suffix = r.campaign.final_url_suffix or "(empty)"
    print(f"{r.campaign.name}")
    print(f"  len    : {len(r.campaign.final_url_suffix or '')}")
    print(f"  preview: {suffix[:120]}")
    print()
