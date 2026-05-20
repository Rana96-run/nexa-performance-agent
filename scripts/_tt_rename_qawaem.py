"""Rename the TikTok Qawaem campaign to follow established convention.

Old: Tiktok_WebForm_AR_Qawaem236
New: Tiktok_Conversion_Prospecting_Interests_FinancialStatemnt_Websiteform

Matches existing TikTok portfolio naming pattern:
  Tiktok_{Type}_{Audience descriptors}_{Product}_{Format}
"""
import sys, os, json, urllib.request, urllib.error
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from dotenv import load_dotenv
load_dotenv()

TOKEN  = os.getenv("TIKTOK_ACCESS_TOKEN")
ADV_ID = os.getenv("TIKTOK_AD_ACCOUNT_2024")
BASE   = "https://business-api.tiktok.com/open_api/v1.3"

CAMP_ID = "1865704232893537"
AG_ID   = "1865704444794050"

NEW_CAMP_NAME = "Tiktok_Conversion_Prospecting_Interests_FinancialStatemnt_Websiteform"
NEW_AG_NAME   = "Prospecting_Interests_iOS_Android_AR"


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Access-Token": TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


print("1. Rename campaign")
r = post("/campaign/update/", {
    "advertiser_id": ADV_ID,
    "campaign_id":   CAMP_ID,
    "campaign_name": NEW_CAMP_NAME,
})
if r.get("code") == 0:
    print(f"   ✅ campaign renamed → {NEW_CAMP_NAME}")
else:
    print(f"   ❌ {r.get('message')}")

print("\n2. Rename ad group")
r2 = post("/adgroup/update/", {
    "advertiser_id": ADV_ID,
    "adgroup_id":    AG_ID,
    "adgroup_name":  NEW_AG_NAME,
})
if r2.get("code") == 0:
    print(f"   ✅ ad group renamed → {NEW_AG_NAME}")
else:
    print(f"   ❌ {r2.get('message')}")
