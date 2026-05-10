"""
Unified reporting views for Looker Studio.

Two master views power the dashboards:
  - channel_roas_daily   (per date x channel: spend, leads, CPL, CPQL, deals, ROAS)
  - channel_roas_monthly (same metrics rolled up to month)

Plus drill-down views per mapping doc.
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
WITH spend AS (
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
         SUM(d.amount_open)    AS pipeline_open,
         SUM(d.amount_total)   AS total_deal_amount
  FROM `{P}.{D}.hubspot_deals_daily` d
  JOIN `{P}.{D}.v_channel_key_map` m ON d.qoyod_source = m.qoyod_source
  GROUP BY 1,2
)
SELECT
  COALESCE(s.date, l.date, d.date)             AS date,
  COALESCE(s.channel, l.channel, d.channel)    AS channel,
  COALESCE(s.spend, 0)                         AS spend,
  s.impressions,
  s.clicks,
  SAFE_DIVIDE(s.clicks, s.impressions) * 100   AS ctr,
  s.platform_leads,
  s.platform_conversions,
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
  COALESCE(d.deals_total, 0)     AS deals_total,
  COALESCE(d.deals_won, 0)       AS deals_won,
  COALESCE(d.deals_lost, 0)      AS deals_lost,
  COALESCE(d.deals_open, 0)      AS deals_open,
  COALESCE(d.revenue_won, 0)       AS revenue_won,
  COALESCE(d.pipeline_open, 0)     AS pipeline_open,
  COALESCE(d.total_deal_amount, 0) AS amount_total,
  SAFE_DIVIDE(s.spend, l.hs_leads)     AS cpl,
  SAFE_DIVIDE(s.spend, l.hs_qualified) AS cpql,
  -- qual/disq rates: denominator = qualified+disqualified (excludes open leads)
  SAFE_DIVIDE(l.hs_qualified,   l.hs_qualified + l.hs_disqualified) * 100 AS qual_rate_pct,
  SAFE_DIVIDE(l.hs_disqualified, l.hs_qualified + l.hs_disqualified) * 100 AS disq_rate_pct,
  SAFE_DIVIDE(d.revenue_won, s.spend)   AS roas,
  SAFE_DIVIDE(d.deals_won, l.hs_leads) * 100 AS lead_to_deal_pct,
  CASE
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) IS NULL THEN 'no_data'
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) < 20 THEN 'scale'
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) <= 28 THEN 'acceptable'
    WHEN SAFE_DIVIDE(s.spend, l.hs_leads) <= 30 THEN 'warning'
    ELSE 'pause_zone'
  END AS cpl_zone,
  CASE
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) IS NULL THEN 'no_data'
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) < 40 THEN 'scale'
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) <= 65 THEN 'acceptable'
    WHEN SAFE_DIVIDE(s.spend, l.hs_qualified) <= 80 THEN 'warning'
    ELSE 'pause_zone'
  END AS cpql_zone
-- FULL OUTER JOIN so lead-only channels (e.g. Organic Search, no spend)
-- still appear in the dashboard with NULL CPL/CPQL/ROAS instead of being dropped.
FROM spend s
FULL OUTER JOIN leads l ON s.date = l.date AND s.channel = l.channel
LEFT JOIN deals d ON COALESCE(s.date, l.date) = d.date
                 AND COALESCE(s.channel, l.channel) = d.channel
"""


CHANNEL_ROAS_MONTHLY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.channel_roas_monthly` AS
SELECT
  DATE_TRUNC(date, MONTH) AS month,
  channel,
  SUM(spend)          AS spend,
  SUM(impressions)    AS impressions,
  SUM(clicks)         AS clicks,
  SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr,
  SUM(platform_leads) AS platform_leads,
  SUM(hs_leads)       AS hs_leads,
  SUM(hs_qualified)   AS hs_qualified,
  SUM(hs_disqualified) AS hs_disqualified,
  SUM(hs_open)        AS hs_open,
  SUM(deals_total)    AS deals_total,
  SUM(deals_won)      AS deals_won,
  SUM(deals_lost)     AS deals_lost,
  SUM(deals_open)     AS deals_open,
  SUM(revenue_won)      AS revenue_won,
  SUM(pipeline_open)    AS pipeline_open,
  SUM(amount_total)     AS amount_total,
  SAFE_DIVIDE(SUM(spend), SUM(hs_leads))       AS cpl,
  SAFE_DIVIDE(SUM(spend), SUM(hs_qualified))   AS cpql,
  -- qual/disq rates: denominator = qualified+disqualified (excludes open leads)
  SAFE_DIVIDE(SUM(hs_qualified),   SUM(hs_qualified) + SUM(hs_disqualified)) * 100 AS qual_rate_pct,
  SAFE_DIVIDE(SUM(hs_disqualified), SUM(hs_qualified) + SUM(hs_disqualified)) * 100 AS disq_rate_pct,
  SAFE_DIVIDE(SUM(revenue_won), SUM(spend))    AS roas,
  SAFE_DIVIDE(SUM(deals_won), SUM(hs_leads)) * 100 AS lead_to_deal_pct
FROM `{P}.{D}.channel_roas_daily`
GROUP BY 1,2
"""


CAMPAIGN_PERFORMANCE_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.campaign_performance_daily` AS
SELECT
  c.date,
  c.channel,
  c.account_id,
  c.campaign_id,
  c.campaign_name,
  c.status,
  c.objective,
  c.spend,
  c.impressions,
  c.clicks,
  c.ctr,
  c.leads       AS platform_leads,
  c.conversions AS platform_conversions,
  c.cpl         AS platform_cpl,
  -- Seasonal / format tags for filtering in Looker
  CASE
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'ramadan|eid|ramdan') THEN 'Ramadan/Eid'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'zatka|zakat|vat|tax') THEN 'ZATCA/Tax'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'sale|offer|discount') THEN 'Promo'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'brand|awareness') THEN 'Brand'
    ELSE 'Always-on'
  END AS seasonal_tag,
  CASE
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'pmax|performance ?max') THEN 'PMax'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'search') THEN 'Search'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'display') THEN 'Display'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'video|youtube') THEN 'Video'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'reel|story|stories') THEN 'Reels/Stories'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'feed') THEN 'Feed'
    ELSE 'Other'
  END AS format_tag,
  -- Creative type dimension (UGC / TGC / Video / Image)
  CASE
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'\bugc\b') THEN 'UGC'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'\btgc\b') THEN 'TGC'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'video|reel|youtube') THEN 'Video'
    WHEN REGEXP_CONTAINS(LOWER(c.campaign_name), r'image|static|photo|banner') THEN 'Image'
    ELSE 'Other'
  END AS creative_type
FROM `{P}.{D}.campaigns_daily` c
"""


CAMPAIGN_PERFORMANCE_MONTHLY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.campaign_performance_monthly` AS
SELECT
  DATE_TRUNC(date, MONTH) AS month,
  channel,
  account_id,
  campaign_id,
  ANY_VALUE(campaign_name) AS campaign_name,
  ANY_VALUE(status)        AS status,
  ANY_VALUE(objective)     AS objective,
  ANY_VALUE(seasonal_tag)    AS seasonal_tag,
  ANY_VALUE(format_tag)      AS format_tag,
  ANY_VALUE(creative_type)   AS creative_type,
  SUM(spend)               AS spend,
  SUM(impressions)         AS impressions,
  SUM(clicks)              AS clicks,
  SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100 AS ctr,
  SUM(platform_leads)      AS platform_leads,
  SAFE_DIVIDE(SUM(spend), SUM(platform_leads)) AS platform_cpl
FROM `{P}.{D}.campaign_performance_daily`
GROUP BY 1,2,3,4
"""


DISQUAL_MATRIX_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.disqualification_matrix` AS
-- Cross-tab of disqualification reasons matching the PDF matrix layout:
-- rows = main reason, columns drillable by pipeline / channel / month
SELECT
  DATE_TRUNC(date, MONTH)   AS month,
  date,
  qoyod_source,
  pipeline,
  top_disq_reason           AS disqual_reason,
  -- Map verbose reasons to cleaner labels for the report
  CASE top_disq_reason
    WHEN 'No lead response'             THEN 'No Lead Response'
    WHEN 'After 8+ sales attempts'      THEN 'After 8+ Attempts'
    WHEN 'Number failed'                THEN 'Number Failed'
    WHEN 'Not a Buyer'                  THEN 'Not a Buyer'
    WHEN 'No Registered business'       THEN 'No Registered Business'
    WHEN 'Browsing/Testing'             THEN 'Browsing / Testing'
    WHEN 'Training'                     THEN 'Training'
    WHEN 'Existing customer'            THEN 'Existing Customer'
    WHEN 'Urdu speaker'                 THEN 'Urdu Speaker'
    WHEN 'Student'                      THEN 'Student'
    WHEN 'Lead denies'                  THEN 'Lead Denies'
    WHEN 'Out of region'                THEN 'Out of Region'
    ELSE COALESCE(top_disq_reason, 'Other')
  END AS disqual_reason_label,
  SUM(leads_disqualified) AS disqualified_count
FROM `{P}.{D}.hubspot_leads_module_daily`
WHERE leads_disqualified > 0
GROUP BY 1,2,3,4,5,6
"""


PIPELINE_FUNNEL_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.pipeline_funnel` AS
-- Funnel by month x channel x pipeline.
-- Stages: Total -> Qualified -> Disqualified -> Open
-- Matches the PDF funnel chart + disqualification cross-tab
SELECT
  DATE_TRUNC(date, MONTH)  AS month,
  date,
  qoyod_source,
  pipeline,
  -- Friendly pipeline label for Looker display
  CASE
    WHEN LOWER(pipeline) LIKE '%book%'    THEN 'Bookkeeping Pipeline'
    WHEN LOWER(pipeline) LIKE '%lead%'    THEN 'Lead Pipeline'
    WHEN LOWER(pipeline) LIKE '%account%' THEN 'Lead Pipeline'
    ELSE COALESCE(pipeline, 'Lead Pipeline')
  END AS pipeline_label,
  stage,
  SUM(leads_total)        AS leads_total,
  SUM(leads_qualified)    AS leads_qualified,
  SUM(leads_disqualified) AS leads_disqualified,
  SUM(leads_open)         AS leads_open,
  -- Conversion rates
  ROUND(SAFE_DIVIDE(SUM(leads_qualified), SUM(leads_total)) * 100, 1) AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified), SUM(leads_total)) * 100, 1) AS disqual_rate_pct
FROM `{P}.{D}.hubspot_leads_module_daily`
GROUP BY 1,2,3,4,5,6
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
WITH
  -- Map our channel slug -> the qoyod_source label HubSpot writes
  channel_map AS (
    SELECT 'google_ads'    AS channel, 'Google Ads'    AS qoyod_source UNION ALL
    SELECT 'meta',                     'Meta Ads'                       UNION ALL
    SELECT 'snapchat',                 'Snapchat'                       UNION ALL
    SELECT 'tiktok',                   'Tiktok Ads'                     UNION ALL
    SELECT 'linkedin',                 'LinkedIn Ads'                   UNION ALL
    SELECT 'microsoft_ads',            'Microsoft Ads'
  ),
  spend AS (
    SELECT date, channel, campaign_name,
           SUM(spend)        AS spend,
           SUM(impressions)  AS impressions,
           SUM(clicks)       AS clicks
    FROM `{P}.{D}.campaigns_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY date, channel, campaign_name
  ),
  leads AS (
    SELECT date, qoyod_source, lead_utm_campaign AS campaign_name,
           SUM(leads_total)        AS leads,
           SUM(leads_qualified)    AS qualified,
           SUM(leads_disqualified) AS disqualified
    FROM `{P}.{D}.hubspot_leads_module_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY date, qoyod_source, lead_utm_campaign
  ),
  deals AS (
    SELECT date, qoyod_source, deal_utm_campaign AS campaign_name,
           SUM(deals_won)  AS deals_won,
           SUM(amount_won) AS amount_won
    FROM `{P}.{D}.hubspot_deals_daily`
    WHERE date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    GROUP BY date, qoyod_source, deal_utm_campaign
  )
SELECT
  s.date,
  s.channel,
  s.campaign_name,
  -- Spend metrics (from ad platform)
  ROUND(s.spend, 2)        AS spend,
  s.impressions,
  s.clicks,
  -- Lead metrics (from HubSpot)
  IFNULL(l.leads, 0)        AS leads,
  IFNULL(l.qualified, 0)    AS qualified,
  IFNULL(l.disqualified, 0) AS disqualified,
  IFNULL(l.leads, 0) - IFNULL(l.qualified, 0) - IFNULL(l.disqualified, 0) AS open_leads,
  -- Deal metrics (from HubSpot)
  IFNULL(d.deals_won, 0)              AS deals,
  ROUND(IFNULL(d.amount_won, 0), 2)   AS deal_amount,
  -- Computed KPIs (single source of truth — never recompute in Python)
  ROUND(SAFE_DIVIDE(s.spend, NULLIF(l.leads, 0)),     2) AS cpl,
  ROUND(SAFE_DIVIDE(s.spend, NULLIF(l.qualified, 0)), 2) AS cpql,
  ROUND(SAFE_DIVIDE(d.amount_won, NULLIF(s.spend, 0)), 2) AS roas,
  ROUND(SAFE_DIVIDE(s.clicks, NULLIF(s.impressions, 0)) * 100, 4) AS ctr_pct,
  ROUND(SAFE_DIVIDE(l.leads, NULLIF(s.clicks, 0)) * 100, 4)        AS cvr_pct,
  ROUND(SAFE_DIVIDE(l.qualified, NULLIF(l.leads, 0)) * 100, 2)     AS qual_rate_pct
FROM spend s
LEFT JOIN channel_map cm  ON cm.channel = s.channel
LEFT JOIN leads l         ON l.date = s.date
                         AND l.qoyod_source = cm.qoyod_source
                         AND LOWER(l.campaign_name) = LOWER(s.campaign_name)
LEFT JOIN deals d         ON d.date = s.date
                         AND d.qoyod_source = cm.qoyod_source
                         AND LOWER(d.campaign_name) = LOWER(s.campaign_name)
"""


# Channel-level rollup view — same data aggregated to (date, channel)
PAID_CHANNEL_DAILY_SQL = f"""
CREATE OR REPLACE VIEW `{P}.{D}.paid_channel_daily` AS
SELECT
  date,
  channel,
  ROUND(SUM(spend), 2)        AS spend,
  SUM(impressions)            AS impressions,
  SUM(clicks)                 AS clicks,
  SUM(leads)                  AS leads,
  SUM(qualified)              AS qualified,
  SUM(disqualified)           AS disqualified,
  SUM(open_leads)             AS open_leads,
  SUM(deals)                  AS deals,
  ROUND(SUM(deal_amount), 2)  AS deal_amount,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)),       2) AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)),   2) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(deal_amount), NULLIF(SUM(spend), 0)), 2) AS roas,
  ROUND(SAFE_DIVIDE(SUM(qualified), NULLIF(SUM(leads), 0)) * 100, 2) AS qual_rate_pct
FROM `{P}.{D}.paid_channel_campaign_daily`
GROUP BY date, channel
"""


ALL_VIEWS = [
    ("v_channel_key_map",          CHANNEL_MAP_SQL),
    ("campaign_performance_daily", CAMPAIGN_PERFORMANCE_DAILY_SQL),
    ("campaign_performance_monthly", CAMPAIGN_PERFORMANCE_MONTHLY_SQL),
    ("channel_roas_daily",         CHANNEL_ROAS_DAILY_SQL),
    ("channel_roas_monthly",       CHANNEL_ROAS_MONTHLY_SQL),
    ("disqualification_matrix",    DISQUAL_MATRIX_SQL),
    ("pipeline_funnel",            PIPELINE_FUNNEL_SQL),
    # Unified views — single source of truth for the dashboard
    ("paid_channel_campaign_daily", PAID_CHANNEL_CAMPAIGN_DAILY_SQL),
    ("paid_channel_daily",          PAID_CHANNEL_DAILY_SQL),
]

# Sub-campaign views (adset / ad / keyword grain).
# Defined in bq_writer.py alongside their table schemas.
# Imported here so refresh_all_views() keeps them in sync automatically.
#
# Order matters: utm_paid_attribution_daily MUST come before v_adset_performance,
# v_ad_performance, and v_keyword_performance because those views SELECT from it.
def _sub_campaign_views():
    from collectors.bq_writer import (
        UTM_PAID_ATTRIBUTION_VIEW_SQL,
        V_ADSET_PERFORMANCE_SQL,
        V_AD_PERFORMANCE_SQL,
        V_KEYWORD_PERFORMANCE_SQL,
        V_LP_PERFORMANCE_WEEKLY_SQL,
        V_LP_WEEKLY_SUMMARY_SQL,
    )
    UTM_ATTRIBUTION_DAILY_SQL = UTM_PAID_ATTRIBUTION_VIEW_SQL
    return [
        # Attribution base — must be created before the grain views below
        ("utm_paid_attribution_daily", UTM_ATTRIBUTION_DAILY_SQL),
        ("v_adset_performance",        V_ADSET_PERFORMANCE_SQL),
        ("v_ad_performance",           V_AD_PERFORMANCE_SQL),
        ("v_keyword_performance",      V_KEYWORD_PERFORMANCE_SQL),
        # LP A/B test views — v_lp_weekly_summary depends on v_lp_performance_weekly
        ("v_lp_performance_weekly",    V_LP_PERFORMANCE_WEEKLY_SQL),
        ("v_lp_weekly_summary",        V_LP_WEEKLY_SUMMARY_SQL),
    ]


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


if __name__ == "__main__":
    refresh_all_views()
