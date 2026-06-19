"""
Unified reporting views — channel and campaign grain.

Store tables (source of truth, never queried directly by Python analysers):
  - hubspot_leads_individual    (record-level HubSpot leads mirror, 2025-01-01+)
  - hubspot_deals_individual    (record-level HubSpot deals mirror, all pipelines, 2025-01-01+)
  - ads_daily / adsets_daily / campaigns_daily / keywords_daily (platform spend store)

Compat views (ALL_VIEWS — lightweight, refreshed every 6h by refresh_all_views()):
  - hubspot_leads_module_daily  (aggregates from hubspot_leads_individual — backward compat)
  - hubspot_deals_daily         (aggregates from hubspot_deals_individual — backward compat)
  - v_channel_key_map           (RESTORED 2026-06-16 — still referenced by Hex SQL cells)
  - v_new_biz_daily             (DROPPED 2026-06-16 — 0 active consumers)
  - v_agent_activity_dashboard  (DROPPED 2026-06-16 — 0 active consumers)
  - v_keyword_performance       (keyword grain, via _sub_campaign_views())

Materialized tables (rebuilt every 6h by materialize_heavy_views() — all source from wide_ads):
  - paid_channel_campaign_daily (campaign grain rollup)
  - paid_channel_daily          (channel grain rollup)
  - v_adset_performance         (adset grain rollup)
  - v_ad_performance            (ad grain rollup — essentially wide_ads with column aliases)
  - wide_ads                    (ad grain, id-first attribution — primary reporting table)
  - wide_keywords               (keyword grain — primary reporting table)
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
         WHEN 'tiktok'         THEN 'TikTok Ads'
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


PAID_CHANNEL_CAMPAIGN_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.paid_channel_campaign_daily` AS
SELECT
  date,
  channel,
  campaign_id,
  ANY_VALUE(campaign_name)                                                             AS campaign_name,
  ANY_VALUE(status)                                                                    AS status,
  CAST(NULL AS STRING)                                                                 AS utm_source,
  ROUND(SUM(spend), 2)                                                                AS spend,
  SUM(impressions)                                                                     AS impressions,
  SUM(clicks)                                                                          AS clicks,
  SUM(leads_total)                                                                     AS leads,
  SUM(leads_qualified)                                                                 AS qualified,
  SUM(leads_disqualified)                                                              AS disqualified,
  SUM(leads_open)                                                                      AS open_leads,
  SUM(new_biz_deals_won)                                                               AS new_biz_deals_won,
  SUM(new_biz_deals_lost)                                                              AS new_biz_deals_lost,
  SUM(new_biz_deals_open)                                                              AS new_biz_deals_open,
  SUM(new_biz_deals_total)                                                             AS new_biz_deals_total,
  ROUND(SUM(new_biz_revenue_won), 2)                                                  AS new_biz_revenue_won,
  ROUND(SUM(new_biz_amount_lost), 2)                                                  AS new_biz_amount_lost,
  ROUND(SUM(new_biz_amount_open), 2)                                                  AS new_biz_amount_open,
  ROUND(SUM(new_biz_revenue_won)+SUM(new_biz_amount_lost)+SUM(new_biz_amount_open), 2) AS new_biz_amount_total,
  SUM(all_deals_won)                                                                   AS all_deals_won,
  ROUND(SUM(all_revenue_won), 2)                                                      AS revenue_won,
  ROUND(SUM(all_amount_lost), 2)                                                      AS amount_lost,
  ROUND(SUM(all_amount_open), 2)                                                      AS amount_open,
  ROUND(SUM(all_revenue_won)+SUM(all_amount_lost)+SUM(all_amount_open), 2)            AS amount_total,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)), 2)                     AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)                 AS cpql,
  ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)             AS new_biz_roas,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won), NULLIF(SUM(spend), 0)), 2)                 AS roas,
  ROUND(SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) * 100, 4)              AS ctr_pct,
  ROUND(SAFE_DIVIDE(SUM(leads_total), NULLIF(SUM(clicks), 0)) * 100, 4)              AS cvr_pct,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),
    NULLIF(SUM(leads_qualified)+SUM(leads_disqualified), 0)) * 100, 2)               AS qual_rate_pct
FROM `{P}.{D}.wide_ads`
GROUP BY date, channel, campaign_id
-- Note: HAVING with aggregates is not allowed in BQ VIEWs.
-- wide_ads already filters WHERE spend > 0, so ghost rows are excluded at source.
"""


# ── dummy placeholder so old imports don't break ──────────────────────────────
CHANNEL_ROAS_DAILY_SQL = ""  # dropped — 0 consumers; wide_ads is the source now


# Channel-level rollup — simple GROUP BY on wide_ads (id-first attribution already done)
PAID_CHANNEL_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.paid_channel_daily` AS
SELECT
  date,
  channel,
  ROUND(SUM(spend), 2)                                                         AS spend,
  SUM(impressions)                                                              AS impressions,
  SUM(clicks)                                                                   AS clicks,
  SUM(leads_total)                                                              AS leads_total,
  SUM(leads_qualified)                                                          AS qualified,
  SUM(leads_disqualified)                                                       AS disqualified,
  SUM(leads_open)                                                               AS open_leads,
  SUM(all_deals_won)                                                            AS deals_won,
  SUM(new_biz_deals_lost)                                                       AS deals_lost,
  SUM(new_biz_deals_open)                                                       AS deals_open,
  ROUND(SUM(all_revenue_won), 2)                                               AS revenue_won,
  ROUND(SUM(all_amount_lost), 2)                                               AS amount_lost,
  ROUND(SUM(all_amount_open), 2)                                               AS amount_open,
  SUM(new_biz_deals_won)                                                        AS new_biz_deals_won,
  SUM(new_biz_deals_lost)                                                       AS new_biz_deals_lost,
  SUM(new_biz_deals_open)                                                       AS new_biz_deals_open,
  SUM(new_biz_deals_total)                                                      AS new_biz_deals_total,
  ROUND(SUM(new_biz_revenue_won), 2)                                           AS new_biz_revenue_won,
  ROUND(SUM(new_biz_amount_lost), 2)                                           AS new_biz_amount_lost,
  ROUND(SUM(new_biz_amount_open), 2)                                           AS new_biz_amount_open,
  ROUND(SUM(new_biz_revenue_won)+SUM(new_biz_amount_lost)+SUM(new_biz_amount_open), 2) AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)), 2)              AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)          AS cpql,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),
    NULLIF(SUM(leads_qualified)+SUM(leads_disqualified), 0)) * 100, 2)        AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(all_revenue_won), NULLIF(SUM(spend), 0)), 2)          AS roas,
  ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)      AS new_biz_roas
FROM `{P}.{D}.wide_ads`
GROUP BY date, channel
"""


UNIFIED_CHANNEL_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_unified_channel_daily` AS

-- Branch 1: Paid channels — from paid_channel_daily (channel-grain rollup of wide_ads)
SELECT
  date,
  channel,
  'paid'                          AS source_type,
  spend,
  impressions,
  clicks,
  CAST(NULL AS INT64)             AS sessions,
  CAST(NULL AS INT64)             AS new_users,
  CAST(NULL AS FLOAT64)           AS bounce_rate,
  leads_total,
  qualified                       AS leads_qualified,
  cpl,
  cpql,
  qual_rate_pct,
  roas,
  CAST(NULL AS INT64)             AS search_impressions,
  CAST(NULL AS FLOAT64)           AS avg_position,
  CAST(NULL AS INT64)             AS engagements,
  CAST(NULL AS INT64)             AS reach,
  CAST(NULL AS INT64)             AS followers_gained,
  CAST(NULL AS FLOAT64)           AS watch_time_min
FROM `{P}.{D}.paid_channel_daily`

UNION ALL

-- Branch 2: Organic search — Google Search Console, aggregated to date grain
SELECT
  date,
  'organic_search'                AS channel,
  'organic'                       AS source_type,
  CAST(NULL AS FLOAT64)           AS spend,
  CAST(NULL AS INT64)             AS impressions,
  SUM(clicks)                     AS clicks,
  CAST(NULL AS INT64)             AS sessions,
  CAST(NULL AS INT64)             AS new_users,
  CAST(NULL AS FLOAT64)           AS bounce_rate,
  CAST(NULL AS INT64)             AS leads_total,
  CAST(NULL AS INT64)             AS leads_qualified,
  CAST(NULL AS FLOAT64)           AS cpl,
  CAST(NULL AS FLOAT64)           AS cpql,
  CAST(NULL AS FLOAT64)           AS qual_rate_pct,
  CAST(NULL AS FLOAT64)           AS roas,
  SUM(impressions)                AS search_impressions,
  ROUND(AVG(position), 1)         AS avg_position,
  CAST(NULL AS INT64)             AS engagements,
  CAST(NULL AS INT64)             AS reach,
  CAST(NULL AS INT64)             AS followers_gained,
  CAST(NULL AS FLOAT64)           AS watch_time_min
FROM `{P}.{D}.gsc_organic_daily`
GROUP BY date

UNION ALL

-- Branch 3: Organic web — GA4 sessions, aggregated across property_ids per date
SELECT
  date,
  'organic_web'                   AS channel,
  'organic'                       AS source_type,
  CAST(NULL AS FLOAT64)           AS spend,
  CAST(NULL AS INT64)             AS impressions,
  CAST(NULL AS INT64)             AS clicks,
  SUM(sessions)                   AS sessions,
  SUM(new_users)                  AS new_users,
  AVG(bounce_rate)                AS bounce_rate,
  CAST(NULL AS INT64)             AS leads_total,
  CAST(NULL AS INT64)             AS leads_qualified,
  CAST(NULL AS FLOAT64)           AS cpl,
  CAST(NULL AS FLOAT64)           AS cpql,
  CAST(NULL AS FLOAT64)           AS qual_rate_pct,
  CAST(NULL AS FLOAT64)           AS roas,
  CAST(NULL AS INT64)             AS search_impressions,
  CAST(NULL AS FLOAT64)           AS avg_position,
  CAST(NULL AS INT64)             AS engagements,
  CAST(NULL AS INT64)             AS reach,
  CAST(NULL AS INT64)             AS followers_gained,
  CAST(NULL AS FLOAT64)           AS watch_time_min
FROM `{P}.{D}.ga4_sessions_daily`
GROUP BY date

UNION ALL

-- Branch 4: Meta Facebook organic — one row per date from organic_page_daily
SELECT
  date,
  'meta_organic'                  AS channel,
  'organic'                       AS source_type,
  CAST(NULL AS FLOAT64)           AS spend,
  fb_impressions                  AS impressions,
  CAST(NULL AS INT64)             AS clicks,
  CAST(NULL AS INT64)             AS sessions,
  CAST(NULL AS INT64)             AS new_users,
  CAST(NULL AS FLOAT64)           AS bounce_rate,
  CAST(NULL AS INT64)             AS leads_total,
  CAST(NULL AS INT64)             AS leads_qualified,
  CAST(NULL AS FLOAT64)           AS cpl,
  CAST(NULL AS FLOAT64)           AS cpql,
  CAST(NULL AS FLOAT64)           AS qual_rate_pct,
  CAST(NULL AS FLOAT64)           AS roas,
  CAST(NULL AS INT64)             AS search_impressions,
  CAST(NULL AS FLOAT64)           AS avg_position,
  fb_engagements                  AS engagements,
  fb_reach                        AS reach,
  fb_new_followers                AS followers_gained,
  CAST(NULL AS FLOAT64)           AS watch_time_min
FROM `{P}.{D}.organic_page_daily`

UNION ALL

-- Branch 5: Instagram organic — from organic_page_daily
SELECT
  date,
  'instagram_organic'             AS channel,
  'organic'                       AS source_type,
  CAST(NULL AS FLOAT64)           AS spend,
  ig_impressions                  AS impressions,
  ig_website_clicks               AS clicks,
  CAST(NULL AS INT64)             AS sessions,
  CAST(NULL AS INT64)             AS new_users,
  CAST(NULL AS FLOAT64)           AS bounce_rate,
  CAST(NULL AS INT64)             AS leads_total,
  CAST(NULL AS INT64)             AS leads_qualified,
  CAST(NULL AS FLOAT64)           AS cpl,
  CAST(NULL AS FLOAT64)           AS cpql,
  CAST(NULL AS FLOAT64)           AS qual_rate_pct,
  CAST(NULL AS FLOAT64)           AS roas,
  CAST(NULL AS INT64)             AS search_impressions,
  CAST(NULL AS FLOAT64)           AS avg_position,
  CAST(NULL AS INT64)             AS engagements,
  ig_reach                        AS reach,
  ig_followers                    AS followers_gained,
  CAST(NULL AS FLOAT64)           AS watch_time_min
FROM `{P}.{D}.organic_page_daily`

UNION ALL

-- Branch 6: YouTube organic — from organic_page_daily
SELECT
  date,
  'youtube_organic'               AS channel,
  'organic'                       AS source_type,
  CAST(NULL AS FLOAT64)           AS spend,
  yt_views                        AS impressions,
  CAST(NULL AS INT64)             AS clicks,
  CAST(NULL AS INT64)             AS sessions,
  CAST(NULL AS INT64)             AS new_users,
  CAST(NULL AS FLOAT64)           AS bounce_rate,
  CAST(NULL AS INT64)             AS leads_total,
  CAST(NULL AS INT64)             AS leads_qualified,
  CAST(NULL AS FLOAT64)           AS cpl,
  CAST(NULL AS FLOAT64)           AS cpql,
  CAST(NULL AS FLOAT64)           AS qual_rate_pct,
  CAST(NULL AS FLOAT64)           AS roas,
  CAST(NULL AS INT64)             AS search_impressions,
  CAST(NULL AS FLOAT64)           AS avg_position,
  CAST(NULL AS INT64)             AS engagements,
  CAST(NULL AS INT64)             AS reach,
  yt_subscribers                  AS followers_gained,
  CAST(yt_watch_time_min AS FLOAT64) AS watch_time_min
FROM `{P}.{D}.organic_page_daily`

UNION ALL

-- Branch 7: LinkedIn organic — from organic_page_daily
SELECT
  date,
  'linkedin_organic'              AS channel,
  'organic'                       AS source_type,
  CAST(NULL AS FLOAT64)           AS spend,
  li_impressions                  AS impressions,
  li_clicks                       AS clicks,
  CAST(NULL AS INT64)             AS sessions,
  CAST(NULL AS INT64)             AS new_users,
  CAST(NULL AS FLOAT64)           AS bounce_rate,
  CAST(NULL AS INT64)             AS leads_total,
  CAST(NULL AS INT64)             AS leads_qualified,
  CAST(NULL AS FLOAT64)           AS cpl,
  CAST(NULL AS FLOAT64)           AS cpql,
  CAST(NULL AS FLOAT64)           AS qual_rate_pct,
  CAST(NULL AS FLOAT64)           AS roas,
  CAST(NULL AS INT64)             AS search_impressions,
  CAST(NULL AS FLOAT64)           AS avg_position,
  li_engagement                   AS engagements,
  CAST(NULL AS INT64)             AS reach,
  li_followers                    AS followers_gained,
  CAST(NULL AS FLOAT64)           AS watch_time_min
FROM `{P}.{D}.organic_page_daily`
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

# All new_biz deals — NO channel filter.
# Use this view for dashboard "New Biz Total" cards (matching HubSpot all-sources count).
# paid_channel_daily.new_biz_* columns show PAID-ONLY (inner-joined to v_channel_key_map);
# this view is the correct source for the aggregate overview section.
NEW_BIZ_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_new_biz_daily` AS
SELECT
  date,
  pipeline,
  qoyod_source,
  SUM(deals_total)  AS deals_total,
  SUM(deals_won)    AS deals_won,
  SUM(deals_lost)   AS deals_lost,
  SUM(deals_open)   AS deals_open,
  SUM(amount_total) AS amount_total,
  SUM(amount_won)   AS amount_won,
  SUM(amount_lost)  AS amount_lost,
  SUM(amount_open)  AS amount_open
FROM `{P}.{D}.hubspot_deals_daily`
WHERE pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours')
  AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
GROUP BY date, pipeline, qoyod_source
"""

# ── Compat views: HubSpot daily buckets replaced by aggregations on individual tables ─
# Physical tables were dropped in wide-table redesign Step 4 (2026-06-15).
# All group-B chain SQLs and Python consumers continue to query the same names —
# they now read through these lightweight views instead of physical tables.
HUBSPOT_LEADS_MODULE_COMPAT_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.hubspot_leads_module_daily` AS
SELECT
  hs_createdate                                                          AS date,
  qoyod_source,
  pipeline,
  stage,
  lead_utm_campaign,
  lead_utm_audience,
  lead_utm_content,
  lead_utm_source,
  lead_utm_medium,
  lead_utm_term,
  COUNT(*)                                                               AS leads_total,
  COUNTIF(is_qualified)                                                  AS leads_qualified,
  COUNTIF(is_disqualified)                                               AS leads_disqualified,
  COUNTIF(is_open)                                                       AS leads_open,
  APPROX_TOP_COUNT(top_disq_reason, 1)[SAFE_OFFSET(0)].value            AS top_disq_reason,
  MAX(updated_at)                                                        AS updated_at,
  APPROX_TOP_COUNT(top_disq_sub_reason, 1)[SAFE_OFFSET(0)].value        AS top_disq_sub_reason,
  CAST(NULL AS STRING)                                                   AS lead_campaign_id,
  CAST(NULL AS STRING)                                                   AS lead_ad_group_id,
  CAST(NULL AS STRING)                                                   AS lead_ad_id,
  ANY_VALUE(lead_campaign_id_sync)                                       AS lead_campaign_id_sync,
  ANY_VALUE(lead_adgroup_id_sync)                                        AS lead_adgroup_id_sync,
  ANY_VALUE(lead_ad_id_sync)                                             AS lead_ad_id_sync,
  ANY_VALUE(lead_google_ad_click_id)                                     AS lead_google_ad_click_id,
  ANY_VALUE(lead_cta_source_sync)                                        AS lead_cta_source_sync,
  ANY_VALUE(lead_cta_source_url)                                         AS lead_cta_source_url,
  ANY_VALUE(ga4_client_id)                                               AS ga4_client_id
FROM `{P}.{D}.hubspot_leads_individual`
GROUP BY 1,2,3,4,5,6,7,8,9,10
"""

HUBSPOT_DEALS_COMPAT_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.hubspot_deals_daily` AS
SELECT
  createdate                                                             AS date,
  qoyod_source,
  pipeline,
  stage_status,
  deal_utm_campaign,
  deal_utm_audience,
  deal_utm_content,
  deal_utm_source,
  deal_utm_medium,
  deal_utm_term,
  COUNT(*)                                                               AS deals_total,
  COUNTIF(is_won)                                                        AS deals_won,
  COUNTIF(is_lost)                                                       AS deals_lost,
  COUNTIF(is_open)                                                       AS deals_open,
  SUM(amount)                                                            AS amount_total,
  SUM(IF(is_won,  amount, 0))                                            AS amount_won,
  SUM(IF(is_lost, amount, 0))                                            AS amount_lost,
  SUM(IF(is_open, amount, 0))                                            AS amount_open,
  CAST(NULL AS FLOAT64)                                                  AS avg_time_in_current_stage_ms,
  MAX(updated_at)                                                        AS updated_at,
  ANY_VALUE(currency)                                                    AS currency,
  SUM(amount_native)                                                     AS amount_total_native,
  SUM(IF(is_won,  amount_native, 0))                                     AS amount_won_native,
  SUM(IF(is_lost, amount_native, 0))                                     AS amount_lost_native,
  SUM(IF(is_open, amount_native, 0))                                     AS amount_open_native,
  ANY_VALUE(currency_native)                                             AS currency_native,
  ANY_VALUE(deal_campaign_id_sync)                                       AS deal_campaign_id_sync,
  ANY_VALUE(deal_adgroup_id_sync)                                        AS deal_adgroup_id_sync,
  ANY_VALUE(deal_ad_id_sync)                                             AS deal_ad_id_sync
FROM `{P}.{D}.hubspot_deals_individual`
GROUP BY 1,2,3,4,5,6,7,8,9,10
"""


ALL_VIEWS = [
    # v_channel_key_map RESTORED 2026-06-16 — still referenced by Hex SQL cells
    ("v_channel_key_map",             CHANNEL_MAP_SQL),
    # HubSpot compat views — aggregate from individual store tables (wide-table redesign step 4)
    ("hubspot_leads_module_daily",     HUBSPOT_LEADS_MODULE_COMPAT_SQL),
    ("hubspot_deals_daily",            HUBSPOT_DEALS_COMPAT_SQL),
    # RESTORED 2026-06-17 — n8n on-demand workflows (campaign-health, period-compare) query these views
    ("paid_channel_daily",             PAID_CHANNEL_DAILY_SQL),
    # RESTORED 2026-06-19 — Hex campaign-grain cells and scripts (reconcile_views, cowork skills) query this
    # (previous "aggregation-of-aggregation bug" note was incorrect — SQL sources from wide_ads directly)
    ("paid_channel_campaign_daily",    PAID_CHANNEL_CAMPAIGN_DAILY_SQL),
    # Unified paid + organic view — single reporting table for Databox covering all channels (added 2026-06-19)
    ("v_unified_channel_daily",        UNIFIED_CHANNEL_DAILY_SQL),
    # v_new_biz_daily and v_agent_activity_dashboard DROPPED 2026-06-16 (0 active consumers)
]

# Sub-campaign views (adset, ad, keyword grain).
# v_adset_performance RESTORED 2026-06-19 — cowork skills (pmax-decoder, wasted-spend-finder),
#   reconcile_views.py, and growth-analyst agent all query this view.
# v_ad_performance RESTORED 2026-06-17 — n8n on-demand ad-audit workflow queries it.
# v_keyword_performance is defined in bq_writer.py.
def _sub_campaign_views():
    from collectors.bq_writer import (
        V_KEYWORD_PERFORMANCE_SQL,
        V_AD_PERFORMANCE_SQL,
        V_ADSET_PERFORMANCE_SQL,
    )
    return [
        ("v_adset_performance",     V_ADSET_PERFORMANCE_SQL),
        ("v_keyword_performance",   V_KEYWORD_PERFORMANCE_SQL),
        ("v_ad_performance",        V_AD_PERFORMANCE_SQL),
    ]


# ── Wide-table redesign: new reporting views on store tables ─────────────────
# Grain: date × channel × ad_id (wide_ads) or keyword_id (wide_keywords).
# Joins spend ↔ leads ↔ deals directly from the 6 store tables — no intermediate
# views needed. Pre-aggregating both sides before joining prevents fan-out.
# id-first join strategy: platform sync ID → utm name fallback (mutually exclusive).
WIDE_ADS_SQL = f"""
CREATE OR REPLACE TABLE `{P}.{D}.wide_ads` AS
-- Ad-grain reporting: spend (ads_daily) + leads (hubspot_leads_individual)
-- + deals (hubspot_deals_individual). Single grain — safe to GROUP BY up.
--
-- Fix A (2026-06-16): COALESCE campaign_name/adset_name from lookup tables
--   so Snapchat (100% NULL campaign_name) and TikTok (100% NULL campaign_name)
--   rows get populated names. camp_lookup/adset_lookup join on (channel, id).
-- Fix B (2026-06-16): date join RETAINED in leads_by_id to prevent fan-out.
--   Removing the date caused 30x lead overcounting (lifetime leads attached to
--   every daily spend row). Known limitation: ~39% of leads arrive on a
--   different date than spend (hs_createdate ≠ ads_daily.date). Accepted
--   trade-off — undercounting is safer than overcounting for CPQL decisions.
-- Fix C (2026-06-16): ads_daily source filtered to spend > 0 to eliminate
--   Snapchat ghost rows (97.1% of Snap rows had zero spend, polluting counts).
WITH

-- Leads aggregated by ad sync ID (Meta/Snap/TikTok Instantform — survives ad renames)
-- Date join retained: removes fan-out (without date, lifetime leads appear on every
-- daily spend row → 30x overcounting). Leads arriving on different days from spend
-- are a known limitation (< 39% captured); accepted trade-off vs overcounting.
leads_by_id AS (
  SELECT
    hs_createdate                    AS date,
    lead_ad_id_sync                  AS ad_id,
    COUNT(*)                         AS leads_total,
    COUNTIF(is_qualified)            AS leads_qualified,
    COUNTIF(is_disqualified)         AS leads_disqualified,
    COUNTIF(is_open)                 AS leads_open
  FROM `{P}.{D}.hubspot_leads_individual`
  WHERE lead_ad_id_sync IS NOT NULL
  GROUP BY 1, 2
),

-- Leads aggregated by utm_content (Google/MS/LinkedIn website forms — no sync ID)
leads_by_name AS (
  SELECT
    hs_createdate                        AS date,
    LOWER(TRIM(lead_utm_content))        AS utm_key,
    COUNT(*)                             AS leads_total,
    COUNTIF(is_qualified)                AS leads_qualified,
    COUNTIF(is_disqualified)             AS leads_disqualified,
    COUNTIF(is_open)                     AS leads_open
  FROM `{P}.{D}.hubspot_leads_individual`
  WHERE lead_ad_id_sync IS NULL AND lead_utm_content IS NOT NULL
  GROUP BY 1, 2
),

-- Deals aggregated by ad sync ID (date retained — prevents fan-out)
deals_by_id AS (
  SELECT
    createdate                           AS date,
    deal_ad_id_sync                      AS ad_id,
    COUNTIF(is_won AND is_new_biz)       AS new_biz_deals_won,
    COUNTIF(is_lost AND is_new_biz)      AS new_biz_deals_lost,
    COUNTIF(is_open AND is_new_biz)      AS new_biz_deals_open,
    COUNTIF(is_new_biz)                  AS new_biz_deals_total,
    SUM(CASE WHEN is_won  AND is_new_biz THEN amount ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN is_lost AND is_new_biz THEN amount ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN is_open AND is_new_biz THEN amount ELSE 0 END) AS new_biz_amount_open,
    COUNTIF(is_won)                      AS all_deals_won,
    SUM(CASE WHEN is_won  THEN amount ELSE 0 END) AS all_revenue_won,
    SUM(CASE WHEN is_lost THEN amount ELSE 0 END) AS all_amount_lost,
    SUM(CASE WHEN is_open THEN amount ELSE 0 END) AS all_amount_open
  FROM `{P}.{D}.hubspot_deals_individual`
  WHERE deal_ad_id_sync IS NOT NULL
  GROUP BY 1, 2
),

-- Deals aggregated by utm_content (name fallback)
deals_by_name AS (
  SELECT
    createdate                           AS date,
    LOWER(TRIM(deal_utm_content))        AS utm_key,
    COUNTIF(is_won AND is_new_biz)       AS new_biz_deals_won,
    COUNTIF(is_lost AND is_new_biz)      AS new_biz_deals_lost,
    COUNTIF(is_open AND is_new_biz)      AS new_biz_deals_open,
    COUNTIF(is_new_biz)                  AS new_biz_deals_total,
    SUM(CASE WHEN is_won  AND is_new_biz THEN amount ELSE 0 END) AS new_biz_revenue_won,
    SUM(CASE WHEN is_lost AND is_new_biz THEN amount ELSE 0 END) AS new_biz_amount_lost,
    SUM(CASE WHEN is_open AND is_new_biz THEN amount ELSE 0 END) AS new_biz_amount_open,
    COUNTIF(is_won)                      AS all_deals_won,
    SUM(CASE WHEN is_won  THEN amount ELSE 0 END) AS all_revenue_won,
    SUM(CASE WHEN is_lost THEN amount ELSE 0 END) AS all_amount_lost,
    SUM(CASE WHEN is_open THEN amount ELSE 0 END) AS all_amount_open
  FROM `{P}.{D}.hubspot_deals_individual`
  WHERE deal_ad_id_sync IS NULL AND deal_utm_content IS NOT NULL
  GROUP BY 1, 2
)

SELECT
  a.date,
  a.channel,
  CASE a.channel
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'meta'          THEN 'Meta Ads'
    WHEN 'snapchat'      THEN 'Snapchat Ads'
    WHEN 'tiktok'        THEN 'TikTok Ads'
    WHEN 'linkedin'      THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    WHEN 'youtube'       THEN 'YouTube Ads'
    ELSE INITCAP(REPLACE(a.channel, '_', ' '))
  END                                                               AS channel_name,
  a.account_id,
  a.campaign_id,
  -- Fix A: COALESCE from lookup tables for Snapchat/TikTok which have NULL campaign_name in ads_daily
  COALESCE(a.campaign_name, camp_lookup.campaign_name)             AS campaign_name,
  a.adset_id,
  COALESCE(a.adset_name,    adset_lookup.adset_name)               AS adset_name,
  a.ad_id,
  a.ad_name,
  a.utm_content,
  a.status,
  a.creative_type,
  a.final_url,
  -- Spend metrics (source: ads_daily)
  COALESCE(a.spend, 0)                                              AS spend,
  COALESCE(a.impressions, 0)                                        AS impressions,
  COALESCE(a.clicks, 0)                                             AS clicks,
  SAFE_DIVIDE(a.clicks, NULLIF(a.impressions, 0))                   AS ctr,
  a.leads                                                           AS platform_leads,
  -- Leads (authoritative: HubSpot) — id-match first, name fallback
  COALESCE(li.leads_total,        ln.leads_total,        0)         AS leads_total,
  COALESCE(li.leads_qualified,    ln.leads_qualified,    0)         AS leads_qualified,
  COALESCE(li.leads_disqualified, ln.leads_disqualified, 0)         AS leads_disqualified,
  COALESCE(li.leads_open,         ln.leads_open,         0)         AS leads_open,
  -- Deals — new-biz pipelines (Sales Pipeline / Bookkeeping / Qflavours)
  COALESCE(di.new_biz_deals_won,   dn.new_biz_deals_won,   0)      AS new_biz_deals_won,
  COALESCE(di.new_biz_deals_lost,  dn.new_biz_deals_lost,  0)      AS new_biz_deals_lost,
  COALESCE(di.new_biz_deals_open,  dn.new_biz_deals_open,  0)      AS new_biz_deals_open,
  COALESCE(di.new_biz_deals_total, dn.new_biz_deals_total, 0)      AS new_biz_deals_total,
  COALESCE(di.new_biz_revenue_won, dn.new_biz_revenue_won, 0)      AS new_biz_revenue_won,
  COALESCE(di.new_biz_amount_lost, dn.new_biz_amount_lost, 0)      AS new_biz_amount_lost,
  COALESCE(di.new_biz_amount_open, dn.new_biz_amount_open, 0)      AS new_biz_amount_open,
  -- Deals — all pipelines (use for total revenue across Renewal, QoyodK, etc.)
  COALESCE(di.all_deals_won,       dn.all_deals_won,       0)      AS all_deals_won,
  COALESCE(di.all_revenue_won,     dn.all_revenue_won,     0)      AS all_revenue_won,
  COALESCE(di.all_amount_lost,     dn.all_amount_lost,     0)      AS all_amount_lost,
  COALESCE(di.all_amount_open,     dn.all_amount_open,     0)      AS all_amount_open,
  -- Derived KPIs (use leads_total/qualified from HubSpot, not platform_leads)
  SAFE_DIVIDE(a.spend, NULLIF(COALESCE(li.leads_total, ln.leads_total), 0))           AS cpl,
  SAFE_DIVIDE(a.spend, NULLIF(COALESCE(li.leads_qualified, ln.leads_qualified), 0))   AS cpql,
  SAFE_DIVIDE(
    COALESCE(li.leads_qualified, ln.leads_qualified, 0),
    NULLIF(COALESCE(li.leads_total, ln.leads_total), 0)
  )                                                                                    AS qual_rate,
  SAFE_DIVIDE(
    COALESCE(di.new_biz_revenue_won, dn.new_biz_revenue_won, 0),
    NULLIF(a.spend, 0)
  )                                                                                    AS new_biz_roas,
  SAFE_DIVIDE(
    COALESCE(di.all_revenue_won, dn.all_revenue_won, 0),
    NULLIF(a.spend, 0)
  )                                                                                    AS roas

FROM `{P}.{D}.ads_daily` a

-- Fix A: lookup tables to back-fill NULL campaign_name (Snapchat, TikTok) and adset_name
LEFT JOIN (
  SELECT channel, campaign_id, ANY_VALUE(campaign_name) AS campaign_name
  FROM `{P}.{D}.campaigns_daily`
  WHERE campaign_name IS NOT NULL
  GROUP BY channel, campaign_id
) camp_lookup ON a.channel = camp_lookup.channel AND a.campaign_id = camp_lookup.campaign_id

LEFT JOIN (
  SELECT channel, adset_id, ANY_VALUE(adset_name) AS adset_name
  FROM `{P}.{D}.ads_daily`
  WHERE adset_name IS NOT NULL AND adset_id IS NOT NULL
  GROUP BY channel, adset_id
) adset_lookup ON a.channel = adset_lookup.channel AND a.adset_id = adset_lookup.adset_id

-- Leads: id-first (Instantform — sync ID survives ad renames)
LEFT JOIN leads_by_id li
  ON a.date = li.date AND a.ad_id = li.ad_id

-- Leads: name fallback (website forms — only when id-match found nothing)
LEFT JOIN leads_by_name ln
  ON li.ad_id IS NULL
 AND a.date = ln.date
 AND LOWER(TRIM(a.utm_content)) = ln.utm_key

-- Deals: id-first
LEFT JOIN deals_by_id di
  ON a.date = di.date AND a.ad_id = di.ad_id

-- Deals: name fallback
LEFT JOIN deals_by_name dn
  ON di.ad_id IS NULL
 AND a.date = dn.date
 AND LOWER(TRIM(a.utm_content)) = dn.utm_key

-- Fix C: exclude zero-spend ghost rows (eliminates 97% of Snapchat rows + 22% TikTok)
WHERE a.spend > 0
"""

WIDE_KEYWORDS_SQL = f"""
CREATE OR REPLACE TABLE `{P}.{D}.wide_keywords` AS
-- Keyword-grain reporting: spend (keywords_daily) + leads + deals from HubSpot.
-- Joined by (campaign_name, keyword_text) to avoid fan-out when the same
-- keyword text appears in multiple campaigns.
WITH

leads_by_term AS (
  SELECT
    hs_createdate                        AS date,
    LOWER(TRIM(lead_utm_campaign))       AS utm_campaign,
    LOWER(TRIM(lead_utm_term))           AS utm_term,
    COUNT(*)                             AS leads_total,
    COUNTIF(is_qualified)                AS leads_qualified,
    COUNTIF(is_disqualified)             AS leads_disqualified,
    COUNTIF(is_open)                     AS leads_open
  FROM `{P}.{D}.hubspot_leads_individual`
  WHERE lead_utm_term IS NOT NULL AND lead_utm_term != ''
  GROUP BY 1, 2, 3
),

deals_by_term AS (
  SELECT
    createdate                           AS date,
    LOWER(TRIM(deal_utm_campaign))       AS utm_campaign,
    LOWER(TRIM(deal_utm_term))           AS utm_term,
    COUNTIF(is_won AND is_new_biz)       AS new_biz_deals_won,
    COUNTIF(is_new_biz)                  AS new_biz_deals_total,
    SUM(CASE WHEN is_won AND is_new_biz THEN amount ELSE 0 END) AS new_biz_revenue_won,
    COUNTIF(is_won)                      AS all_deals_won,
    SUM(CASE WHEN is_won THEN amount ELSE 0 END) AS all_revenue_won
  FROM `{P}.{D}.hubspot_deals_individual`
  WHERE deal_utm_term IS NOT NULL AND deal_utm_term != ''
  GROUP BY 1, 2, 3
)

SELECT
  k.date,
  k.channel,
  CASE k.channel
    WHEN 'google_ads'    THEN 'Google Ads'
    WHEN 'microsoft_ads' THEN 'Microsoft Ads'
    ELSE INITCAP(REPLACE(k.channel, '_', ' '))
  END                                                               AS channel_name,
  k.account_id,
  k.campaign_id,
  k.campaign_name,
  k.adgroup_id,
  k.adgroup_name,
  k.keyword_id,
  k.keyword_text,
  k.match_type,
  k.status,
  k.quality_score,
  -- Spend metrics
  COALESCE(k.spend, 0)                                              AS spend,
  COALESCE(k.impressions, 0)                                        AS impressions,
  COALESCE(k.clicks, 0)                                             AS clicks,
  SAFE_DIVIDE(k.clicks, NULLIF(k.impressions, 0))                   AS ctr,
  k.avg_cpc,
  -- Leads (HubSpot) — joined by campaign + keyword text
  COALESCE(l.leads_total,        0)                                 AS leads_total,
  COALESCE(l.leads_qualified,    0)                                 AS leads_qualified,
  COALESCE(l.leads_disqualified, 0)                                 AS leads_disqualified,
  -- Deals
  COALESCE(d.new_biz_deals_won,   0)                               AS new_biz_deals_won,
  COALESCE(d.new_biz_deals_total, 0)                               AS new_biz_deals_total,
  COALESCE(d.new_biz_revenue_won, 0)                               AS new_biz_revenue_won,
  COALESCE(d.all_deals_won,       0)                               AS all_deals_won,
  COALESCE(d.all_revenue_won,     0)                               AS all_revenue_won,
  -- Derived KPIs
  SAFE_DIVIDE(k.spend, NULLIF(l.leads_total, 0))                    AS cpl,
  SAFE_DIVIDE(k.spend, NULLIF(l.leads_qualified, 0))                AS cpql,
  SAFE_DIVIDE(k.spend, NULLIF(d.new_biz_deals_won, 0))              AS cost_per_deal,
  SAFE_DIVIDE(d.new_biz_revenue_won, NULLIF(k.spend, 0))            AS new_biz_roas

FROM `{P}.{D}.keywords_daily` k

LEFT JOIN leads_by_term l
  ON k.date = l.date
 AND LOWER(TRIM(k.campaign_name)) = l.utm_campaign
 AND LOWER(TRIM(k.keyword_text))  = l.utm_term

LEFT JOIN deals_by_term d
  ON k.date = d.date
 AND LOWER(TRIM(k.campaign_name)) = d.utm_campaign
 AND LOWER(TRIM(k.keyword_text))  = d.utm_term
"""


def _heavy_views_list():
    """
    Returns (name, sql) pairs for views materialised as physical tables so Hex
    reads are instant. Listed in dependency order.

    NOTE: paid_channel_campaign_daily, paid_channel_daily, v_adset_performance,
    and v_ad_performance have been removed from this list — they will be dropped
    manually after testing. Only the new wide-table chain is rebuilt here.
    """
    return [
        ("wide_ads",      WIDE_ADS_SQL),
        ("wide_keywords", WIDE_KEYWORDS_SQL),
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
