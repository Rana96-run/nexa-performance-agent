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
         WHEN 'google_ads' THEN 'Google Ads'
         WHEN 'meta'       THEN 'Meta Ads'
         WHEN 'snapchat'   THEN 'Snapchat'
         WHEN 'tiktok'     THEN 'TikTok'
         WHEN 'microsoft'  THEN 'Microsoft Ads'
       END AS qoyod_source
FROM UNNEST(['google_ads','meta','snapchat','tiktok','microsoft']) AS channel
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
         SUM(d.deals_total)   AS deals_total,
         SUM(d.deals_won)     AS deals_won,
         SUM(d.deals_lost)    AS deals_lost,
         SUM(d.deals_open)    AS deals_open,
         SUM(d.amount_won)    AS revenue_won,
         SUM(d.amount_open)   AS pipeline_open
  FROM `{P}.{D}.hubspot_deals_daily` d
  JOIN `{P}.{D}.v_channel_key_map` m ON d.qoyod_source = m.qoyod_source
  GROUP BY 1,2
)
SELECT
  s.date,
  s.channel,
  s.spend,
  s.impressions,
  s.clicks,
  SAFE_DIVIDE(s.clicks, s.impressions) * 100 AS ctr,
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
  COALESCE(d.revenue_won, 0)     AS revenue_won,
  COALESCE(d.pipeline_open, 0)   AS pipeline_open,
  SAFE_DIVIDE(s.spend, l.hs_leads)     AS cpl,
  SAFE_DIVIDE(s.spend, l.hs_qualified) AS cpql,
  SAFE_DIVIDE(l.hs_qualified, l.hs_leads) * 100 AS qual_rate_pct,
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
FROM spend s
LEFT JOIN leads l ON s.date = l.date AND s.channel = l.channel
LEFT JOIN deals d ON s.date = d.date AND s.channel = d.channel
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
  SUM(revenue_won)    AS revenue_won,
  SUM(pipeline_open)  AS pipeline_open,
  SAFE_DIVIDE(SUM(spend), SUM(hs_leads))       AS cpl,
  SAFE_DIVIDE(SUM(spend), SUM(hs_qualified))   AS cpql,
  SAFE_DIVIDE(SUM(hs_qualified), SUM(hs_leads)) * 100 AS qual_rate_pct,
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


ALL_VIEWS = [
    ("v_channel_key_map",          CHANNEL_MAP_SQL),
    ("campaign_performance_daily", CAMPAIGN_PERFORMANCE_DAILY_SQL),
    ("campaign_performance_monthly", CAMPAIGN_PERFORMANCE_MONTHLY_SQL),
    ("channel_roas_daily",         CHANNEL_ROAS_DAILY_SQL),
    ("channel_roas_monthly",       CHANNEL_ROAS_MONTHLY_SQL),
    ("disqualification_matrix",    DISQUAL_MATRIX_SQL),
    ("pipeline_funnel",            PIPELINE_FUNNEL_SQL),
]


def refresh_all_views():
    client = get_client()
    for name, sql in ALL_VIEWS:
        try:
            client.query(sql).result()
            print(f"[views] OK: {name}")
        except Exception as e:
            print(f"[views] FAIL: {name}: {e}")
            raise
    print(f"[views] Refreshed {len(ALL_VIEWS)} views.")


if __name__ == "__main__":
    refresh_all_views()
