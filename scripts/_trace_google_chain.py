"""Trace one Google contact with campaign_id populated → associated Lead →
verify if lead_campaign_id_sync is set. This isolates whether the calculated
property is firing for Google contacts the same way it does for Meta/Snap."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# Find a Google contact with campaign_id populated (last 72h)
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=72)).timestamp() * 1000))

body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_analytics_source", "operator": "EQ", "value": "PAID_SEARCH"},
        {"propertyName": "campaign_id", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": ["campaign_id", "ad_group_id", "ad_id", "createdate"],
    "limit": 3,
    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=H, json=body, timeout=30)
results = r.json().get("results", [])
print(f"Google contacts with campaign_id populated (last 72h): {len(results)}\n")

for ct in results:
    cid_id = ct["id"]
    cp = ct["properties"]
    print(f"━━━ Contact {cid_id} ━━━")
    print(f"  created      = {cp.get('createdate')}")
    print(f"  campaign_id  = {cp.get('campaign_id')}")
    print(f"  ad_group_id  = {cp.get('ad_group_id')}")
    print(f"  ad_id        = {cp.get('ad_id')}")

    # Find associated Lead
    a_r = requests.get(f"{BASE}/crm/v4/objects/0-1/{cid_id}/associations/0-136",
                       headers=H, timeout=30)
    aresults = a_r.json().get("results", [])
    if not aresults:
        print("  [no Lead Module association — that's why BQ doesn't see it]")
        continue
    lid = aresults[0]["toObjectId"]
    l_r = requests.get(
        f"{BASE}/crm/v3/objects/0-136/{lid}"
        f"?properties=lead_campaign_id_sync,lead_adgroup_id_sync,lead_ad_id_sync,hs_createdate",
        headers=H, timeout=30,
    )
    lp = l_r.json().get("properties", {})
    print(f"  → Lead {lid}:")
    print(f"    hs_createdate         = {lp.get('hs_createdate')}")
    print(f"    lead_campaign_id_sync = {lp.get('lead_campaign_id_sync')}")
    print(f"    lead_adgroup_id_sync  = {lp.get('lead_adgroup_id_sync')}")
    print(f"    lead_ad_id_sync       = {lp.get('lead_ad_id_sync')}")
    if lp.get('lead_campaign_id_sync') == cp.get('campaign_id'):
        print(f"  ✓ MATCH")
    else:
        print(f"  ✗ MISMATCH — calculated property not firing for Google?")
    print()
