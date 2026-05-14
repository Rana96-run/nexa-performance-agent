"""Check a recent Google Ads lead — does the associated Contact have campaign_id /
ad_group_id populated from hsa_cam / hsa_grp? If yes, we can wire them through
to the Lead Module via either a HubSpot workflow OR a collector-side join."""
import os, sys, requests, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}"}
BASE = "https://api.hubapi.com"

# Pull 5 recent Google Ads leads from the Lead Module
since_ms = "1762000000000"  # ~recent enough
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "lead_utm_source", "operator": "EQ", "value": "google"},
        {"propertyName": "hs_createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": ["lead_utm_campaign", "lead_utm_audience", "lead_utm_content",
                   "lead_campaign_id_sync", "lead_adgroup_id_sync", "lead_ad_id_sync",
                   "lead_google_ad_click_id"],
    "limit": 5,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/0-136/search", headers={**H, "Content-Type": "application/json"}, json=body, timeout=30)
r.raise_for_status()
leads = r.json().get("results", [])
print(f"Pulled {len(leads)} recent Google Ads leads from Lead Module:\n")

for lead in leads:
    p = lead.get("properties", {})
    lead_id = lead["id"]
    print(f"Lead {lead_id}:")
    print(f"  utm_campaign     = {p.get('lead_utm_campaign')}")
    print(f"  utm_audience     = {p.get('lead_utm_audience')}")
    print(f"  campaign_id_sync = {p.get('lead_campaign_id_sync')}")
    print(f"  adgroup_id_sync  = {p.get('lead_adgroup_id_sync')}")
    print(f"  ad_id_sync       = {p.get('lead_ad_id_sync')}")
    print(f"  google_click_id  = {p.get('lead_google_ad_click_id')}")

    # Get associated Contact
    assoc_r = requests.get(
        f"{BASE}/crm/v4/objects/0-136/{lead_id}/associations/0-1",
        headers=H, timeout=30)
    if assoc_r.status_code != 200:
        print(f"  [no contact association]\n")
        continue
    results = assoc_r.json().get("results", [])
    if not results:
        print(f"  [no contact association]\n")
        continue
    contact_id = results[0]["toObjectId"]

    # Fetch Contact properties
    c_r = requests.get(
        f"{BASE}/crm/v3/objects/contacts/{contact_id}"
        f"?properties=campaign_id,ad_group_id,hs_google_click_id,msclkid,hs_bing_click_id",
        headers=H, timeout=30)
    if c_r.status_code != 200:
        print(f"  [contact fetch failed]\n")
        continue
    cp = c_r.json().get("properties", {})
    print(f"  Contact {contact_id}:")
    print(f"    campaign_id      = {cp.get('campaign_id')}      <-- from hsa_cam")
    print(f"    ad_group_id      = {cp.get('ad_group_id')}      <-- from hsa_grp")
    print(f"    hs_google_click_id = {cp.get('hs_google_click_id')}")
    print(f"    msclkid (MS)     = {cp.get('msclkid')}")
    print(f"    hs_bing_click_id = {cp.get('hs_bing_click_id')}")
    print()
