"""Find what value hs_analytics_source_data_1 actually holds for Google
Ads contacts. Earlier verify_google_id_flow used 'google' (lowercase) and
got 0 matches — find the right value."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# Pull 20 recent contacts that have hs_google_click_id set (= clicked Google ad)
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=72)).timestamp() * 1000))

body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_google_click_id", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": [
        "createdate", "email",
        "hs_analytics_source", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
        "campaign_id", "ad_group_id", "ad_id",
    ],
    "limit": 20,
    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=H, json=body, timeout=30)
results = r.json().get("results", [])
print(f"Recent Google-click contacts (with gclid, last 72h): {len(results)}\n")

from collections import Counter
source_values = Counter()
src_data_values = Counter()
populated = 0
for ct in results:
    p = ct["properties"]
    src = p.get("hs_analytics_source", "NULL")
    sd1 = p.get("hs_analytics_source_data_1", "NULL")
    source_values[src] += 1
    src_data_values[sd1] += 1
    if p.get("campaign_id"):
        populated += 1

print("hs_analytics_source distinct values:")
for v, n in source_values.most_common():
    print(f"  {n:3d}×  '{v}'")
print("\nhs_analytics_source_data_1 distinct values:")
for v, n in src_data_values.most_common():
    print(f"  {n:3d}×  '{v}'")

print(f"\n{populated}/{len(results)} have campaign_id populated")

# Show 3 examples with details
print("\nExamples:")
for ct in results[:3]:
    p = ct["properties"]
    print(f"  Contact {ct['id']}: source='{p.get('hs_analytics_source')}'  "
          f"src1='{p.get('hs_analytics_source_data_1')}'  cid={p.get('campaign_id') or '—'}")
