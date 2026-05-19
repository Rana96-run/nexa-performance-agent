"""Inspect what fields the Campaign object exposes via the bingads SDK."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.microsoft_ads import get_service

svc = get_service("CampaignManagementService")
camp = svc.factory.create("Campaign")
print("Campaign fields:")
for attr in sorted(set(dir(camp)) - set(dir(object))):
    if not attr.startswith("_"):
        val = getattr(camp, attr)
        print(f"  {attr:<35} = {repr(val)[:80]}")
