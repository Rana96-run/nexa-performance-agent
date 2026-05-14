"""Check if drilldown columns are actually populated for ANY leads."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# Check overall drilldown population
print("Drilldown column population — last 30 days, all sources:")
sql = f"""
SELECT
  COUNT(*) AS total,
  COUNTIF(lead_original_traffic_source_drilldown_1 IS NOT NULL) AS with_orig_dd1,
  COUNTIF(lead_latest_traffic_source_drilldown_1 IS NOT NULL) AS with_latest_dd1
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
"""
for r in c.query(sql).result():
    print(f"  Total rows: {r.total}")
    print(f"  With orig_dd1:   {r.with_orig_dd1}")
    print(f"  With latest_dd1: {r.with_latest_dd1}")

# Sample some values
print("\nSample 15 leads (any source) with drilldown populated:")
sql2 = f"""
SELECT qoyod_source, lead_utm_campaign,
       lead_original_traffic_source_drilldown_1 AS orig_dd1,
       lead_latest_traffic_source_drilldown_1 AS latest_dd1,
       leads_total
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND (lead_original_traffic_source_drilldown_1 IS NOT NULL
       OR lead_latest_traffic_source_drilldown_1 IS NOT NULL)
LIMIT 15
"""
for r in c.query(sql2).result():
    print(f"  {r.qoyod_source:18s} utm='{(r.lead_utm_campaign or '')[:30]}' orig_dd1='{(r.orig_dd1 or '')[:30]}' latest_dd1='{(r.latest_dd1 or '')[:30]}'")
