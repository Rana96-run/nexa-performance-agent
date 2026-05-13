"""
List all HubSpot Lead Module properties related to ad tracking
to find where hsa_grp / hsa_ad / hsa_cam values land.
"""
import sys, os, requests
sys.path.insert(0, ".")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
BASE  = "https://api.hubapi.com"
LEAD_OBJ = "0-136"

# Get all properties on the Lead Module
r = requests.get(
    f"{BASE}/crm/v3/properties/{LEAD_OBJ}",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
r.raise_for_status()
props = r.json().get("results", [])

# Filter for ad / campaign / hsa / google related properties
keywords = ["campaign", "ad_", "hsa", "google", "click", "gclid", "adgroup", "ad_id", "ad_group"]
print(f"Total lead module properties: {len(props)}")
print("\nAd-tracking related:")
for p in sorted(props, key=lambda x: x["name"]):
    name = p["name"].lower()
    if any(k in name for k in keywords):
        print(f"  {p['name']:50s}  ({p['type']}) — {p.get('label','')}")

# Also check a recent TikTok lead to see what's actually populated
print("\n=== Sample recent TikTok lead properties ===")
r2 = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Tiktok Ads"},
        ]}],
        "properties": ["campaign_id", "ad_group_id", "ad_id", "lead_utm_campaign",
                       "lead_utm_audience", "lead_utm_content"],
        "limit": 3,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
for lead in r2.json().get("results", []):
    p = lead["properties"]
    print(f"  campaign_id={p.get('campaign_id')}  ad_group_id={p.get('ad_group_id')}  ad_id={p.get('ad_id')}")
    print(f"  utm_campaign={p.get('lead_utm_campaign')}  utm_audience={p.get('lead_utm_audience')}")

# Check a recent Google Ads lead
print("\n=== Sample recent Google Ads lead properties ===")
r3 = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Google Ads"},
        ]}],
        "properties": ["campaign_id", "ad_group_id", "ad_id", "lead_utm_campaign",
                       "lead_utm_audience", "lead_utm_content"],
        "limit": 3,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
for lead in r3.json().get("results", []):
    p = lead["properties"]
    print(f"  campaign_id={p.get('campaign_id')}  ad_group_id={p.get('ad_group_id')}  ad_id={p.get('ad_id')}")
    print(f"  utm_campaign={p.get('lead_utm_campaign')}  utm_audience={p.get('lead_utm_audience')}")
