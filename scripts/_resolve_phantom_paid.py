"""Take the 10 DIRECT_TRAFFIC contacts with gclids (from earlier proof),
look up each gclid in gclid_attribution table, and show the recovered
campaign attribution + click-to-conversion gap."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# Pull recent DIRECT_TRAFFIC contacts with gclid (paid-decayed-to-direct)
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=72)).timestamp() * 1000))
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_analytics_source", "operator": "EQ", "value": "DIRECT_TRAFFIC"},
        {"propertyName": "hs_google_click_id", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": ["createdate", "hs_google_click_id", "campaign_id"],
    "limit": 10,
    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=H, json=body, timeout=30)
results = r.json().get("results", [])
print(f"DIRECT_TRAFFIC contacts with gclid (last 72h): {len(results)}\n")

# Get all the gclids
gclids = [c["properties"].get("hs_google_click_id") for c in results]
gclids = [g for g in gclids if g]

# Look them up in BQ
bq = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]
gclid_list_sql = ",".join(f"'{g}'" for g in gclids)
sql = f"""
SELECT gclid, date AS click_date, campaign_id, campaign_name, ad_group_id, ad_id
FROM `{proj}.{ds}.gclid_attribution`
WHERE gclid IN ({gclid_list_sql})
"""
attr = {}
for row in bq.query(sql).result():
    attr[row.gclid] = row

# Show recovery
recovered = 0
for ct in results:
    p = ct["properties"]
    gclid = p.get("hs_google_click_id")
    created = p.get("createdate")[:10]
    a = attr.get(gclid)
    print(f"Contact {ct['id']}  created={created}  hs_source=DIRECT_TRAFFIC  contact.campaign_id={p.get('campaign_id') or '—'}")
    if a:
        recovered += 1
        from datetime import date as _date
        try:
            gap = (_date.fromisoformat(created) - a.click_date).days
            gap_label = "fresh" if gap <= 1 else ("recent" if gap <= 7 else "stale")
        except Exception:
            gap = None; gap_label = "?"
        print(f"  ✓ RECOVERED via gclid {gclid[:25]}...")
        print(f"    click_date={a.click_date}  gap={gap}d ({gap_label})")
        print(f"    campaign_id={a.campaign_id}  campaign_name={a.campaign_name[:50] if a.campaign_name else '—'}")
        print(f"    ad_group_id={a.ad_group_id}  ad_id={a.ad_id}")
    else:
        print(f"  ✗ gclid {gclid[:25]}... NOT in gclid_attribution (older than 30d, or invalid)")
    print()

print(f"=== RECOVERY RATE: {recovered}/{len(results)} ===")
