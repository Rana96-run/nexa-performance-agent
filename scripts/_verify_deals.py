"""Verify deals data: amounts, won amounts, createdate logic, new_biz calc.
Pulls BQ + HubSpot live, reconciles on a 7-day window."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
from collectors.bq_writer import get_client
from datetime import datetime, timezone, timedelta

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]
HS = os.environ["HUBSPOT_ACCESS_TOKEN"]

# Window: T-8 to T-2 (settled days)
START = "2026-05-12"
END   = "2026-05-18"
riyadh = timezone(timedelta(hours=3))
start_l = datetime(2026, 5, 12, 0, 0, tzinfo=riyadh)
end_l   = datetime(2026, 5, 19, 0, 0, tzinfo=riyadh)
since_ms = int(start_l.timestamp() * 1000)
until_ms = int(end_l.timestamp() * 1000)

print("=" * 90)
print(f"DEALS VERIFICATION — {START} to {END} (Riyadh, 7 days)")
print("=" * 90)

# 1. BQ totals by pipeline
print("\n1. BQ — by pipeline (raw aggregates from hubspot_deals_daily)")
print("-" * 90)
sql = f"""
SELECT pipeline,
       SUM(deals_total) AS deals_total,
       SUM(deals_won) AS deals_won,
       ROUND(SUM(amount_total), 2) AS amount_total_usd,
       ROUND(SUM(amount_won), 2) AS amount_won_usd,
       ROUND(SUM(amount_total_native), 2) AS amount_total_native,
       ANY_VALUE(currency_native) AS native_cur
FROM `{proj}.{ds}.hubspot_deals_daily`
WHERE date BETWEEN '{START}' AND '{END}'
GROUP BY 1
ORDER BY deals_total DESC
"""
bq_by_pipeline = {}
print(f"  {'Pipeline':25s}  {'deals':>5s}  {'won':>4s}  {'amt_USD':>12s}  {'won_USD':>12s}  {'amt_native':>12s}")
for r in c.query(sql).result():
    bq_by_pipeline[r.pipeline] = r
    print(f"  {(r.pipeline or '?')[:25]:25s}  {r.deals_total:>5}  {r.deals_won:>4}  ${r.amount_total_usd:>10.2f}  ${r.amount_won_usd:>10.2f}  {r.amount_total_native or 0:>10.2f} {r.native_cur or ''}")

# 2. New-biz definition check
NEW_BIZ_PIPELINES = ("Sales Pipeline", "Bookkeeping", "Qflavours")
print(f"\n2. New-biz pipelines = {NEW_BIZ_PIPELINES}")
new_biz_in_bq = [p for p in NEW_BIZ_PIPELINES if p in bq_by_pipeline]
missing = [p for p in NEW_BIZ_PIPELINES if p not in bq_by_pipeline]
print(f"   Present in BQ for window: {new_biz_in_bq}")
if missing:
    print(f"   ⚠ Missing from BQ: {missing} (could be no activity or pipeline rename)")

# Compute new_biz totals
nb_deals = sum(bq_by_pipeline[p].deals_total for p in new_biz_in_bq)
nb_won   = sum(bq_by_pipeline[p].deals_won   for p in new_biz_in_bq)
nb_amount = sum(bq_by_pipeline[p].amount_total_usd or 0 for p in new_biz_in_bq)
nb_won_amount = sum(bq_by_pipeline[p].amount_won_usd or 0 for p in new_biz_in_bq)
print(f"\n   New-biz totals (BQ):")
print(f"     deals_total={nb_deals}  deals_won={nb_won}")
print(f"     amount_total=${nb_amount:.2f}  amount_won=${nb_won_amount:.2f}")

# 3. Pull HubSpot live for Sales Pipeline (primary new-biz pipeline)
print(f"\n3. HubSpot live API — Sales Pipeline deals created in window")
print("-" * 90)
# Find Sales Pipeline ID
r = requests.get("https://api.hubapi.com/crm/v3/pipelines/deals",
                 headers={"Authorization": f"Bearer {HS}"}, timeout=15)
pipelines = r.json().get("results", [])
sp_id = next((p["id"] for p in pipelines if p["label"] == "Sales Pipeline"), None)
print(f"   Sales Pipeline id: {sp_id}")

# Search Sales Pipeline deals by createdate
body = {
    "filterGroups": [{"filters": [
        {"propertyName": "pipeline",    "operator": "EQ",  "value": sp_id},
        {"propertyName": "createdate",  "operator": "GTE", "value": since_ms},
        {"propertyName": "createdate",  "operator": "LT",  "value": until_ms},
    ]}],
    "properties": ["amount", "dealstage", "hs_is_closed_won", "hs_is_closed", "createdate"],
    "limit": 100,
}
hs_deals = []
after = 0
while True:
    body["after"] = after
    rr = requests.post("https://api.hubapi.com/crm/v3/objects/deals/search",
                       headers={"Authorization": f"Bearer {HS}", "Content-Type": "application/json"},
                       json=body, timeout=30)
    rr.raise_for_status()
    data = rr.json()
    hs_deals.extend(data.get("results", []))
    nxt = data.get("paging", {}).get("next", {}).get("after")
    if not nxt: break
    after = nxt
    if len(hs_deals) > 5000: break

hs_total = len(hs_deals)
hs_won = sum(1 for d in hs_deals if d.get("properties", {}).get("hs_is_closed_won") == "true")

# Sum amounts (HS native = SAR; divide by 3.75 NO — we just sum native, then convert below for comparison)
hs_amount_native = sum(float(d.get("properties", {}).get("amount") or 0) for d in hs_deals)
hs_won_amount_native = sum(
    float(d.get("properties", {}).get("amount") or 0)
    for d in hs_deals if d.get("properties", {}).get("hs_is_closed_won") == "true"
)
# Convert SAR → USD using 3.75 peg (BQ stores USD; HS API returns native SAR)
hs_amount_usd = hs_amount_native / 3.75
hs_won_amount_usd = hs_won_amount_native / 3.75

print(f"   HS deals_total: {hs_total}")
print(f"   HS deals_won:   {hs_won}")
print(f"   HS amount_total native: SAR {hs_amount_native:,.2f}  →  USD ${hs_amount_usd:,.2f}")
print(f"   HS amount_won   native: SAR {hs_won_amount_native:,.2f}  →  USD ${hs_won_amount_usd:,.2f}")

# 4. Reconciliation: Sales Pipeline only
sp_bq = bq_by_pipeline.get("Sales Pipeline")
print(f"\n4. RECON — Sales Pipeline (BQ vs HS)")
print("-" * 90)
if sp_bq is None:
    print("   ⚠ Sales Pipeline missing from BQ for window")
else:
    def pct(bq, hs):
        if hs == 0: return 0
        return (bq - hs) / hs * 100
    print(f"   deals_total:  BQ={sp_bq.deals_total:>4}  HS={hs_total:>4}  drift={pct(sp_bq.deals_total, hs_total):+.2f}%")
    print(f"   deals_won:    BQ={sp_bq.deals_won:>4}  HS={hs_won:>4}  drift={pct(sp_bq.deals_won, hs_won):+.2f}%")
    print(f"   amount_USD:   BQ=${sp_bq.amount_total_usd:>11,.2f}  HS=${hs_amount_usd:>11,.2f}  drift={pct(sp_bq.amount_total_usd, hs_amount_usd):+.2f}%")
    print(f"   won_USD:      BQ=${sp_bq.amount_won_usd:>11,.2f}  HS=${hs_won_amount_usd:>11,.2f}  drift={pct(sp_bq.amount_won_usd, hs_won_amount_usd):+.2f}%")

# 5. createdate semantics: are BQ partitions actually by createdate?
print(f"\n5. createdate semantics check")
print("-" * 90)
# Sample first 5 BQ deals from yesterday's partition, look up their HS createdate
sample_sql = f"""
SELECT date, deals_total, amount_total
FROM `{proj}.{ds}.hubspot_deals_daily`
WHERE date BETWEEN '{START}' AND '{END}'
  AND pipeline = 'Sales Pipeline'
ORDER BY date DESC
LIMIT 7
"""
print(f"   BQ daily breakdown (Sales Pipeline):")
for r in c.query(sample_sql).result():
    print(f"     {r.date}  deals={r.deals_total}  amount=${r.amount_total:>10,.2f}")

# Pull HS deals grouped by createdate Riyadh day
from collections import Counter
hs_by_day = Counter()
hs_amt_by_day = {}
for d in hs_deals:
    cd_str = d.get("properties", {}).get("createdate") or ""
    if not cd_str:
        continue
    # HS Search API returns ISO 8601 string (e.g. "2026-05-11T23:48:21.538Z")
    cd_dt = datetime.fromisoformat(cd_str.replace("Z", "+00:00")).astimezone(riyadh)
    day = cd_dt.strftime("%Y-%m-%d")
    hs_by_day[day] += 1
    hs_amt_by_day.setdefault(day, 0)
    hs_amt_by_day[day] += float(d.get("properties", {}).get("amount") or 0)

print(f"\n   HS daily breakdown (Sales Pipeline, createdate Riyadh):")
for day in sorted(hs_by_day, reverse=True):
    amt_usd = hs_amt_by_day[day] / 3.75
    print(f"     {day}  deals={hs_by_day[day]}  amount=${amt_usd:>10,.2f}")
