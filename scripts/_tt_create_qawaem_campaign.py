"""Create the Qawaem WebForm campaign on TikTok (Account 2024).

Builds the campaign + ad group via TikTok Business API v1.3.
Skips ad creation — that requires uploaded creative assets (video/image
uploaded to TikTok Creative Library). User adds creatives in UI after.

Mirrors the planned spec:
  - Campaign: WEB_CONVERSIONS objective (NOT LEAD_GENERATION — that's
    for in-app instant forms; WebForm means website conversion)
  - Ad group: $50/d, Saudi only, AR, iOS+Android, age 25-55, optimize for
    CompleteRegistration via the web pixel CSAM5QRC77U0GMM8R160
"""
import sys, os, json, time
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from dotenv import load_dotenv
import urllib.request

load_dotenv()

TOKEN     = os.getenv("TIKTOK_ACCESS_TOKEN")
ADV_ID    = os.getenv("TIKTOK_AD_ACCOUNT_2024")
PIXEL_ID  = "7427949599597379592"   # numeric pixel_id for 'Qoyod 2024' (code: CSAM5QRC77U0GMM8R160)
BASE      = "https://business-api.tiktok.com/open_api/v1.3"

# Campaign already exists from prior partial run — reuse it
EXISTING_CAMPAIGN_ID = "1865704232893537"


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


# ── 1. Campaign already created — reuse ────────────────────────────────
campaign_id = EXISTING_CAMPAIGN_ID
print(f"1. Reusing existing campaign: {campaign_id}")


# ── 2. Create ad group ────────────────────────────────────────────────────
print("\n2. Create ad group")
# Schedule: now → 30 days out (TikTok needs explicit times)
start_ts = int(time.time())
end_ts   = start_ts + 30 * 24 * 3600

ag_body = {
    "advertiser_id":   ADV_ID,
    "campaign_id":     campaign_id,
    "adgroup_name":    "Qawaem_AR_iOS_Android",
    "promotion_type":  "WEBSITE",
    "placement_type":  "PLACEMENT_TYPE_AUTOMATIC",
    # Geo + language + device
    "location_ids":    ["102358"],   # Saudi Arabia in TikTok geo
    "languages":       ["ar"],
    "age_groups":      ["AGE_25_34", "AGE_35_44", "AGE_45_54", "AGE_55_100"],
    "gender":          "GENDER_UNLIMITED",
    "operating_systems": ["IOS", "ANDROID"],
    # Budget + schedule
    "budget_mode":     "BUDGET_MODE_DAY",
    "budget":          50.00,
    "schedule_type":   "SCHEDULE_START_END",
    "schedule_start_time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(start_ts)),
    "schedule_end_time":   time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(end_ts)),
    # Pixel + optimization
    "pixel_id":        PIXEL_ID,
    "optimization_event": "FORM",   # the form-submit event configured on this pixel
    "optimization_goal":  "CONVERT",
    "billing_event":      "OCPM",
    "bid_type":           "BID_TYPE_NO_BID",   # lowest-cost auto
    "pacing":             "PACING_MODE_SMOOTH",
    "operation_status":   "DISABLE",
}

res2 = post("/adgroup/create/", ag_body)
print(json.dumps(res2, ensure_ascii=False, indent=2)[:1500])
if res2.get("code") != 0:
    print(f"\n❌ ad group create failed: {res2.get('message')}")
    sys.exit(1)

adgroup_id = res2["data"]["adgroup_id"]
print(f"\n✅ adgroup_id = {adgroup_id}")

print("\n" + "=" * 70)
print("DONE — TikTok WebForm Qawaem campaign skeleton live")
print("=" * 70)
print(f"  campaign_id  : {campaign_id}")
print(f"  adgroup_id   : {adgroup_id}")
print(f"  Status       : DISABLED (PAUSED on TikTok)")
print(f"  Budget       : $50/day at ad-group level")
print(f"  Pixel + event: {PIXEL} / ON_WEB_REGISTER")
print()
print("MANUAL NEXT STEP (in TikTok Ads Manager):")
print("  Add ads to the ad group with creative video + LP url")
print("  → 3 creative variants per the spec (director liability, deadline, easy)")
print("  → LP: https://lp.qoyod.com/qawaem/")
