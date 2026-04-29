"""
Phase 1 — Creative library access test.
Run from repo root: python scripts/test_creative_library.py
"""
import sys
sys.path.insert(0, r"D:\Nexa Performance Agent")

from dotenv import load_dotenv
load_dotenv(override=True)

results = {}
for channel, fn in [
    ("meta",       lambda: __import__("executors.meta",      fromlist=["list_creatives"]).list_creatives()),
    ("tiktok",     lambda: __import__("executors.tiktok",    fromlist=["list_creatives"]).list_creatives()),
    ("snapchat",   lambda: __import__("executors.snapchat",  fromlist=["list_creatives"]).list_creatives()),
    ("linkedin",   lambda: __import__("executors.linkedin",  fromlist=["list_creatives"]).list_creatives()),
    ("google_ads", lambda: __import__("executors.google_ads",fromlist=["list_creatives"]).list_creatives()),
]:
    try:
        items = fn()
        results[channel] = {"ok": True, "count": len(items), "sample": items[:2]}
    except Exception as e:
        results[channel] = {"ok": False, "error": str(e)}

import json
print(json.dumps(results, indent=2, default=str))
