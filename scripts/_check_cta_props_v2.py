"""Re-check CTA props on Lead Module + sample populated leads."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

H = {"Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}"}
BASE = "https://api.hubapi.com"

# 1. List CTA props on Lead Module
r = requests.get(f"{BASE}/crm/v3/properties/0-136", headers=H, timeout=30)
props = {p["name"]: p for p in r.json().get("results", [])}
print("=== CTA props on Lead Module ===")
for n in sorted(props):
    if "cta" in n.lower():
        p = props[n]
        calc = "calculated" if p.get("calculated") else "manual"
        print(f"  {n:30s}  type={p.get('type')}  src={calc}  label={p.get('label')}")

# 2. Find a recent lead with the new prop populated
print("\n=== Sample 5 recent leads — show all CTA prop values ===")
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24)).timestamp() * 1000))
cta_prop_names = [n for n in props if "cta" in n.lower()]

body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": cta_prop_names + ["lead_utm_source", "lead_utm_campaign", "hs_createdate"],
    "limit": 5,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/0-136/search", headers={**H, "Content-Type": "application/json"}, json=body, timeout=30)
leads = r.json().get("results", [])
for ld in leads:
    p = ld["properties"]
    print(f"\nLead {ld['id']}  utm_source={p.get('lead_utm_source')}  utm_campaign={(p.get('lead_utm_campaign') or '')[:35]}")
    for prop_name in cta_prop_names:
        val = p.get(prop_name)
        if val:
            print(f"  {prop_name} = {val[:90]}")
        else:
            print(f"  {prop_name} = (empty)")
