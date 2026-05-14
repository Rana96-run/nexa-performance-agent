"""Pull a few recent Google-Ads leads from HubSpot directly and dump ALL their
drilldown / traffic_source property values. Verify the property names work."""
import os, sys, requests, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# First check: do these properties exist on Lead Module?
r = requests.get("https://api.hubapi.com/crm/v3/properties/0-136", headers=H, timeout=30)
props = {p["name"]: p.get("label") for p in r.json().get("results", [])}
candidates = [
    "lead_original_traffic_source",
    "lead_latest_traffic_source",
    "lead_original_traffic_source_drilldown_1",
    "lead_latest_traffic_source_drilldown_1",
    "lead_original_traffic_source_drilldown_2",
    "lead_latest_traffic_source_drilldown_2",
    "hs_analytics_source",
    "hs_analytics_source_data_1",
    "hs_analytics_source_data_2",
    "hs_latest_source",
    "hs_latest_source_data_1",
    "hs_latest_source_data_2",
]
print("=== Property existence check on Lead Module ===")
for n in candidates:
    if n in props:
        print(f"  ✓ {n:55s} ({props[n]})")
    else:
        print(f"  ✗ {n} NOT FOUND")

# Now sample 5 recent leads
print("\n=== Sample 5 Google leads with their drilldown values ===")
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=72)).timestamp() * 1000))

body = {
    "filterGroups": [{"filters": [
        {"propertyName": "lead_utm_source", "operator": "EQ", "value": "google"},
        {"propertyName": "hs_createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": [n for n in candidates if n in props],
    "limit": 5,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
}
r = requests.post("https://api.hubapi.com/crm/v3/objects/0-136/search", headers=H, json=body, timeout=30)
leads = r.json().get("results", [])
for ld in leads:
    p = ld["properties"]
    print(f"\nLead {ld['id']}:")
    for n in candidates:
        if n in props:
            v = p.get(n)
            mark = "  " if v else "× "
            print(f"  {mark}{n:55s} = {v}")
