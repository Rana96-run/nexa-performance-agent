"""Check leads day-by-day to see if the gap is today's mirror-lag."""
import os, sys, requests, datetime as _dt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

PAID = ["Google Ads", "Meta Ads", "Snapchat Ads", "Tiktok Ads",
        "Microsoft Ads", "LinkedIn Ads"]

# BQ by day
print("BQ leads per day (paid only):")
sql = f"""
SELECT date, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date BETWEEN '2026-05-07' AND '2026-05-13'
  AND qoyod_source IN UNNEST({PAID})
GROUP BY 1 ORDER BY 1
"""
bq_by_day = {}
for r in c.query(sql).result():
    bq_by_day[str(r.date)] = r.leads or 0
    print(f"  {r.date}  {r.leads or 0}")

# HubSpot by day (in epoch-ms ranges)
print("\nHubSpot leads per day (paid only):")
def to_ms(date_str, h=0, m=0, s=0):
    dt = _dt.datetime.fromisoformat(date_str).replace(hour=h, minute=m, second=s) - _dt.timedelta(hours=3)
    return str(int(dt.timestamp() * 1000))

hs_by_day = {}
for offset in range(7):
    day = _dt.date(2026, 5, 7) + _dt.timedelta(days=offset)
    next_day = day + _dt.timedelta(days=1)
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "IN", "values": PAID},
            {"propertyName": "hs_createdate", "operator": "GTE", "value": to_ms(day.isoformat())},
            {"propertyName": "hs_createdate", "operator": "LT",  "value": to_ms(next_day.isoformat())},
        ]}],
        "properties": ["hs_createdate"],
        "limit": 1,
    }
    r = requests.post("https://api.hubapi.com/crm/v3/objects/0-136/search",
                      headers=H, json=body, timeout=30)
    n = r.json().get("total", 0) if r.status_code == 200 else None
    hs_by_day[day.isoformat()] = n or 0
    print(f"  {day}  {n if n is not None else 'ERR'}")

# Side-by-side
print("\n" + "=" * 50)
print(f"  {'date':12s}  {'BQ':>5s}  {'HS':>5s}  {'Δ':>4s}")
print(f"  {'-'*12}  {'-'*5}  {'-'*5}  {'-'*4}")
bq_tot = hs_tot = 0
for offset in range(7):
    day = (_dt.date(2026, 5, 7) + _dt.timedelta(days=offset)).isoformat()
    bq = bq_by_day.get(day, 0); hs = hs_by_day.get(day, 0)
    print(f"  {day}  {bq:>5d}  {hs:>5d}  {bq-hs:>+4d}")
    bq_tot += bq; hs_tot += hs
print(f"  {'-'*12}  {'-'*5}  {'-'*5}  {'-'*4}")
print(f"  {'TOTAL':12s}  {bq_tot:>5d}  {hs_tot:>5d}  {bq_tot-hs_tot:>+4d}")
