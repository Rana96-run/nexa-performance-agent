"""Verify lead_cta_source + lead_cta_source_url exist on Lead Module and check
what they actually contain for recent Google contacts (especially the
DIRECT_TRAFFIC ones where hs_analytics_first_url showed only app.qoyod.com).
"""
import os, sys, requests, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# 1. Confirm properties exist on Lead Module
r = requests.get(f"{BASE}/crm/v3/properties/0-136", headers=H, timeout=30)
props = {p["name"]: p for p in r.json().get("results", [])}
print("=" * 70)
print("Property check on Lead Module (0-136)")
print("=" * 70)
for name in ("lead_cta_source", "lead_cta_source_url"):
    if name in props:
        p = props[name]
        print(f"  ✓ {name:25s}  type={p.get('type'):10s}  label={p.get('label')}")
    else:
        print(f"  ✗ {name} — NOT FOUND")

# 2. Pull recent Google leads (including DIRECT_TRAFFIC ones) and inspect cta props
print("\n" + "=" * 70)
print("Sample recent Google leads — lead_cta_source / lead_cta_source_url values")
print("=" * 70)

import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=48)).timestamp() * 1000))

# Pull leads from Lead Module directly (not Contact)
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "lead_utm_source", "operator": "EQ", "value": "google"},
        {"propertyName": "hs_createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": [
        "hs_createdate",
        "lead_utm_campaign", "lead_campaign_id_sync",
        "lead_cta_source", "lead_cta_source_url",
    ],
    "limit": 10,
    "sorts": [{"propertyName": "hs_createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/0-136/search", headers=H, json=body, timeout=30)
leads = r.json().get("results", [])
print(f"\nPulled {len(leads)} recent leads (utm_source=google, last 48h):\n")

has_hsa_in_cta = 0
for ld in leads:
    p = ld["properties"]
    cta_url = p.get("lead_cta_source_url") or ""
    has_hsa = "hsa_cam=" in cta_url
    if has_hsa:
        has_hsa_in_cta += 1
    print(f"Lead {ld['id']}  utm_campaign={(p.get('lead_utm_campaign') or '—')[:35]}")
    print(f"  cid_sync          = {p.get('lead_campaign_id_sync') or '—'}")
    print(f"  lead_cta_source   = {p.get('lead_cta_source') or '—'}")
    print(f"  lead_cta_source_url = {cta_url[:100]}{'...' if len(cta_url)>100 else ''}")
    if has_hsa:
        m = re.search(r"hsa_cam=(\d+)", cta_url)
        if m:
            print(f"  → hsa_cam extracted: {m.group(1)}")
    print()

print(f"SUMMARY: {has_hsa_in_cta}/{len(leads)} leads have hsa_cam in lead_cta_source_url")
