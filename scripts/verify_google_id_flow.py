"""Verify Google + Microsoft Ads ID flow end-to-end.

Checks:
  1. Recent contacts created in HubSpot via Google/Microsoft Ads — do they
     have campaign_id / ad_group_id / ad_id populated?
  2. For those contacts, does the associated Lead Module have the matching
     lead_*_id_sync calculated values?
  3. Aggregate sync ID coverage on hubspot_leads_module_daily for the last
     24h — Google + Microsoft.

Run this any time after the Google/Microsoft Final URL suffix change.
Expected: coverage should jump from ~1% / 0% to 60-80% as new traffic comes in.
"""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}"}
BASE = "https://api.hubapi.com"
c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

def sec(t): print(f"\n{'='*78}\n{t}\n{'='*78}")

# Helper: epoch-ms for "N hours ago" UTC
import datetime as _dt
def hours_ago(n):
    return str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=n)).timestamp() * 1000))

# ── 1. BQ aggregate coverage on Lead Module (last 24h) ─────────────────────
sec("1. Lead Module — sync ID coverage on recently-created leads (last 24h)")
sql = f"""
SELECT qoyod_source,
  COUNT(*)                          AS row_count,
  SUM(leads_total)                  AS leads,
  COUNTIF(lead_campaign_id_sync IS NOT NULL) AS rows_with_cid,
  COUNTIF(lead_adgroup_id_sync  IS NOT NULL) AS rows_with_aid,
  COUNTIF(lead_ad_id_sync       IS NOT NULL) AS rows_with_adid
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)
  AND qoyod_source IN ('Google Ads','Microsoft Ads')
GROUP BY 1
"""
for r in c.query(sql).result():
    cov_cid = (r.rows_with_cid / r.row_count * 100) if r.row_count else 0
    cov_aid = (r.rows_with_aid / r.row_count * 100) if r.row_count else 0
    cov_ad  = (r.rows_with_adid / r.row_count * 100) if r.row_count else 0
    print(f"  {r.qoyod_source:18s}  leads={r.leads or 0:3d}  "
          f"cid={cov_cid:4.0f}%  adgroup={cov_aid:4.0f}%  ad={cov_ad:4.0f}%")

# ── 2. Sample 5 recent Google + 5 Microsoft contacts via HubSpot API ───────
sec("2. Sample contacts created in last 24h — Google Ads")

for label, source_value in [("Google Ads", "google"), ("Microsoft Ads", "bing")]:
    print(f"\n  --- {label} ---")
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "hs_analytics_source_data_1", "operator": "EQ", "value": source_value},
            {"propertyName": "createdate", "operator": "GTE", "value": hours_ago(24)},
        ]}],
        "properties": [
            "createdate", "email",
            "campaign_id", "ad_group_id", "ad_id",
            "hs_google_click_id", "msclkid",
            "hs_analytics_first_url",
        ],
        "limit": 5,
        "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
    }
    r = requests.post(
        f"{BASE}/crm/v3/objects/contacts/search",
        headers={**H, "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    if r.status_code != 200:
        print(f"  [API err] {r.status_code} {r.text[:120]}")
        continue
    rows = r.json().get("results", [])
    if not rows:
        print("  (no contacts in last 24h)")
        continue
    populated = 0
    for ct in rows:
        p = ct["properties"]
        has = "✓" if p.get("campaign_id") else "✗"
        first_url = (p.get("hs_analytics_first_url") or "")[:50]
        if p.get("campaign_id"):
            populated += 1
        print(f"  {has} cid={p.get('campaign_id') or '—':>15s}  "
              f"aid={p.get('ad_group_id') or '—':>14s}  "
              f"ad={p.get('ad_id') or '—':>13s}")
        print(f"      url={first_url}...")
    print(f"  → {populated}/{len(rows)} contacts have campaign_id populated")

# ── 3. Cross-check: Lead Module values for those same contacts ────────────
sec("3. Lead Module sync — does it mirror the Contact campaign_id?")
print("  Pulls one Google + one Microsoft contact with campaign_id set, ")
print("  then verifies the associated lead.lead_campaign_id_sync matches.")

for label, source in [("Google", "google"), ("Microsoft", "bing")]:
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "hs_analytics_source_data_1", "operator": "EQ", "value": source},
            {"propertyName": "campaign_id", "operator": "HAS_PROPERTY"},
            {"propertyName": "createdate", "operator": "GTE", "value": hours_ago(48)},
        ]}],
        "properties": ["campaign_id", "ad_group_id", "ad_id"],
        "limit": 1,
    }
    r = requests.post(
        f"{BASE}/crm/v3/objects/contacts/search",
        headers={**H, "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    if r.status_code != 200 or not r.json().get("results"):
        print(f"\n  {label}: no contacts with campaign_id populated yet")
        continue
    ct = r.json()["results"][0]
    cp = ct["properties"]
    cid = ct["id"]
    print(f"\n  {label} Contact {cid}:")
    print(f"    campaign_id  = {cp.get('campaign_id')}")
    print(f"    ad_group_id  = {cp.get('ad_group_id')}")
    print(f"    ad_id        = {cp.get('ad_id')}")

    # Find associated Lead
    a_r = requests.get(f"{BASE}/crm/v4/objects/0-1/{cid}/associations/0-136",
                       headers=H, timeout=30)
    results = a_r.json().get("results", [])
    if not results:
        print(f"    [no Lead Module association]")
        continue
    lid = results[0]["toObjectId"]
    l_r = requests.get(
        f"{BASE}/crm/v3/objects/0-136/{lid}"
        f"?properties=lead_campaign_id_sync,lead_adgroup_id_sync,lead_ad_id_sync",
        headers=H, timeout=30)
    lp = l_r.json().get("properties", {})
    print(f"  → Lead {lid}:")
    print(f"    lead_campaign_id_sync = {lp.get('lead_campaign_id_sync')}")
    print(f"    lead_adgroup_id_sync  = {lp.get('lead_adgroup_id_sync')}")
    print(f"    lead_ad_id_sync       = {lp.get('lead_ad_id_sync')}")
    ok = (lp.get("lead_campaign_id_sync") == cp.get("campaign_id"))
    print(f"  {'✓ MATCH — calculated property mirrors correctly' if ok else '✗ MISMATCH — sync may be lagging'}")
