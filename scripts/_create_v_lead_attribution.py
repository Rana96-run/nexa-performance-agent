"""Create v_lead_attribution view — unified lead attribution combining:

  Strategy A: lead_campaign_id_sync          (Snap/Meta/TikTok native)
  Strategy B: gclid_attribution lookup       (Google gclid → click_view)
  Strategy C: lead_cta_source_url URL parse  (campaign_id from landing-page URL)
  Strategy D: lead_utm_campaign name match   (existing fallback)

For each lead, the view picks the highest-priority attribution available
and exposes:
  effective_campaign_id, effective_adgroup_id, effective_ad_id,
  attribution_strategy ('A_sync' | 'B_gclid' | 'C_url_param' | 'D_name')
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{proj}.{ds}.v_lead_attribution` AS
-- Unified lead-to-campaign attribution. For each lead row, picks the
-- highest-priority attribution signal and exposes the effective IDs +
-- the strategy label so dashboards can see which path resolved it.
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
-- Strategy B: gclid lookup. One row per gclid (we already enforce uniqueness).
gclid_lookup AS (
  SELECT
    gclid,
    ANY_VALUE(campaign_id)  AS campaign_id,
    ANY_VALUE(ad_group_id)  AS ad_group_id,
    ANY_VALUE(ad_id)        AS ad_id
  FROM `{proj}.{ds}.gclid_attribution`
  GROUP BY gclid
)
SELECT
  l.date,
  l.qoyod_source,
  l.leads_total,
  l.leads_qualified,
  l.leads_disqualified,
  -- Strategy outputs (raw signals so dashboards can introspect)
  l.lead_campaign_id_sync                                     AS sync_campaign_id,
  g.campaign_id                                               AS gclid_campaign_id,
  REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)') AS url_campaign_id,
  l.lead_utm_campaign                                         AS name_campaign,
  -- Same for adgroup
  l.lead_adgroup_id_sync                                      AS sync_adgroup_id,
  g.ad_group_id                                               AS gclid_adgroup_id,
  REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]ad_group_id=([^&]+)') AS url_adgroup_id,
  l.lead_utm_audience                                         AS name_adgroup,
  -- Same for ad
  l.lead_ad_id_sync                                           AS sync_ad_id,
  g.ad_id                                                     AS gclid_ad_id,
  REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]ad_id=([^&]+)') AS url_ad_id,
  l.lead_utm_content                                          AS name_ad,
  -- COALESCE chain: A → B → C → (D = name; left raw for join elsewhere)
  COALESCE(
    l.lead_campaign_id_sync,
    g.campaign_id,
    REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)')
  ) AS effective_campaign_id,
  COALESCE(
    l.lead_adgroup_id_sync,
    g.ad_group_id,
    REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]ad_group_id=([^&]+)')
  ) AS effective_adgroup_id,
  COALESCE(
    l.lead_ad_id_sync,
    g.ad_id,
    REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]ad_id=([^&]+)')
  ) AS effective_ad_id,
  -- Strategy label — tells you WHICH signal won the COALESCE
  CASE
    WHEN l.lead_campaign_id_sync IS NOT NULL THEN 'A_sync'
    WHEN g.campaign_id           IS NOT NULL THEN 'B_gclid'
    WHEN REGEXP_EXTRACT(l.lead_cta_source_url, r'[?&]campaign_id=([^&]+)') IS NOT NULL THEN 'C_url_param'
    WHEN l.lead_utm_campaign IS NOT NULL AND l.lead_utm_campaign != '__none__' THEN 'D_name'
    ELSE 'unattributed'
  END AS attribution_strategy,
  -- gclid presence (used as channel-level proof of paid Google)
  l.lead_google_ad_click_id IS NOT NULL AS has_gclid
FROM leads l
LEFT JOIN gclid_lookup g ON g.gclid = l.lead_google_ad_click_id
"""

print("Creating v_lead_attribution view…")
c.query(VIEW_SQL).result()
print("✓ View created")

# Quick verify: coverage by strategy for last 7 days
print("\nAttribution strategy coverage (last 7 days):")
sql = f"""
SELECT qoyod_source, attribution_strategy,
       COUNT(*) AS row_count, SUM(leads_total) AS leads
FROM `{proj}.{ds}.v_lead_attribution`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
  AND qoyod_source IN ('Google Ads','Microsoft Ads','Meta Ads','Snapchat Ads','Tiktok Ads')
GROUP BY 1, 2
ORDER BY 1, 4 DESC
"""
for r in c.query(sql).result():
    print(f"  {r.qoyod_source:18s}  {r.attribution_strategy:14s}  rows={r.row_count:5d}  leads={r.leads:5d}")
