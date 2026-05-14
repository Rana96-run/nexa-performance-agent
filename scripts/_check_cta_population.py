"""Check 1) Does lead_cta_source exist on Contact object?
2) Are ANY leads in HubSpot populating lead_cta_source_url?
3) What's the difference between lead_cta_source_url and hs_analytics_first_url
   for leads that DO have the cta URL set?
"""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# 1. Check Contact for cta_source
print("=== 1. lead_cta_source / cta_source presence on Contact (0-1) ===")
r = requests.get(f"{BASE}/crm/v3/properties/0-1", headers=H, timeout=30)
contact_props = {p["name"]: p for p in r.json().get("results", [])}
for name in ("cta_source", "cta_source_url", "lead_cta_source", "lead_cta_source_url"):
    if name in contact_props:
        print(f"  ✓ {name} (Contact)")
# Also search any cta-related props
print("  Any property with 'cta' in name on Contact:")
for n in sorted(contact_props.keys()):
    if "cta" in n.lower():
        p = contact_props[n]
        print(f"     {n:35s}  ({p.get('type')})")

# 2. Find ANY lead that has lead_cta_source_url populated
print("\n=== 2. Search Lead Module for ANY lead with lead_cta_source_url populated ===")
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "lead_cta_source_url", "operator": "HAS_PROPERTY"},
    ]}],
    "properties": ["lead_cta_source_url", "lead_utm_source", "lead_utm_campaign", "hs_createdate"],
    "limit": 10,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/0-136/search", headers=H, json=body, timeout=30)
results = r.json().get("results", [])
total = r.json().get("total", 0)
print(f"  Total leads ever with lead_cta_source_url populated: {total}")
print(f"  Showing top 10 most recent:\n")
for ld in results[:10]:
    p = ld["properties"]
    url = (p.get("lead_cta_source_url") or "")[:90]
    print(f"  Lead {ld['id']} created={p.get('hs_createdate')[:10]}  utm_source={p.get('lead_utm_source')}")
    print(f"    cta_url = {url}")

# 3. For the most recent lead with cta_source_url, compare to hs_analytics_first_url on associated contact
if results:
    print("\n=== 3. Compare lead_cta_source_url vs Contact.hs_analytics_first_url (for same lead) ===")
    lead = results[0]
    lid = lead["id"]
    # Get associated contact
    a_r = requests.get(f"{BASE}/crm/v4/objects/0-136/{lid}/associations/0-1",
                       headers=H, timeout=30)
    cassoc = a_r.json().get("results", [])
    if cassoc:
        cid = cassoc[0]["toObjectId"]
        c_r = requests.get(
            f"{BASE}/crm/v3/objects/contacts/{cid}"
            f"?properties=hs_analytics_first_url,hs_analytics_last_url",
            headers=H, timeout=30)
        cp = c_r.json().get("properties", {})
        print(f"  Lead {lid} lead_cta_source_url     = {lead['properties'].get('lead_cta_source_url')[:100]}")
        print(f"  Contact {cid} hs_analytics_first_url = {(cp.get('hs_analytics_first_url') or '')[:100]}")
        print(f"  Contact {cid} hs_analytics_last_url  = {(cp.get('hs_analytics_last_url') or '')[:100]}")
