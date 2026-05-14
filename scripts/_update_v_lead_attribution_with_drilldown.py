"""Update v_lead_attribution view to add Strategy E (drilldown fallback).
When utm_campaign is empty, fall back to lead_latest_traffic_source_drilldown_1
or lead_original_traffic_source_drilldown_1, then resolve to campaign_id via
case-insensitive match against campaigns_daily.campaign_name.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{proj}.{ds}.v_lead_attribution` AS
-- Unified lead-to-campaign attribution. Picks the highest-priority signal
-- per lead and exposes effective IDs + the strategy label.
--
-- Strategy order:
--   A_sync       lead_campaign_id_sync                    (Snap/Meta/TikTok native)
--   B_gclid      gclid_attribution lookup                  (Google gclid → click_view)
--   C_url_param  REGEXP_EXTRACT campaign_id from URL       (cta_source_url fallback)
--   E_drilldown  HubSpot drilldown campaign name → ID      (when utm_campaign empty)
--   D_name       lead_utm_campaign name match              (UTM name match)
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
    lead_latest_traffic_source_drilldown_1,
    lead_original_traffic_source_drilldown_1,
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
-- Build a campaign-name → campaign_id lookup (case-insensitive)
-- Strategy E + D both resolve campaign NAME → ID via this map.
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
  l.lead_latest_traffic_source_drilldown_1                    AS drilldown_latest,
  l.lead_original_traffic_source_drilldown_1                  AS drilldown_original,
  -- Effective campaign NAME (used for Strategy E + D)
  COALESCE(
    NULLIF(l.lead_utm_campaign, '__none__'),
    NULLIF(l.lead_utm_campaign, ''),
    l.lead_latest_traffic_source_drilldown_1,
    l.lead_original_traffic_source_drilldown_1
  ) AS effective_campaign_name,
  -- Effective campaign ID — priority chain
  COALESCE(
    l.lead_campaign_id_sync,                                  -- A: native sync
    g.campaign_id,                                            -- B: gclid lookup
    REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)'),  -- C: URL param
    nl_drilldown_latest.campaign_id,                          -- E (latest drilldown name → id)
    nl_drilldown_original.campaign_id,                        -- E (original drilldown name → id)
    nl_utm.campaign_id                                        -- D: utm_campaign name → id
  ) AS effective_campaign_id,
  -- Strategy label
  CASE
    WHEN l.lead_campaign_id_sync IS NOT NULL THEN 'A_sync'
    WHEN g.campaign_id           IS NOT NULL THEN 'B_gclid'
    WHEN REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)') IS NOT NULL THEN 'C_url_param'
    WHEN nl_drilldown_latest.campaign_id IS NOT NULL THEN 'E_drilldown_latest'
    WHEN nl_drilldown_original.campaign_id IS NOT NULL THEN 'E_drilldown_original'
    WHEN nl_utm.campaign_id IS NOT NULL THEN 'D_name'
    WHEN l.lead_utm_campaign IS NOT NULL AND l.lead_utm_campaign != '__none__' THEN 'D_name_no_match'
    ELSE 'unattributed'
  END AS attribution_strategy,
  -- Adset / Ad still use sync IDs only for now
  l.lead_adgroup_id_sync AS effective_adgroup_id,
  l.lead_ad_id_sync      AS effective_ad_id,
  l.lead_google_ad_click_id IS NOT NULL AS has_gclid
FROM leads l
LEFT JOIN gclid_lookup g
  ON g.gclid = l.lead_google_ad_click_id
LEFT JOIN name_lookup nl_drilldown_latest
  ON nl_drilldown_latest.name_lc = LOWER(TRIM(l.lead_latest_traffic_source_drilldown_1))
LEFT JOIN name_lookup nl_drilldown_original
  ON nl_drilldown_original.name_lc = LOWER(TRIM(l.lead_original_traffic_source_drilldown_1))
LEFT JOIN name_lookup nl_utm
  ON nl_utm.name_lc = LOWER(TRIM(l.lead_utm_campaign))
  AND l.lead_utm_campaign IS NOT NULL
  AND l.lead_utm_campaign != '__none__'
  AND l.lead_utm_campaign != ''
"""

print("Updating v_lead_attribution view with Strategy E (drilldown fallback)...")
c.query(VIEW_SQL).result()
print("✓ View updated")

# Verify coverage shift
print("\nNew attribution strategy distribution (last 7 days):")
sql = f"""
SELECT qoyod_source, attribution_strategy,
       COUNT(*) AS row_count, SUM(leads_total) AS leads
FROM `{proj}.{ds}.v_lead_attribution`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND qoyod_source IN ('Google Ads','Microsoft Ads','Meta Ads','Snapchat Ads','Tiktok Ads')
GROUP BY 1, 2
ORDER BY 1, leads DESC
"""
for r in c.query(sql).result():
    print(f"  {r.qoyod_source:18s}  {r.attribution_strategy:25s}  rows={r.row_count:5d}  leads={r.leads:5d}")
