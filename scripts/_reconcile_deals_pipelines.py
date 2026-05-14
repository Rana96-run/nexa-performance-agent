"""Reconcile pipeline deal counts: BQ vs what HubSpot UI shows.
Sales Pipeline last 7d: HubSpot=637 vs Hex=372 → investigate gap."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# Date range matches user's HubSpot filter: 2026-05-07 → 2026-05-13 Riyadh
START = "2026-05-07"
END = "2026-05-13"

print(f"Date range: {START} → {END} (Riyadh)\n")

# 1. All deals by pipeline (no source filter) — should match HubSpot UI total
print("=" * 70)
print("BQ — ALL deals by pipeline (no qoyod_source filter)")
print("=" * 70)
sql = f"""
SELECT pipeline, SUM(deals_total) AS total
FROM `{proj}.{ds}.hubspot_deals_daily`
WHERE date BETWEEN '{START}' AND '{END}'
  AND pipeline IS NOT NULL
GROUP BY 1
ORDER BY total DESC
"""
for r in c.query(sql).result():
    print(f"  {str(r.pipeline):30s}  {r.total}")

# 2. With paid filter (what Hex shows)
print("\n" + "=" * 70)
print("BQ — PAID deals by pipeline (Hex's current filter)")
print("=" * 70)
sql2 = f"""
SELECT pipeline, SUM(deals_total) AS total
FROM `{proj}.{ds}.hubspot_deals_daily`
WHERE date BETWEEN '{START}' AND '{END}'
  AND pipeline IS NOT NULL
  AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
GROUP BY 1
ORDER BY total DESC
"""
for r in c.query(sql2).result():
    print(f"  {str(r.pipeline):30s}  {r.total}")

# 3. Where do Sales Pipeline deals come from by qoyod_source
print("\n" + "=" * 70)
print("Sales Pipeline — breakdown by qoyod_source")
print("=" * 70)
sql3 = f"""
SELECT qoyod_source, SUM(deals_total) AS total
FROM `{proj}.{ds}.hubspot_deals_daily`
WHERE date BETWEEN '{START}' AND '{END}'
  AND pipeline = 'Sales Pipeline'
GROUP BY 1
ORDER BY total DESC
"""
total = 0
for r in c.query(sql3).result():
    print(f"  {str(r.qoyod_source):25s}  {r.total}")
    total += r.total or 0
print(f"  {'TOTAL':25s}  {total}")
