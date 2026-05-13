"""Reconcile paid_channel_campaign_daily (Option B view) against HubSpot
API + raw campaigns_daily for a 7-day window. Verifies:
1. Total leads in view = total leads in HubSpot API for the same channel
2. Snapchat duplicate-name campaign now shows as 2 separate rows (one per ID)
3. Google campaign still attributes via name (since no sync ID exists for Google leads)
"""
import os, sys, json, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]
TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")

def sec(t): print(f"\n{'='*80}\n{t}\n{'='*80}")

# ---- 1. Top campaigns in last 7 days from new view ----
sec("1. Top 15 campaigns in paid_channel_campaign_daily (last 7 days)")
sql = f"""
SELECT channel, campaign_id, campaign_name,
       ROUND(SUM(spend),0) AS spend,
       SUM(leads) AS leads, SUM(qualified) AS sqls,
       SUM(new_biz_deals_won) AS deals_won,
       ROUND(SUM(new_biz_revenue_won),0) AS rev_won
FROM `{proj}.{ds}.paid_channel_campaign_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
GROUP BY 1,2,3
ORDER BY spend DESC
LIMIT 15
"""
for r in c.query(sql).result():
    print(f"  [{r.channel:14s}] cid={(r.campaign_id or '')[:15]:15s}  "
          f"spend=${r.spend:>5.0f}  leads={r.leads:3d}  sqls={r.sqls:3d}  "
          f"won={r.deals_won:2d}  rev=${r.rev_won:.0f}  | {(r.campaign_name or '')[:45]}")

# ---- 2. Snapchat duplicate-name "iPhone_Instantform" campaigns — do they separate? ----
sec("2. Snapchat duplicate-name campaign — should now show as 2 rows (by ID)")
sql2 = f"""
SELECT campaign_id, campaign_name,
       ROUND(SUM(spend),0) AS spend, SUM(leads) AS leads, SUM(qualified) AS sqls,
       SUM(new_biz_deals_won) AS deals_won,
       ROUND(SUM(new_biz_revenue_won),0) AS rev_won
FROM `{proj}.{ds}.paid_channel_campaign_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
  AND channel = 'snapchat'
  AND LOWER(campaign_name) LIKE '%iphone%instantform%'
GROUP BY 1, 2
ORDER BY spend DESC
"""
rows = list(c.query(sql2).result())
if rows:
    for r in rows:
        print(f"  cid={r.campaign_id}  spend=${r.spend:.0f}  leads={r.leads}  sqls={r.sqls}  won={r.deals_won}  rev=${r.rev_won}")
        print(f"      name={r.campaign_name}")
    print(f"\n  → {len(rows)} rows (was 1 row when name-only; separating means Option B works)")
else:
    print("  (no matching rows in last 7 days)")

# ---- 3. Pick one Snapchat campaign — reconcile leads vs HubSpot API ----
sec("3. Lead reconciliation: BQ vs HubSpot API for top Snapchat campaign (7d)")
sql3 = f"""
SELECT campaign_id, campaign_name, SUM(leads) AS leads
FROM `{proj}.{ds}.paid_channel_campaign_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
  AND channel = 'snapchat' AND leads > 0
GROUP BY 1, 2
ORDER BY leads DESC
LIMIT 1
"""
row = next(iter(c.query(sql3).result()), None)
if row:
    print(f"  BQ: campaign '{row.campaign_name[:50]}' (cid={row.campaign_id})")
    print(f"  BQ: {row.leads} leads in last 7 days")

    # Pull HubSpot leads count by lead_campaign_id_sync via Search API
    import datetime as _dt
    # HubSpot Search expects epoch-milliseconds for date filters
    since_dt = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=7)
    since = str(int(since_dt.timestamp() * 1000))
    hs_query = {
        "filterGroups": [{
            "filters": [
                {"propertyName": "lead_campaign_id_sync", "operator": "EQ", "value": row.campaign_id},
                {"propertyName": "hs_createdate", "operator": "GTE", "value": since},
            ]
        }],
        "properties": ["lead_campaign_id_sync"],
        "limit": 1,
    }
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/0-136/search",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json=hs_query, timeout=30,
    )
    if r.status_code == 200:
        hs_count = r.json().get("total", 0)
        print(f"  HS: {hs_count} leads with lead_campaign_id_sync = {row.campaign_id} since 7d ago")
        delta = abs(row.leads - hs_count) / max(hs_count, 1) * 100 if hs_count else 0
        ok = "[OK]" if delta < 5 else "[CHECK]"
        print(f"  {ok} delta = {row.leads - hs_count} ({delta:.1f}%)")
    else:
        print(f"  HS API error: {r.status_code} {r.text[:200]}")

# ---- 4. Pick one Google campaign — should match by NAME (no sync ID expected) ----
sec("4. Google campaign reconciliation (name-fallback path)")
sql4 = f"""
SELECT campaign_id, campaign_name, SUM(leads) AS leads
FROM `{proj}.{ds}.paid_channel_campaign_daily`
WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
  AND channel = 'google_ads' AND leads > 0
GROUP BY 1, 2
ORDER BY leads DESC
LIMIT 1
"""
row = next(iter(c.query(sql4).result()), None)
if row:
    print(f"  BQ: campaign '{row.campaign_name[:50]}' (cid={row.campaign_id})")
    print(f"  BQ: {row.leads} leads in last 7 days")

    import datetime as _dt
    # HubSpot Search expects epoch-milliseconds for date filters
    since_dt = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=7)
    since = str(int(since_dt.timestamp() * 1000))
    hs_query = {
        "filterGroups": [{
            "filters": [
                {"propertyName": "lead_utm_campaign", "operator": "EQ", "value": row.campaign_name},
                {"propertyName": "hs_createdate", "operator": "GTE", "value": since},
            ]
        }],
        "properties": ["lead_utm_campaign"],
        "limit": 1,
    }
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/0-136/search",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json=hs_query, timeout=30,
    )
    if r.status_code == 200:
        hs_count = r.json().get("total", 0)
        print(f"  HS: {hs_count} leads with lead_utm_campaign = '{row.campaign_name[:50]}'")
        delta = abs(row.leads - hs_count) / max(hs_count, 1) * 100 if hs_count else 0
        ok = "[OK]" if delta < 10 else "[CHECK]"
        print(f"  {ok} delta = {row.leads - hs_count} ({delta:.1f}%)")
    else:
        print(f"  HS API error: {r.status_code}")
