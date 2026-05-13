"""
Deep-inspect a recent TikTok lead to see ALL populated properties.
"""
import sys, os, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
BASE  = "https://api.hubapi.com"
LEAD_OBJ = "0-136"

# Get ALL properties of a recent TikTok lead
r = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Tiktok Ads"},
        ]}],
        "properties": [
            "campaign_id", "ad_group_id", "ad_id",
            "lead_utm_campaign", "lead_utm_audience", "lead_utm_content",
            "lead_ttclid", "lead_campaign_id_sync",
            "hs_lead_source_drill_down_1", "hs_lead_source_drill_down_2",
            "lead_conversion_source_page", "lead_cta_source_url",
            "lead__first_page_seen",
        ],
        "limit": 2,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
r.raise_for_status()
for lead in r.json().get("results", []):
    print(f"\n--- TikTok Lead {lead['id']} ---")
    for k, v in sorted(lead["properties"].items()):
        print(f"  {k:45s} = {v!r}")

# Also check a Google Ads lead
print("\n\n=== Google Ads lead ===")
r2 = requests.post(
    f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": "Google Ads"},
        ]}],
        "properties": [
            "campaign_id", "ad_group_id", "ad_id",
            "lead_utm_campaign", "lead_utm_audience", "lead_utm_content",
            "lead_google_ad_click_id",
            "hs_lead_source_drill_down_1", "hs_lead_source_drill_down_2",
            "lead_conversion_source_page", "lead_cta_source_url",
            "lead__first_page_seen",
        ],
        "limit": 1,
        "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
    }
)
r2.raise_for_status()
for lead in r2.json().get("results", []):
    print(f"\n--- Google Lead {lead['id']} ---")
    for k, v in sorted(lead["properties"].items()):
        print(f"  {k:45s} = {v!r}")
