"""
Unified reporting views — channel and campaign grain.

Materialized tables (rebuilt every 6h by materialize_heavy_views()):
  - utm_paid_attribution_daily   (UTM-joined spend + leads, campaign grain)
  - paid_channel_campaign_daily  (spend + leads + deals, campaign grain)
  - channel_roas_daily           (spend + leads + deals + ROAS, channel grain — spine-anchored)
  - paid_channel_daily           (same, channel grain via qoyod_source join — spine-anchored)
  - v_adset_performance          (adset grain)
  - v_ad_performance             (ad grain)

Lightweight views (ALL_VIEWS, refreshed by refresh_all_views()):
  - v_channel_key_map            (channel slug → display name)
  - v_agent_activity_dashboard   (agent activity heatmap for Hex)
  - v_keyword_performance        (keyword grain, via _sub_campaign_views())
"""
import os
from dotenv import load_dotenv
from collectors.bq_writer import get_client

load_dotenv()
P = os.getenv("BQ_PROJECT_ID")
D = os.getenv("BQ_DATASET", "qoyod_marketing")


# Channel label normalization: qoyod_source in HubSpot ~ channel in campaigns_daily.
# This regex-style mapping lets us join paid spend to HubSpot-attributed leads.
CHANNEL_MAP_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_channel_key_map` AS
SELECT channel AS paid_channel,
       CASE channel
         WHEN 'google_ads'     THEN 'Google Ads'
         WHEN 'meta'           THEN 'Meta Ads'
         WHEN 'snapchat'       THEN 'Snapchat Ads'
         WHEN 'tiktok'         THEN 'Tiktok Ads'
         WHEN 'microsoft_ads'  THEN 'Microsoft Ads'
         WHEN 'linkedin'       THEN 'LinkedIn Ads'
         WHEN 'organic_search' THEN 'Organic Search'
       END AS qoyod_source,
       CASE channel
         WHEN 'google_ads'     THEN 'Google Ads'
         WHEN 'meta'           THEN 'Meta Ads'
         WHEN 'snapchat'       THEN 'Snapchat Ads'
         WHEN 'tiktok'         THEN 'TikTok Ads'
         WHEN 'microsoft_ads'  THEN 'Microsoft Ads'
         WHEN 'linkedin'       THEN 'LinkedIn Ads'
         WHEN 'organic_search' THEN 'Organic Search'
       END AS display_name
FROM UNNEST(['google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin','organic_search']) AS channel
"""


CHANNEL_ROAS_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.channel_roas_daily` AS
-- Spine guarantees every channel appears for every date since its first campaign,
-- even on days with zero spend / zero leads / zero deals.
WITH channel_first AS (
  SELECT channel, MIN(date) AS first_date
  FROM `{P}.{D}.campaigns_daily`
  GROUP BY channel
),
spine AS (
  -- One row per (date, channel) for the past 365 days, from channel's first appearance onward
  SELECT d AS date, cf.channel
  FROM UNNEST(GENERATE_DATE_ARRAY(
    DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 365 DAY),
    DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
  )) AS d
  JOIN channel_first cf ON d >= cf.first_date
),
spend AS (
  SELECT date, channel,
         SUM(spend)        AS spend,
         SUM(impressions)  AS impressions,
         SUM(clicks)       AS clicks,
         SUM(leads)        AS platform_leads,
         SUM(conversions)  AS platform_conversions
  FROM `{P}.{D}.campaigns_daily`
  GROUP BY 1,2
),
leads AS (
  -- All pipelines combined
  SELECT l.date,
         m.paid_channel AS channel,
         SUM(l.leads_total)        AS hs_leads,
         SUM(l.leads_qualified)    AS hs_qualified,
         SUM(l.leads_disqualified) AS hs_disqualified,
         SUM(l.leads_open)         AS hs_open,
         -- Lead Pipeline (accounting / e-invoice — main product)
         SUM(CASE WHEN LOWER(l.pipeline) LIKE '%lead%' OR LOWER(l.pipeline) LIKE '%account%'
                       OR LOWER(l.pipeline) NOT LIKE '%book%'
                  THEN l.leads_total        ELSE 0 END) AS leads_accounting,
         SUM(CASE WHEN LOWER(l.pipeline) LIKE '%lead%' OR LOWER(l.pipeline) LIKE '%account%'
                       OR LOWER(l.pipeline) NOT LIKE '%book%'
                  THEN l.leads_qualified    ELSE 0 END) AS qualified_accounting,
         SUM(CASE WHEN LOWER(l.pipeline) LIKE '%lead%' OR LOWER(l.pipeline) LIKE '%account%'
                       OR LOWER(l.pipeline) NOT LIKE '%book%'
                  THEN l.leads_disqualified ELSE 0 END) AS disqualified_accounting,
         -- Bookkeeping Pipeline
         SUM(CASE WHEN LOWER(l.pipeline) LIKE '%book%'
                  THEN l.leads_total        ELSE 0 END) AS leads_bookkeeping,
         SUM(CASE WHEN LOWER(l.pipeline) LIKE '%book%'
                  THEN l.leads_qualified    ELSE 0 END) AS qualified_bookkeeping,
         SUM(CASE WHEN LOWER(l.pipeline) LIKE '%book%'
                  THEN l.leads_disqualified ELSE 0 END) AS disqualified_bookkeeping
  FROM `{P}.{D}.hubspot_leads_module_daily` l
  JOIN `{P}.{D}.v_channel_key_map` m ON l.qoyod_source = m.qoyod_source
  GROUP BY 1,2
),
deals AS (
  SELECT d.date,
         m.paid_channel AS channel,
         SUM(d.deals_total)    AS deals_total,
         SUM(d.deals_won)      AS deals_won,
         SUM(d.deals_lost)     AS deals_lost,
         SUM(d.deals_open)     AS deals_open,
         SUM(d.amount_won)     AS revenue_won,
         SUM(d.amount_lost)    AS amount_lost,
         SUM(d.amount_open)    AS pipeline_open,
         SUM(d.amount_total)   AS total_deal_amount,
         -- New business pipelines: Sales Pipeline, Bookkeeping, Qflavours
         -- Full parallel set: counts + amounts for won/lost/open + total
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.deals_won   ELSE 0 END) AS new_biz_deals_won,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.deals_lost  ELSE 0 END) AS new_biz_deals_lost,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.deals_open  ELSE 0 END) AS new_biz_deals_open,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.deals_total ELSE 0 END) AS new_biz_deals_total,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.amount_won  ELSE 0 END) AS new_biz_revenue_won,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.amount_lost ELSE 0 END) AS new_biz_amount_lost,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.amount_open ELSE 0 END) AS new_biz_amount_open,
         SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                  THEN d.amount_total ELSE 0 END) AS new_biz_amount_total
  FROM `{P}.{D}.hubspot_deals_daily` d
  JOIN `{P}.{D}.v_channel_key_map` m ON d.qoyod_source = m.qoyod_source
  GROUP BY 1,2
)
SELECT
  spine.date,
  spine.channel,
  COALESCE(s.spend, 0)                         AS spend,
  COALESCE(s.impressions, 0)                   AS impressions,
  COALESCE(s.clicks, 0)                        AS clicks,
  SAFE_DIVIDE(s.clicks, s.impressions) * 100   AS ctr,
  COALESCE(s.platform_leads, 0)                AS platform_leads,
  COALESCE(s.platform_conversions, 0)          AS platform_conversions,
  COALESCE(l.hs_leads, 0)        AS hs_leads,
  COALESCE(l.hs_qualified, 0)    AS hs_qualified,
  COALESCE(l.hs_disqualified, 0) AS hs_disqualified,
  COALESCE(l.hs_open, 0)         AS hs_open,
  -- Per-pipeline lead breakdowns (Lead Pipeline = accounting/e-invoice)
  COALESCE(l.leads_accounting, 0)        AS leads_accounting,
  COALESCE(l.qualified_accounting, 0)    AS qualified_accounting,
  COALESCE(l.disqualified_accounting, 0) AS disqualified_accounting,
  COALESCE(l.leads_bookkeeping, 0)       AS leads_bookkeeping,
  COALESCE(l.qualified_bookkeeping, 0)   AS qualified_bookkeeping,
  COALESCE(l.disqualified_bookkeeping, 0) AS disqualified_bookkeeping,
  -- Per-pipeline CPL/CPQL
  SAFE_DIVIDE(s.spend, l.leads_accounting)     AS cpl_accounting,
  SAFE_DIVIDE(s.spend, l.qualified_accounting) AS cpql_accounting,
  SAFE_DIVIDE(s.spend, l.leads_bookkeeping)    AS cpl_bookkeeping,
  SAFE_DIVIDE(s.spend, l.qualified_bookkeeping) AS cpql_bookkeeping,
  COALESCE(d.deals_total, 0)           AS deals_total,
  COALESCE(d.deals_won, 0)             AS deals_won,
  COALESCE(d.deals_lost, 0)            AS deals_lost,
  COALESCE(d.deals_open, 0)            AS deals_open,
  COALESCE(d.revenue_won, 0)           AS revenue_won,
  COALESCE(d.amount_lost, 0)           AS amount_lost,
  COALESCE(d.pipeline_open, 0)         AS pipeline_open,
  COALESCE(d.total_deal_amount, 0)     AS amount_total,
  -- New business pipelines (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
  COALESCE(d.new_biz_deals_won,   0)   AS new_biz_deals_won,
  COALESCE(d.new_biz_deals_lost,  0)   AS new_biz_deals_lost,
  COALESCE(d.new_biz_deals_open,  0)   AS new_biz_deals_open,
  COALESCE(d.new_biz_deals_total, 0)   AS new_biz_deals_total,
  COALESCE(d.new_biz_revenue_won, 0)   AS new_biz_revenue_won,
  COALESCE(d.new_biz_amount_lost, 0)   AS new_biz_amount_lost,
  COALESCE(d.new_biz_amount_open, 0)   AS new_biz_amount_open,
  COALESCE(d.new_biz_amount_total,0)   AS new_biz_amount_total,
  SAFE_DIVIDE(s.spend, l.hs_leads)     AS cpl,
  SAFE_DIVIDE(s.spend, l.hs_qualified) AS cpql,
  SAFE_DIVIDE(l.hs_qualified,   l.hs_qualified + l.hs_disqualified) * 100 AS qual_rate_pct,
  SAFE_DIVIDE(l.hs_disqualified, l.hs_qualified + l.hs_disqualified) * 100 AS disq_rate_pct,
  SAFE_DIVIDE(d.revenue_won,         s.spend) AS roas,
  SAFE_DIVIDE(d.new_biz_revenue_won, s.spend) AS new_biz_roas,
  SAFE_DIVIDE(d.deals_won, l.hs_leads) * 100  AS lead_to_deal_pct,
  -- Zone thresholds mirror config.py campaign-level CPL_*/CPQL_* (single source of truth).
  -- CPL:  scale <25 | acceptable <=35 | warning <=40 | else pause_zone
  CASE
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) IS NULL THEN 'no_data'
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) < 25 THEN 'scale'
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) <= 35 THEN 'acceptable'
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) <= 40 THEN 'warning'
    ELSE 'pause_zone'
  END AS cpl_zone,
  -- CPQL: scale <60 | acceptable <=80 | warning <=95 | else pause_zone
  CASE
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) IS NULL THEN 'no_data'
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) < 60 THEN 'scale'
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) <= 80 THEN 'acceptable'
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) <= 95 THEN 'warning'
    ELSE 'pause_zone'
  END AS cpql_zone
-- Spine-anchored: channel always appears for every date since its first campaign,
-- even on zero-spend / zero-lead days. spend/leads/deals LEFT JOINed on top.
FROM spine
LEFT JOIN spend s ON s.date = spine.date AND s.channel = spine.channel
LEFT JOIN leads l ON l.date = spine.date AND l.channel = spine.channel
LEFT JOIN deals d ON d.date = spine.date AND d.channel = spine.channel
"""


# ─── Unified paid-channel view (single source of truth for the dashboard) ────
# Joins ad-platform spend with HubSpot leads + deals, computing CPL/CPQL/ROAS
# in SQL.  All reporting MUST use this view — no Python-side spend/leads math.
#
# Date discipline: rows emitted only for date <= CURRENT_DATE('Asia/Riyadh') - 1.
# Today's data is always partial across platforms (Google Ads is T-1, Meta has
# 24h lag) so we ALWAYS cut at yesterday.  The dashboard tells the user
# "data through {yesterday}".
PAID_CHANNEL_CAMPAIGN_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.paid_channel_campaign_daily` AS
-- ID-first attribution (Option B, 2026-05-13):
--   spend is grouped by (date, channel, campaign_id) — the latest campaign_name
--   is just a display label via ANY_VALUE().
--   Leads + deals are split into two mutually-exclusive buckets:
--     *_by_id   → rows with lead/deal_campaign_id_sync IS NOT NULL
--                 (Snap/Meta/TikTok Instantform — native platform ID populated)
--     *_by_name → rows with sync_id IS NULL
--                 (Google/Bing/LinkedIn website forms — UTM name is the only signal)
--   Sums are safe because the two buckets are disjoint on sync_id.
-- This consolidates renames (same ID gets all leads+spend+deals regardless of
-- how often the name changed) AND separates duplicate-name campaigns by ID.
WITH
  channel_map AS (
    SELECT 'google_ads'    AS channel, 'Google Ads'    AS qoyod_source UNION ALL
    SELECT 'meta',                     'Meta Ads'                       UNION ALL
    SELECT 'snapchat',                 'Snapchat Ads'                   UNION ALL
    SELECT 'tiktok',                   'Tiktok Ads'                     UNION ALL
    SELECT 'linkedin',                 'LinkedIn Ads'                   UNION ALL
    SELECT 'microsoft_ads',            'Microsoft Ads'
  ),
  spend AS (
    SELECT date, channel, campaign_id,
           ANY_VALUE(campaign_name) AS campaign_name,   -- latest name for display
           ANY_VALUE(status)  AS status,
           SUM(spend)        AS spend,
           SUM(impressions)  AS impressions,
           SUM(clicks)       AS clicks
    FROM `{P}.{D}.campaigns_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY date, channel, campaign_id
  ),
  -- Leads: ID-matched bucket (Snap / Meta / TikTok Instantform)
  leads_by_id AS (
    SELECT date, qoyod_source, lead_campaign_id_sync AS campaign_id,
           ANY_VALUE(lead_utm_source) AS utm_source,
           SUM(leads_total)        AS leads,
           SUM(leads_qualified)    AS qualified,
           SUM(leads_disqualified) AS disqualified
    FROM `{P}.{D}.hubspot_leads_module_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
      AND lead_campaign_id_sync IS NOT NULL
    GROUP BY date, qoyod_source, lead_campaign_id_sync
  ),
  -- Leads: name-matched bucket (Google / Microsoft / LinkedIn website forms — no sync ID)
  leads_by_name AS (
    SELECT date, qoyod_source, lead_utm_campaign AS campaign_name,
           ANY_VALUE(lead_utm_source) AS utm_source,
           SUM(leads_total)        AS leads,
           SUM(leads_qualified)    AS qualified,
           SUM(leads_disqualified) AS disqualified
    FROM `{P}.{D}.hubspot_leads_module_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
      AND lead_campaign_id_sync IS NULL
    GROUP BY date, qoyod_source, lead_utm_campaign
  ),
  -- Deals: ID-matched bucket (new_biz + all-pipeline)
  deals_by_id AS (
    SELECT date, qoyod_source, deal_campaign_id_sync AS campaign_id,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_lost  ELSE 0 END) AS new_biz_deals_lost,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_open  ELSE 0 END) AS new_biz_deals_open,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_total ELSE 0 END) AS new_biz_deals_total,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_open ELSE 0 END) AS new_biz_amount_open,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_total ELSE 0 END) AS new_biz_amount_total,
           -- All pipelines
           SUM(deals_won)    AS all_deals_won,
           SUM(amount_won)   AS all_revenue_won,
           SUM(amount_lost)  AS all_amount_lost,
           SUM(amount_open)  AS all_amount_open,
           SUM(amount_total) AS all_amount_total
    FROM `{P}.{D}.hubspot_deals_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
      AND deal_campaign_id_sync IS NOT NULL
    GROUP BY date, qoyod_source, deal_campaign_id_sync
  ),
  -- Deals: name-matched bucket (new_biz + all-pipeline — no sync ID)
  deals_by_name AS (
    SELECT date, qoyod_source, deal_utm_campaign AS campaign_name,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_won   ELSE 0 END) AS new_biz_deals_won,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_lost  ELSE 0 END) AS new_biz_deals_lost,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_open  ELSE 0 END) AS new_biz_deals_open,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN deals_total ELSE 0 END) AS new_biz_deals_total,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_won  ELSE 0 END) AS new_biz_revenue_won,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_lost ELSE 0 END) AS new_biz_amount_lost,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_open ELSE 0 END) AS new_biz_amount_open,
           SUM(CASE WHEN pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN amount_total ELSE 0 END) AS new_biz_amount_total,
           -- All pipelines
           SUM(deals_won)    AS all_deals_won,
           SUM(amount_won)   AS all_revenue_won,
           SUM(amount_lost)  AS all_amount_lost,
           SUM(amount_open)  AS all_amount_open,
           SUM(amount_total) AS all_amount_total
    FROM `{P}.{D}.hubspot_deals_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
      AND deal_campaign_id_sync IS NULL
    GROUP BY date, qoyod_source, deal_utm_campaign
  )
SELECT
  s.date,
  s.channel,
  s.campaign_id,                                       -- NEW: exposed for disambiguation
  s.campaign_name,
  s.status,
  COALESCE(li.utm_source, ln.utm_source) AS utm_source,
  ROUND(s.spend, 2)         AS spend,
  s.impressions,
  s.clicks,
  -- Mutually exclusive buckets — sum is safe
  IFNULL(li.leads, 0)        + IFNULL(ln.leads, 0)        AS leads,
  IFNULL(li.qualified, 0)    + IFNULL(ln.qualified, 0)    AS qualified,
  IFNULL(li.disqualified, 0) + IFNULL(ln.disqualified, 0) AS disqualified,
  (IFNULL(li.leads,0) + IFNULL(ln.leads,0))
    - (IFNULL(li.qualified,0) + IFNULL(ln.qualified,0))
    - (IFNULL(li.disqualified,0) + IFNULL(ln.disqualified,0)) AS open_leads,
  -- New business deals — ID + name buckets summed
  IFNULL(di.new_biz_deals_won,   0) + IFNULL(dn.new_biz_deals_won,   0) AS new_biz_deals_won,
  IFNULL(di.new_biz_deals_lost,  0) + IFNULL(dn.new_biz_deals_lost,  0) AS new_biz_deals_lost,
  IFNULL(di.new_biz_deals_open,  0) + IFNULL(dn.new_biz_deals_open,  0) AS new_biz_deals_open,
  IFNULL(di.new_biz_deals_total, 0) + IFNULL(dn.new_biz_deals_total, 0) AS new_biz_deals_total,
  ROUND(IFNULL(di.new_biz_revenue_won, 0) + IFNULL(dn.new_biz_revenue_won, 0), 2) AS new_biz_revenue_won,
  ROUND(IFNULL(di.new_biz_amount_lost, 0) + IFNULL(dn.new_biz_amount_lost, 0), 2) AS new_biz_amount_lost,
  ROUND(IFNULL(di.new_biz_amount_open, 0) + IFNULL(dn.new_biz_amount_open, 0), 2) AS new_biz_amount_open,
  ROUND(IFNULL(di.new_biz_amount_total,0) + IFNULL(dn.new_biz_amount_total,0), 2) AS new_biz_amount_total,
  -- KPIs — use the summed lead totals
  ROUND(SAFE_DIVIDE(s.spend,
        NULLIF(IFNULL(li.leads,0) + IFNULL(ln.leads,0), 0)),     2) AS cpl,
  ROUND(SAFE_DIVIDE(s.spend,
        NULLIF(IFNULL(li.qualified,0) + IFNULL(ln.qualified,0), 0)), 2) AS cpql,
  ROUND(SAFE_DIVIDE(
        IFNULL(di.new_biz_revenue_won,0) + IFNULL(dn.new_biz_revenue_won,0),
        NULLIF(s.spend, 0)), 2) AS new_biz_roas,
  -- All-pipeline deals (all HubSpot pipelines, not just new_biz)
  IFNULL(di.all_deals_won,    0) + IFNULL(dn.all_deals_won,    0) AS all_deals_won,
  ROUND(IFNULL(di.all_revenue_won,  0) + IFNULL(dn.all_revenue_won,  0), 2) AS revenue_won,
  ROUND(IFNULL(di.all_amount_lost,  0) + IFNULL(dn.all_amount_lost,  0), 2) AS amount_lost,
  ROUND(IFNULL(di.all_amount_open,  0) + IFNULL(dn.all_amount_open,  0), 2) AS amount_open,
  ROUND(IFNULL(di.all_amount_total, 0) + IFNULL(dn.all_amount_total, 0), 2) AS amount_total,
  ROUND(SAFE_DIVIDE(
        IFNULL(di.all_revenue_won,0) + IFNULL(dn.all_revenue_won,0),
        NULLIF(s.spend, 0)), 2) AS roas,
  ROUND(SAFE_DIVIDE(s.clicks, NULLIF(s.impressions, 0)) * 100, 4) AS ctr_pct,
  ROUND(SAFE_DIVIDE(IFNULL(li.leads,0) + IFNULL(ln.leads,0),
        NULLIF(s.clicks, 0)) * 100, 4) AS cvr_pct,
  ROUND(SAFE_DIVIDE(IFNULL(li.qualified,0) + IFNULL(ln.qualified,0),
        NULLIF(IFNULL(li.leads,0) + IFNULL(ln.leads,0), 0)) * 100, 2) AS qual_rate_pct
FROM spend s
LEFT JOIN channel_map cm   ON cm.channel = s.channel
-- ID-match (Snap/Meta/TikTok Instantform — survives renames + separates duplicate names)
LEFT JOIN leads_by_id li   ON li.date = s.date
                          AND li.qoyod_source = cm.qoyod_source
                          AND li.campaign_id = s.campaign_id
-- Name-match (Google/Microsoft/LinkedIn website forms — no sync ID populated)
LEFT JOIN leads_by_name ln ON ln.date = s.date
                          AND ln.qoyod_source = cm.qoyod_source
                          AND LOWER(ln.campaign_name) = LOWER(s.campaign_name)
LEFT JOIN deals_by_id di   ON di.date = s.date
                          AND di.qoyod_source = cm.qoyod_source
                          AND di.campaign_id = s.campaign_id
LEFT JOIN deals_by_name dn ON dn.date = s.date
                          AND dn.qoyod_source = cm.qoyod_source
                          AND LOWER(dn.campaign_name) = LOWER(s.campaign_name)
"""


# Channel-level rollup view — same data aggregated to (date, channel)
PAID_CHANNEL_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.paid_channel_daily` AS
-- Lead totals come directly from hubspot_leads_module_daily by qoyod_source
-- (no campaign-name join) so ALL paid leads are counted, including those
-- with no UTM campaign. Spend comes from campaigns_daily. Campaign-level
-- drill-down lives in paid_channel_campaign_daily.
WITH
  channel_map AS (
    SELECT 'google_ads'   AS channel, 'Google Ads'   AS qoyod_source UNION ALL
    SELECT 'meta',                    'Meta Ads'                      UNION ALL
    SELECT 'snapchat',                'Snapchat Ads'                  UNION ALL
    SELECT 'tiktok',                  'Tiktok Ads'                    UNION ALL
    SELECT 'linkedin',                'LinkedIn Ads'                  UNION ALL
    SELECT 'microsoft_ads',           'Microsoft Ads'
  ),
  channel_first AS (
    SELECT channel, MIN(date) AS first_date
    FROM `{P}.{D}.campaigns_daily`
    GROUP BY channel
  ),
  spine AS (
    SELECT d AS date, cf.channel
    FROM UNNEST(GENERATE_DATE_ARRAY(
      DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 365 DAY),
      DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    )) AS d
    JOIN channel_first cf ON d >= cf.first_date
  ),
  spend AS (
    SELECT date, channel,
           SUM(spend)       AS spend,
           SUM(impressions) AS impressions,
           SUM(clicks)      AS clicks
    FROM `{P}.{D}.campaigns_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY date, channel
  ),
  leads AS (
    SELECT cm.channel,
           l.date,
           SUM(l.leads_total)        AS leads,
           SUM(l.leads_qualified)    AS qualified,
           SUM(l.leads_disqualified) AS disqualified,
           SUM(l.leads_open)         AS open_leads
    FROM `{P}.{D}.hubspot_leads_module_daily` l
    JOIN channel_map cm ON cm.qoyod_source = l.qoyod_source
    WHERE l.date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY cm.channel, l.date
  ),
  deals AS (
    SELECT cm.channel,
           d.date,
           SUM(d.deals_won)    AS deals_won,
           SUM(d.deals_lost)   AS deals_lost,
           SUM(d.deals_open)   AS deals_open,
           SUM(d.deals_total)  AS deals_total,
           SUM(d.amount_won)   AS revenue_won,
           SUM(d.amount_lost)  AS amount_lost,
           SUM(d.amount_open)  AS amount_open,
           SUM(d.amount_total) AS amount_total,
           -- New business pipelines (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.deals_won   ELSE 0 END) AS new_biz_deals_won,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.deals_lost  ELSE 0 END) AS new_biz_deals_lost,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.deals_open  ELSE 0 END) AS new_biz_deals_open,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.deals_total ELSE 0 END) AS new_biz_deals_total,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.amount_won  ELSE 0 END) AS new_biz_revenue_won,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.amount_lost ELSE 0 END) AS new_biz_amount_lost,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.amount_open ELSE 0 END) AS new_biz_amount_open,
           SUM(CASE WHEN d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
                    THEN d.amount_total ELSE 0 END) AS new_biz_amount_total
    FROM `{P}.{D}.hubspot_deals_daily` d
    JOIN channel_map cm ON cm.qoyod_source = d.qoyod_source
    WHERE d.date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY cm.channel, d.date
  )
SELECT
  spine.date,
  spine.channel,
  ROUND(IFNULL(s.spend, 0), 2)              AS spend,
  IFNULL(s.impressions, 0)                  AS impressions,
  IFNULL(s.clicks, 0)                       AS clicks,
  IFNULL(l.leads, 0)                        AS leads_total,
  IFNULL(l.qualified, 0)                    AS qualified,
  IFNULL(l.disqualified, 0)                 AS disqualified,
  IFNULL(l.open_leads, 0)                   AS open_leads,
  -- Deal metrics (all pipelines)
  IFNULL(d.deals_won, 0)                    AS deals_won,
  IFNULL(d.deals_lost, 0)                   AS deals_lost,
  IFNULL(d.deals_open, 0)                   AS deals_open,
  ROUND(IFNULL(d.revenue_won, 0), 2)        AS revenue_won,
  ROUND(IFNULL(d.amount_lost, 0), 2)        AS amount_lost,
  ROUND(IFNULL(d.amount_open, 0), 2)        AS amount_open,
  -- New business pipelines only (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
  IFNULL(d.new_biz_deals_won,   0)                  AS new_biz_deals_won,
  IFNULL(d.new_biz_deals_lost,  0)                  AS new_biz_deals_lost,
  IFNULL(d.new_biz_deals_open,  0)                  AS new_biz_deals_open,
  IFNULL(d.new_biz_deals_total, 0)                  AS new_biz_deals_total,
  ROUND(IFNULL(d.new_biz_revenue_won, 0), 2)        AS new_biz_revenue_won,
  ROUND(IFNULL(d.new_biz_amount_lost, 0), 2)        AS new_biz_amount_lost,
  ROUND(IFNULL(d.new_biz_amount_open, 0), 2)        AS new_biz_amount_open,
  ROUND(IFNULL(d.new_biz_amount_total,0), 2)        AS new_biz_amount_total,
  -- KPIs
  ROUND(SAFE_DIVIDE(IFNULL(s.spend,0), NULLIF(IFNULL(l.leads,0), 0)),          2) AS cpl,
  ROUND(SAFE_DIVIDE(IFNULL(s.spend,0), NULLIF(IFNULL(l.qualified,0), 0)),      2) AS cpql,
  ROUND(SAFE_DIVIDE(IFNULL(l.qualified,0), NULLIF(IFNULL(l.leads,0),0)) * 100, 2) AS qual_rate_pct,
  -- ROAS: all pipelines
  ROUND(SAFE_DIVIDE(IFNULL(d.revenue_won,0), NULLIF(IFNULL(s.spend,0), 0)),    2) AS roas,
  -- ROAS: new business only
  ROUND(SAFE_DIVIDE(IFNULL(d.new_biz_revenue_won,0), NULLIF(IFNULL(s.spend,0), 0)), 2) AS new_biz_roas
-- Spine-anchored: every channel appears for every date since its first campaign,
-- even on zero-spend / zero-lead days.
FROM spine
LEFT JOIN spend s ON s.date = spine.date AND s.channel = spine.channel
LEFT JOIN leads l ON l.date = spine.date AND l.channel = spine.channel
LEFT JOIN deals d ON d.date = spine.date AND d.channel = spine.channel
"""


AGENT_ACTIVITY_DASHBOARD_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_agent_activity_dashboard` AS
-- Daily counts per category, last 180 days. Powers the Hex activity dashboard heatmap.
WITH raw AS (
  SELECT
    DATE(ts, 'Asia/Riyadh') AS day,
    action,
    role,
    channel,
    campaign_name,
    status,
    COALESCE(rows_affected, 1) AS cnt
  FROM `{P}.{D}.agent_activity_log`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
    AND status NOT IN ('failed', 'skipped')
),
categorised AS (
  SELECT
    day,
    COALESCE(channel, 'general')  AS channel,
    campaign_name,
    CASE
      WHEN action IN ('campaign_created', 'user_created_campaign')
        THEN 'Campaigns Created'
      WHEN action IN ('launch', 'keyword_candidates_queued_for_weekly_review',
                      'positive_keywords_added')
           AND role = 'keyword_management'
        THEN 'Keywords Added'
      WHEN action IN ('keywords_paused', 'keywords_deleted')
        THEN 'Keywords Paused'
      WHEN action IN ('negative_keywords_added', 'negative_keywords_removed')
        THEN 'Negatives Added'
      WHEN action IN ('campaign_paused', 'pause_task_created', 'junk_leads_task_created')
        THEN 'Campaigns Paused'
      WHEN action IN ('campaign_scaled', 'scale_task_created')
        THEN 'Campaigns Scaled'
      WHEN action IN ('ads_paused', 'ads_enabled')
        THEN 'Ads Paused'
      WHEN action IN (
        'asana_task_created', 'asana_tasks_created',
        'optimize_task_created', 'drilldown_task_created'
      )
        THEN 'Asana Tasks'
      WHEN action IN ('detect_spikes', 'data_quality_autoheal')
        THEN 'Optimizations'
      WHEN action IN ('posted_slack_digest', 'slack_summary_posted',
                      'post_weekly_summary', 'nightly_audit_complete',
                      'cadence_daily_complete', 'cadence_nightly_complete',
                      'cadence_weekly_complete', 'cadence_monthly_complete')
        THEN 'Slack Messages'
      WHEN action IN ('posted_approvals_digest', 'approval_requested',
                      'action_approved_via_slack', 'action_rejected_via_slack')
        THEN 'Approvals'
      WHEN action IN (
        'user_completed_task', 'user_created_task',
        'user_executed_scale', 'user_executed_pause',
        'user_added_negative', 'user_reviewed_recommendation',
        'user_paused_campaign', 'user_enabled_campaign',
        'user_changed_budget', 'user_changed_status',
        'user_paused_ad', 'user_enabled_ad', 'user_created_campaign'
      ) OR role = 'user'
        THEN 'User Actions'
    END AS category,
    cnt
  FROM raw
)
SELECT
  day,
  category,
  channel,
  SUM(cnt) AS count
FROM categorised
WHERE category IS NOT NULL
GROUP BY day, category, channel
"""

ALL_VIEWS = [
    ("v_channel_key_map",            CHANNEL_MAP_SQL),
    # paid_channel_campaign_daily + paid_channel_daily + channel_roas_daily
    # are MATERIALIZED TABLES — handled by materialize_heavy_views()
    # Agent activity dashboard — powers Nexa-Agent-Activity Hex heatmap
    ("v_agent_activity_dashboard",   AGENT_ACTIVITY_DASHBOARD_SQL),
]

# Sub-campaign views (keyword / LP grain).
# Defined in bq_writer.py alongside their table schemas.
# Imported here so refresh_all_views() keeps them in sync automatically.
#
# Note: utm_paid_attribution_daily, v_adset_performance, v_ad_performance are
# MATERIALIZED TABLES (see _heavy_views_list). Only lightweight views live here.
def _sub_campaign_views():
    # utm_paid_attribution_daily, v_adset_performance, v_ad_performance are
    # MATERIALIZED TABLES — they live in _heavy_views_list() / materialize_heavy_views().
    # Only lightweight grain views that don't need instant-read speed live here.
    from collectors.bq_writer import (
        V_KEYWORD_PERFORMANCE_SQL,
    )
    return [
        ("v_keyword_performance",   V_KEYWORD_PERFORMANCE_SQL),
    ]


def _heavy_views_list():
    """
    Returns (name, sql) pairs for the 6 views that get materialised as physical
    tables so Hex reads are instant.  Listed in dependency order:
      utm_paid_attribution_daily must come before v_adset/v_ad_performance.
      paid_channel_campaign_daily must come before paid_channel_daily.
    """
    from collectors.bq_writer import (
        UTM_PAID_ATTRIBUTION_VIEW_SQL,
        V_ADSET_PERFORMANCE_SQL,
        V_AD_PERFORMANCE_SQL,
    )
    return [
        ("utm_paid_attribution_daily",  UTM_PAID_ATTRIBUTION_VIEW_SQL),
        ("paid_channel_campaign_daily", PAID_CHANNEL_CAMPAIGN_DAILY_SQL),
        ("channel_roas_daily",          CHANNEL_ROAS_DAILY_SQL),
        ("paid_channel_daily",          PAID_CHANNEL_DAILY_SQL),
        ("v_adset_performance",         V_ADSET_PERFORMANCE_SQL),
        ("v_ad_performance",            V_AD_PERFORMANCE_SQL),
    ]


def materialize_heavy_views():
    """
    Re-creates the 6 heaviest views as physical BQ tables (same names).
    Hex SQL cells need zero changes — they query the same table names.
    No staleness window: called automatically at the end of refresh_all_views()
    after each 6-hour scheduler cycle.

    On the first ever run the objects are VIEWs:
      CREATE OR REPLACE TABLE will fail with "different type" → we delete the
      view and retry.  On every subsequent run the objects are already TABLEs,
      so CREATE OR REPLACE TABLE succeeds directly.
    """
    client = get_client()
    heavy = _heavy_views_list()
    failed = []

    for name, view_sql in heavy:
        # Swap VIEW keyword → TABLE in the DDL (1st occurrence only)
        table_sql = view_sql.replace("CREATE OR REPLACE VIEW", "CREATE OR REPLACE TABLE", 1)
        try:
            client.query(table_sql).result()
            print(f"[materialize] OK: {name}")
        except Exception as first_err:
            err_str = str(first_err).lower()
            if any(s in err_str for s in ("already exists", "different type", "conflict", "not allowed", "type view", "currently has type")):
                # Object is still a VIEW from a prior run — drop it then retry
                try:
                    client.delete_table(f"{P}.{D}.{name}", not_found_ok=True)
                    client.query(table_sql).result()
                    print(f"[materialize] OK (replaced view): {name}")
                except Exception as second_err:
                    print(f"[materialize] FAIL: {name}: {second_err}")
                    failed.append((name, str(second_err)))
            else:
                print(f"[materialize] FAIL: {name}: {first_err}")
                failed.append((name, str(first_err)))

    if failed:
        names = ", ".join(n for n, _ in failed)
        raise RuntimeError(f"[materialize] {len(failed)} table(s) failed: {names}")
    print(f"[materialize] Done — {len(heavy)} tables refreshed.")


def refresh_all_views():
    client = get_client()
    all_views = ALL_VIEWS + _sub_campaign_views()
    failed = []
    for name, sql in all_views:
        try:
            client.query(sql).result()
            print(f"[views] OK: {name}")
        except Exception as e:
            print(f"[views] FAIL: {name}: {e}")
            failed.append((name, str(e)))
    if failed:
        names = ", ".join(n for n, _ in failed)
        raise RuntimeError(f"[views] {len(failed)} view(s) failed: {names}")
    print(f"[views] Refreshed {len(all_views)} views.")
    # Materialise heavy views as physical tables so Hex reads are instant.
    # Runs immediately after view DDL so the tables always reflect the latest SQL.
    materialize_heavy_views()


if __name__ == "__main__":
    refresh_all_views()
