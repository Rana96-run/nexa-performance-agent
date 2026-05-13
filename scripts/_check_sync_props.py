"""
Check the new sync properties on HubSpot Lead Module:
lead_campaign_id_sync, lead_adgroup_id_sync, lead_ad_id_sync
"""
import sys, os, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
BASE  = "https://api.hubapi.com"
LEAD_OBJ = "0-136"

SYNC_PROPS = ["lead_campaign_id_sync", "lead_adgroup_id_sync", "lead_ad_id_sync"]

# Sample TikTok leads
print("=== TikTok Ads leads ===")
r = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Tiktok Ads"},
        ]}],
        "properties": SYNC_PROPS + ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content"],
        "limit": 3,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
r.raise_for_status()
for lead in r.json().get("results", []):
    p = lead["properties"]
    print(f"  Lead {lead['id']}")
    for k in SYNC_PROPS + ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content"]:
        print(f"    {k:30s} = {p.get(k)!r}")

# Sample Meta leads
print("\n=== Meta Ads leads ===")
r2 = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Meta Ads"},
        ]}],
        "properties": SYNC_PROPS + ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content"],
        "limit": 3,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
r2.raise_for_status()
for lead in r2.json().get("results", []):
    p = lead["properties"]
    print(f"  Lead {lead['id']}")
    for k in SYNC_PROPS + ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content"]:
        print(f"    {k:30s} = {p.get(k)!r}")

# Sample Google Ads leads
print("\n=== Google Ads leads ===")
r3 = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Google Ads"},
        ]}],
        "properties": SYNC_PROPS + ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content"],
        "limit": 2,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
r3.raise_for_status()
for lead in r3.json().get("results", []):
    p = lead["properties"]
    print(f"  Lead {lead['id']}")
    for k in SYNC_PROPS + ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content"]:
        print(f"    {k:30s} = {p.get(k)!r}")
