"""Quantify the 30-day window gap: of all Google leads with gclid in last 7d,
how many gclids don't match gclid_attribution (= clicked > 30 days ago)?
Tells us whether widening to 90 days would meaningfully change attribution."""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client(); proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

sql = f"""
SELECT
  COUNT(*) AS row_count,
  COUNTIF(lead_google_ad_click_id IS NOT NULL) AS rows_with_gclid,
  COUNTIF(lead_google_ad_click_id IS NOT NULL
          AND lead_google_ad_click_id IN (
            SELECT gclid FROM `{proj}.{ds}.gclid_attribution`
          )) AS rows_with_gclid_in_30d,
  COUNTIF(lead_google_ad_click_id IS NOT NULL
          AND lead_google_ad_click_id NOT IN (
            SELECT gclid FROM `{proj}.{ds}.gclid_attribution`
          )) AS rows_gclid_older_than_30d,
  COUNTIF(lead_campaign_id_sync IS NOT NULL) AS rows_with_sync,
  SUM(leads_total) AS total_leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND qoyod_source = 'Google Ads'
"""

for r in c.query(sql).result():
    print(f"Last 7 days — Google Ads leads:")
    print(f"  Total rows:              {r.row_count}")
    print(f"  Total leads:             {r.total_leads}")
    print(f"  Rows with gclid:         {r.rows_with_gclid}")
    print(f"  → resolved in 30d:       {r.rows_with_gclid_in_30d}  ({r.rows_with_gclid_in_30d/r.rows_with_gclid*100:.0f}% of gclids)")
    print(f"  → gclid > 30d (stale):   {r.rows_gclid_older_than_30d}  ({r.rows_gclid_older_than_30d/r.rows_with_gclid*100:.0f}% of gclids)")
    print(f"  Rows with sync (no gclid lookup needed): {r.rows_with_sync}")
    print()
    print(f"=> Widening 30→90 days would recover at most {r.rows_gclid_older_than_30d} more rows")
