"""Check if Contact.cta_source / cta_source_url are populated for recent
contacts (including DIRECT_TRAFFIC ones with gclid)."""
import os, sys, requests, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=48)).timestamp() * 1000))

# Get recent contacts with gclid (paid Google), include DIRECT_TRAFFIC ones
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_google_click_id", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": [
        "createdate", "hs_analytics_source",
        "cta_source", "cta_source_url",
        "hs_google_click_id", "campaign_id",
        "hs_analytics_first_url",
    ],
    "limit": 15,
    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=H, json=body, timeout=30)
results = r.json().get("results", [])
print(f"Recent contacts with gclid (last 48h): {len(results)}\n")

n_populated = 0
n_with_hsa = 0
for ct in results:
    p = ct["properties"]
    cta = p.get("cta_source_url") or ""
    has_hsa_in_cta = "hsa_cam=" in cta
    has_hsa_in_first = "hsa_cam=" in (p.get("hs_analytics_first_url") or "")
    if cta:
        n_populated += 1
    if has_hsa_in_cta:
        n_with_hsa += 1
    print(f"Contact {ct['id']}  source={p.get('hs_analytics_source')}  cid={p.get('campaign_id') or '—'}")
    print(f"  cta_source       = {p.get('cta_source') or '—'}")
    print(f"  cta_source_url   = {(cta or '(empty)')[:90]}")
    if has_hsa_in_cta:
        m = re.search(r"hsa_cam=(\d+)", cta)
        print(f"  → hsa_cam in cta_url: {m.group(1) if m else 'no match'}")
    print(f"  hs_analytics_first_url = {(p.get('hs_analytics_first_url') or '(empty)')[:90]}")
    if has_hsa_in_first:
        print(f"  ← hsa_cam found in first_url too")
    print()

print(f"=== SUMMARY ===")
print(f"  Contacts with cta_source_url populated:  {n_populated}/{len(results)}")
print(f"  Contacts with hsa_cam in cta_source_url: {n_with_hsa}/{len(results)}")
