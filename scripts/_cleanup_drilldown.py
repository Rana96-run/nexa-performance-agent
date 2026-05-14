"""Cleanup the drilldown work that didn't help:
1. Revert v_lead_attribution to pre-drilldown (Strategy A/B/C/D only)
2. Drop the 4 useless drilldown columns from both BQ tables
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# ── 1. Revert v_lead_attribution to clean A/B/C/D version ──────────────────
VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{proj}.{ds}.v_lead_attribution` AS
-- Unified lead-to-campaign attribution. Picks the highest-priority signal
-- per lead and exposes effective IDs + the strategy label.
--
-- Strategy order (priority):
--   A_sync       lead_campaign_id_sync                    (Snap/Meta/TikTok native)
--   B_gclid      gclid_attribution lookup                 (Google gclid → click_view)
--   C_url_param  REGEXP_EXTRACT campaign_id from URL      (cta_source_url fallback)
--   D_name       lead_utm_campaign name match             (UTM name resolves to campaign_id)
WITH leads AS (
  SELECT
    date,
    qoyod_source,
    lead_utm_campaign,
    lead_utm_audience,
    lead_utm_content,
    lead_campaign_id_sync,
    lead_adgroup_id_sync,
    lead_ad_id_sync,
    lead_google_ad_click_id,
    lead_cta_source_url,
    leads_total,
    leads_qualified,
    leads_disqualified
  FROM `{proj}.{ds}.hubspot_leads_module_daily`
  WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 0 DAY)
),
gclid_lookup AS (
  SELECT
    gclid,
    ANY_VALUE(campaign_id)  AS campaign_id,
    ANY_VALUE(ad_group_id)  AS ad_group_id,
    ANY_VALUE(ad_id)        AS ad_id
  FROM `{proj}.{ds}.gclid_attribution`
  GROUP BY gclid
),
name_lookup AS (
  SELECT
    LOWER(TRIM(campaign_name)) AS name_lc,
    ANY_VALUE(channel)         AS channel,
    ANY_VALUE(campaign_id)     AS campaign_id
  FROM `{proj}.{ds}.campaigns_daily`
  WHERE campaign_name IS NOT NULL
  GROUP BY 1
)
SELECT
  l.date,
  l.qoyod_source,
  l.leads_total,
  l.leads_qualified,
  l.leads_disqualified,
  -- Raw signals
  l.lead_campaign_id_sync                                     AS sync_campaign_id,
  g.campaign_id                                               AS gclid_campaign_id,
  REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)') AS url_campaign_id,
  l.lead_utm_campaign                                         AS name_campaign,
  -- Effective campaign ID (priority chain)
  COALESCE(
    l.lead_campaign_id_sync,
    g.campaign_id,
    REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)'),
    nl_utm.campaign_id
  ) AS effective_campaign_id,
  -- Strategy label
  CASE
    WHEN l.lead_campaign_id_sync IS NOT NULL THEN 'A_sync'
    WHEN g.campaign_id           IS NOT NULL THEN 'B_gclid'
    WHEN REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)') IS NOT NULL THEN 'C_url_param'
    WHEN nl_utm.campaign_id IS NOT NULL THEN 'D_name'
    WHEN l.lead_utm_campaign IS NOT NULL AND l.lead_utm_campaign != '__none__' THEN 'D_name_no_match'
    ELSE 'unattributed'
  END AS attribution_strategy,
  l.lead_adgroup_id_sync AS effective_adgroup_id,
  l.lead_ad_id_sync      AS effective_ad_id,
  l.lead_google_ad_click_id IS NOT NULL AS has_gclid
FROM leads l
LEFT JOIN gclid_lookup g
  ON g.gclid = l.lead_google_ad_click_id
LEFT JOIN name_lookup nl_utm
  ON nl_utm.name_lc = LOWER(TRIM(l.lead_utm_campaign))
  AND l.lead_utm_campaign IS NOT NULL
  AND l.lead_utm_campaign != '__none__'
  AND l.lead_utm_campaign != ''
"""

print("Step 1: Revert v_lead_attribution to A/B/C/D version (no drilldown)…")
c.query(VIEW_SQL).result()
print("  ✓ View reverted")

# ── 2. Drop the 4 drilldown columns from both tables ──────────────────────
print("\nStep 2: Drop drilldown columns from BQ tables…")
DRILLDOWN_COLS = [
    "lead_original_traffic_source_drilldown_1",
    "lead_latest_traffic_source_drilldown_1",
    "lead_original_traffic_source_drilldown_2",
    "lead_latest_traffic_source_drilldown_2",
]
for tbl in ("hubspot_leads_module_daily", "hubspot_leads_individual"):
    for col in DRILLDOWN_COLS:
        try:
            c.query(f"ALTER TABLE `{proj}.{ds}.{tbl}` DROP COLUMN IF EXISTS `{col}`").result()
            print(f"  ✓ {tbl}.{col} dropped")
        except Exception as e:
            print(f"  ✗ {tbl}.{col}: {str(e)[:80]}")

print("\nCleanup complete.")
