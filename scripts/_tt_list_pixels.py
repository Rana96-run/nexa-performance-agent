"""List TikTok pixels for the advertiser to find the numeric pixel_id."""
import os, sys, json, urllib.request
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from dotenv import load_dotenv
load_dotenv()

TOKEN  = os.getenv("TIKTOK_ACCESS_TOKEN")
ADV_ID = os.getenv("TIKTOK_AD_ACCOUNT_2024")

url = f"https://business-api.tiktok.com/open_api/v1.3/pixel/list/?advertiser_id={ADV_ID}&page_size=20"
req = urllib.request.Request(url, headers={"Access-Token": TOKEN})
r = urllib.request.urlopen(req, timeout=15)
data = json.loads(r.read().decode("utf-8"))

print(f"HTTP {r.status}")
if data.get("code") != 0:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(1)

pixels = data.get("data", {}).get("pixels", [])
print(f"\n{len(pixels)} pixel(s):")
for p in pixels:
    print(f"  pixel_id={p.get('pixel_id')}  pixel_code={p.get('pixel_code')}  name={p.get('pixel_name')}  status={p.get('pixel_status')}")
    events = p.get("pixel_events") or []
    if events:
        print(f"    events: {[e.get('event_type') for e in events]}")
