"""Check if hsa_cam/hsa_grp/hsa_ad land inside any URL-tracking property on
recent Google Ads contacts. If yes, we can extract them via REGEXP without
asking HubSpot to add new mapping fields."""
import os, sys, requests, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}"}
BASE = "https://api.hubapi.com"

# Pull 5 recent Google Ads leads
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "lead_utm_source", "operator": "EQ", "value": "google"},
    ]}],
    "properties": ["lead_utm_campaign"],
    "limit": 5,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/0-136/search",
                  headers={**H, "Content-Type": "application/json"},
                  json=body, timeout=30)
r.raise_for_status()
leads = r.json().get("results", [])

# URL-storing properties we want to inspect on the associated Contact
URL_PROPS = [
    "hs_analytics_first_url",
    "hs_analytics_last_url",
    "hs_analytics_first_referrer",
    "hs_analytics_last_referrer",
    "hs_latest_source_data_1",
    "hs_latest_source_data_2",
    "hs_analytics_source_data_1",
    "hs_analytics_source_data_2",
    "hs_analytics_first_visit_timestamp",  # not URL but useful context
]

# Track which URL fields contain hsa_*
hits = {p: 0 for p in URL_PROPS}
total = 0

for lead in leads:
    lead_id = lead["id"]
    print(f"\n--- Lead {lead_id} (utm_campaign={lead['properties'].get('lead_utm_campaign')}) ---")
    a_r = requests.get(f"{BASE}/crm/v4/objects/0-136/{lead_id}/associations/0-1",
                       headers=H, timeout=30)
    results = a_r.json().get("results", [])
    if not results:
        print("  [no contact assoc]")
        continue
    cid = results[0]["toObjectId"]
    c_r = requests.get(
        f"{BASE}/crm/v3/objects/contacts/{cid}?properties={','.join(URL_PROPS)}",
        headers=H, timeout=30)
    if c_r.status_code != 200:
        print(f"  [contact fetch err]")
        continue
    cp = c_r.json().get("properties", {})
    total += 1
    print(f"  Contact {cid}:")
    for prop in URL_PROPS:
        val = cp.get(prop)
        if not val:
            continue
        # Truncate very long URLs
        short = val if len(val) <= 200 else val[:200] + "..."
        has_hsa = "hsa_cam" in val
        marker = " <-- HAS hsa_cam!" if has_hsa else ""
        print(f"    {prop:38s} = {short}{marker}")
        if has_hsa:
            hits[prop] += 1
            # Extract the hsa values
            for param in ("hsa_cam", "hsa_grp", "hsa_ad", "hsa_kw", "hsa_mt"):
                m = re.search(rf"{param}=([^&\s]+)", val)
                if m:
                    print(f"        -> {param}={m.group(1)}")

print(f"\n{'='*60}\nSUMMARY: hsa_cam found in URL fields ({total} contacts checked)")
for prop, n in hits.items():
    if n > 0:
        print(f"  {prop:38s}  {n}/{total} contacts")
