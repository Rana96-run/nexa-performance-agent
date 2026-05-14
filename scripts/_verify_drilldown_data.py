"""Verify drilldown columns now exist + sample Google leads with empty utm_campaign."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# Check daily table schema
sql_schema = f"""
SELECT column_name FROM `{proj}.{ds}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'hubspot_leads_module_daily'
  AND column_name LIKE '%drilldown%'
ORDER BY column_name
"""
print("Drilldown columns on hubspot_leads_module_daily:")
for r in c.query(sql_schema).result():
    print(f"  ✓ {r.column_name}")

# Coverage check
print("\nLast 7 days — Google Ads with empty utm_campaign but drilldown populated:")
sql = f"""
SELECT
  COUNT(*) AS total,
  SUM(leads_total) AS leads,
  COUNTIF(lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '') AS no_utm_rows,
  COUNTIF((lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '')
          AND lead_latest_traffic_source_drilldown_1 IS NOT NULL) AS recoverable_via_latest_dd1,
  COUNTIF((lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '')
          AND lead_original_traffic_source_drilldown_1 IS NOT NULL) AS recoverable_via_original_dd1
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND qoyod_source = 'Google Ads'
"""
for r in c.query(sql).result():
    print(f"  Total rows:                   {r.total}")
    print(f"  Total leads:                  {r.leads}")
    print(f"  Rows w/ empty utm:            {r.no_utm_rows}")
    print(f"  → recoverable via latest_dd1: {r.recoverable_via_latest_dd1}")
    print(f"  → recoverable via orig_dd1:   {r.recoverable_via_original_dd1}")

# Sample 10 specific rows
print("\nSample 10 leads with empty utm but drilldown populated:")
sql2 = f"""
SELECT date, lead_utm_campaign,
       lead_latest_traffic_source_drilldown_1 AS latest_dd1,
       lead_original_traffic_source_drilldown_1 AS orig_dd1,
       leads_total
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND qoyod_source = 'Google Ads'
  AND (lead_utm_campaign IS NULL OR lead_utm_campaign = '__none__' OR lead_utm_campaign = '')
  AND (lead_latest_traffic_source_drilldown_1 IS NOT NULL OR lead_original_traffic_source_drilldown_1 IS NOT NULL)
LIMIT 10
"""
for r in c.query(sql2).result():
    print(f"  {r.date}  utm='{r.lead_utm_campaign}'  latest_dd1='{r.latest_dd1 or '—'}'  orig_dd1='{r.orig_dd1 or '—'}'  leads={r.leads_total}")
