"""Measure how many Google Ads leads have empty utm_campaign but DO have
a campaign name available in lead_latest_traffic_source_drilldown_1 or
lead_original_traffic_source_drilldown_1.

This is the attribution gap not yet covered by Strategy A-D in v_lead_attribution.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# Check available columns on hubspot_leads_module_daily
sql_schema = f"""
SELECT column_name
FROM `{proj}.{ds}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'hubspot_leads_module_daily'
  AND (column_name LIKE '%drilldown%' OR column_name LIKE '%source_data%')
ORDER BY column_name
"""
print("Available drilldown columns:")
for r in c.query(sql_schema).result():
    print(f"  {r.column_name}")
print()

# Now measure the gap
sql = f"""
SELECT
  COUNT(*) AS total,
  SUM(leads_total) AS leads,
  COUNTIF(lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '') AS no_utm,
  COUNTIF((lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '')
          AND lead_latest_traffic_source_drilldown_1 IS NOT NULL) AS no_utm_but_drilldown
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND qoyod_source = 'Google Ads'
"""
print("Last 30 days — Google Ads leads:")
for r in c.query(sql).result():
    print(f"  Total rows: {r.total}")
    print(f"  Total leads: {r.leads}")
    print(f"  Rows with empty utm_campaign: {r.no_utm}")
    print(f"  Rows with empty utm_campaign BUT drilldown_1 populated: {r.no_utm_but_drilldown}")
    if r.no_utm:
        recoverable = r.no_utm_but_drilldown / r.no_utm * 100
        print(f"  → {recoverable:.0f}% of empty-UTM leads are recoverable via drilldown")

# Sample 10 specific cases
print("\n\nSample 10 Google leads with no utm but populated drilldown:")
sql2 = f"""
SELECT
  date, lead_utm_campaign, lead_latest_traffic_source_drilldown_1, leads_total
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND qoyod_source = 'Google Ads'
  AND (lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '')
  AND lead_latest_traffic_source_drilldown_1 IS NOT NULL
LIMIT 10
"""
for r in c.query(sql2).result():
    print(f"  date={r.date}  drilldown='{r.lead_latest_traffic_source_drilldown_1}'  leads={r.leads_total}")
