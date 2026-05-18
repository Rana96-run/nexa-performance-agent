"""Diagnose May 17 BQ vs HubSpot lead gap (BQ=18, HS=99 reported)."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from datetime import date, datetime, timedelta, timezone
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]
TARGET = "2026-05-17"

# 1. BQ — what does hubspot_leads_module_daily show for May 17?
print("=" * 70)
print("1. BQ hubspot_leads_module_daily for 2026-05-17")
print("=" * 70)
sql = f"""
SELECT qoyod_source, SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date = '{TARGET}'
GROUP BY 1 ORDER BY leads DESC
"""
bq_total = 0
for r in c.query(sql).result():
    bq_total += r.leads or 0
    print(f"  {(r.qoyod_source or '(null)'):20s}  leads={r.leads:>3}  sqls={r.sqls}")
print(f"\n  BQ total: {bq_total}")

# 2. When was hubspot_leads_module_daily last written?
print("\n" + "=" * 70)
print("2. Most recent writes to hubspot_leads_module_daily")
print("=" * 70)
sql2 = f"""
SELECT date, MAX(updated_at) AS last_write, COUNT(*) AS row_count
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 4 DAY)
GROUP BY 1 ORDER BY 1 DESC
"""
for r in c.query(sql2).result():
    print(f"  date={r.date}  rows={r.row_count:>4}  last_write={r.last_write}")

# 3. HubSpot live count for May 17 (Riyadh midnight to midnight)
print("\n" + "=" * 70)
print("3. HubSpot live API — all leads created on 2026-05-17 Riyadh")
print("=" * 70)
riyadh = timezone(timedelta(hours=3))
start_l = datetime(2026, 5, 17, 0, 0, tzinfo=riyadh)
end_l   = datetime(2026, 5, 18, 0, 0, tzinfo=riyadh)
HS = os.environ["HUBSPOT_ACCESS_TOKEN"]

body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_createdate", "operator": "GTE", "value": int(start_l.timestamp() * 1000)},
        {"propertyName": "hs_createdate", "operator": "LT",  "value": int(end_l.timestamp() * 1000)},
    ]}],
    "properties": ["lead_qoyod_source"],
    "limit": 100,
}
hdr = {"Authorization": f"Bearer {HS}", "Content-Type": "application/json"}
hs_total = 0
by_source = {}
after = 0
while True:
    body["after"] = after
    r = requests.post("https://api.hubapi.com/crm/v3/objects/0-136/search",
                      headers=hdr, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    for obj in data.get("results", []):
        hs_total += 1
        src = (obj.get("properties", {}).get("lead_qoyod_source") or "(null)")
        by_source[src] = by_source.get(src, 0) + 1
    nxt = data.get("paging", {}).get("next", {}).get("after")
    if not nxt: break
    after = nxt
    if hs_total > 5000: break

print(f"HubSpot live total May 17: {hs_total}")
for s, n in sorted(by_source.items(), key=lambda x: -x[1])[:10]:
    print(f"  {s[:25]:25s}  {n}")

# 4. Verdict
print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)
print(f"  BQ for 2026-05-17: {bq_total} leads")
print(f"  HS for 2026-05-17: {hs_total} leads")
print(f"  Gap: {hs_total - bq_total} leads missing from BQ")
print(f"\n  → The hubspot_leads_module collector hasn't fully synced May 17.")
print(f"  → Fix: re-run the collector with a 2-day backfill.")
