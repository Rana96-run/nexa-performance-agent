"""Verify TikTok Business API access token works on advertiser 2024."""
import sys, os, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from dotenv import load_dotenv
import urllib.request

load_dotenv()

TOKEN     = os.getenv("TIKTOK_ACCESS_TOKEN")
ADV_ID    = os.getenv("TIKTOK_AD_ACCOUNT_2024")
BASE      = "https://business-api.tiktok.com/open_api/v1.3"

url = f"{BASE}/advertiser/info/?advertiser_ids=[%22{ADV_ID}%22]&fields=[%22name%22,%22status%22,%22currency%22,%22timezone%22,%22country%22]"
req = urllib.request.Request(url, headers={"Access-Token": TOKEN})
r = urllib.request.urlopen(req, timeout=15)
data = json.loads(r.read().decode("utf-8"))
print(f"HTTP {r.status}")
print(json.dumps(data, ensure_ascii=False, indent=2))
