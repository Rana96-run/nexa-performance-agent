-- ─────────────────────────────────────────────────────────────────────────────
-- HEX CELL — Channel scorecard table with period-over-period change %
-- Variables consumed: start_date, end_date  (no channel filter — shows all)
--
-- One row per channel. For each metric a `*_change_pct` column shows the %
-- change vs the previous period of the same length (e.g. last 30d vs prior 30d).
-- Positive numbers can be good or bad depending on metric:
--   spend / leads / sqls / revenue_won / deal_amount / roas → up = better
--   cpl / cpql / disq_rate_pct                             → up = worse
--
-- Sources DIRECTLY (avoids channel_roas_daily view which drops Snap/LinkedIn deals):
--   Spend  ← campaigns_daily            (paid channels only)
--   Leads  ← hubspot_leads_module_daily (joined to v_channel_key_map → paid channels)
--   Deals  ← hubspot_deals_daily        (filtered by qoyod_source IN paid sources)
-- Currency: all USD (collectors already converted SAR→USD upstream; do NOT divide).
-- ─────────────────────────────────────────────────────────────────────────────
WITH params AS (
  SELECT
    DATE({{ start_date }})                                                AS curr_start,
    DATE({{ end_date }})                                                  AS curr_end,
    DATE_DIFF(DATE({{ end_date }}), DATE({{ start_date }}), DAY) + 1      AS period_days
),
periods AS (
  SELECT 'current'  AS period, curr_start AS start_d, curr_end AS end_d FROM params
  UNION ALL
  SELECT 'previous' AS period,
         DATE_SUB(curr_start, INTERVAL period_days DAY) AS start_d,
         DATE_SUB(curr_start, INTERVAL 1 DAY)           AS end_d
  FROM params
),
spend_raw AS (
  SELECT p.period, c.channel, SUM(c.spend) AS spend
  FROM periods p
  JOIN `angular-axle-492812-q4.qoyod_marketing.campaigns_daily` c
    ON c.date BETWEEN p.start_d AND p.end_d
  WHERE c.channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY p.period, c.channel
),
leads_raw AS (
  SELECT p.period, m.paid_channel AS channel,
    SUM(l.leads_total)        AS leads,
    SUM(l.leads_qualified)    AS qualified,
    SUM(l.leads_disqualified) AS disqualified
  FROM periods p
  JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily` l
    ON l.date BETWEEN p.start_d AND p.end_d
  JOIN `angular-axle-492812-q4.qoyod_marketing.v_channel_key_map` m
    ON l.qoyod_source = m.qoyod_source
  WHERE m.paid_channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY p.period, m.paid_channel
),
deals_raw AS (
  SELECT p.period,
    CASE d.qoyod_source
      WHEN 'Google Ads'    THEN 'google_ads'
      WHEN 'Meta Ads'      THEN 'meta'
      WHEN 'Snapchat Ads'  THEN 'snapchat'
      WHEN 'Tiktok Ads'    THEN 'tiktok'
      WHEN 'Microsoft Ads' THEN 'microsoft_ads'
      WHEN 'LinkedIn Ads'  THEN 'linkedin'
    END AS channel,
    -- All-pipeline deal metrics
    SUM(d.deals_won)    AS deals_won,
    SUM(d.deals_lost)   AS deals_lost,
    SUM(d.deals_open)   AS deals_open,
    SUM(d.deals_total)  AS deals_total,
    SUM(d.amount_won)   AS revenue_won,
    SUM(d.amount_lost)  AS amount_lost,
    SUM(d.amount_open)  AS amount_open,
    SUM(d.amount_total) AS amount_total,
    -- New business: Sales Pipeline + Bookkeeping + Qflavours — full parallel set
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_won,   0)) AS new_biz_deals_won,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_lost,  0)) AS new_biz_deals_lost,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_open,  0)) AS new_biz_deals_open,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_total, 0)) AS new_biz_deals_total,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_won,  0)) AS new_biz_revenue_won,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_lost, 0)) AS new_biz_amount_lost,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_open, 0)) AS new_biz_amount_open,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_total,0)) AS new_biz_amount_total
  FROM periods p
  JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily` d
    ON d.date BETWEEN p.start_d AND p.end_d
  WHERE d.qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY 1, 2
),
agg AS (
  SELECT
    s.period,
    s.channel,
    s.spend,
    COALESCE(l.leads, 0)        AS leads,
    COALESCE(l.qualified, 0)    AS sqls,
    COALESCE(l.disqualified, 0) AS disq_leads,
    COALESCE(d.deals_won,    0) AS deals_won,
    COALESCE(d.deals_lost,   0) AS deals_lost,
    COALESCE(d.deals_open,   0) AS deals_open,
    COALESCE(d.deals_total,  0) AS deals_total,
    COALESCE(d.revenue_won,  0) AS revenue_won,
    COALESCE(d.amount_lost,  0) AS amount_lost,
    COALESCE(d.amount_open,  0) AS amount_open,
    COALESCE(d.amount_total, 0) AS amount_total,
    COALESCE(d.new_biz_deals_won,   0) AS new_biz_deals_won,
    COALESCE(d.new_biz_deals_lost,  0) AS new_biz_deals_lost,
    COALESCE(d.new_biz_deals_open,  0) AS new_biz_deals_open,
    COALESCE(d.new_biz_deals_total, 0) AS new_biz_deals_total,
    COALESCE(d.new_biz_revenue_won, 0) AS new_biz_revenue_won,
    COALESCE(d.new_biz_amount_lost, 0) AS new_biz_amount_lost,
    COALESCE(d.new_biz_amount_open, 0) AS new_biz_amount_open,
    COALESCE(d.new_biz_amount_total,0) AS new_biz_amount_total,
    SAFE_DIVIDE(s.spend, NULLIF(l.leads,     0)) AS cpl,
    SAFE_DIVIDE(s.spend, NULLIF(l.qualified, 0)) AS cpql,
    SAFE_DIVIDE(l.qualified,    NULLIF(l.qualified + l.disqualified, 0)) * 100 AS qual_rate_pct,
    SAFE_DIVIDE(l.disqualified, NULLIF(l.qualified + l.disqualified, 0)) * 100 AS disq_rate_pct,
    SAFE_DIVIDE(d.revenue_won,         NULLIF(s.spend, 0)) AS roas,
    SAFE_DIVIDE(d.new_biz_revenue_won, NULLIF(s.spend, 0)) AS new_biz_roas
  FROM spend_raw s
  LEFT JOIN leads_raw l USING (period, channel)
  LEFT JOIN deals_raw d USING (period, channel)
),
pivot AS (
  SELECT
    channel,
    MAX(IF(period='current',  spend,        NULL)) AS spend,
    MAX(IF(period='previous', spend,        NULL)) AS spend_prev,
    MAX(IF(period='current',  leads,        NULL)) AS leads,
    MAX(IF(period='previous', leads,        NULL)) AS leads_prev,
    MAX(IF(period='current',  sqls,         NULL)) AS sqls,
    MAX(IF(period='previous', sqls,         NULL)) AS sqls_prev,
    MAX(IF(period='current',  disq_leads,   NULL)) AS disq_leads,
    MAX(IF(period='previous', disq_leads,   NULL)) AS disq_leads_prev,
    MAX(IF(period='current',  cpl,          NULL)) AS cpl,
    MAX(IF(period='previous', cpl,          NULL)) AS cpl_prev,
    MAX(IF(period='current',  cpql,         NULL)) AS cpql,
    MAX(IF(period='previous', cpql,         NULL)) AS cpql_prev,
    MAX(IF(period='current',  qual_rate_pct,NULL)) AS qual_rate_pct,
    MAX(IF(period='previous', qual_rate_pct,NULL)) AS qual_rate_pct_prev,
    MAX(IF(period='current',  disq_rate_pct,NULL)) AS disq_rate_pct,
    MAX(IF(period='previous', disq_rate_pct,NULL)) AS disq_rate_pct_prev,
    MAX(IF(period='current',  deals_won,    NULL)) AS deals_won,
    MAX(IF(period='current',  deals_lost,   NULL)) AS deals_lost,
    MAX(IF(period='current',  deals_open,   NULL)) AS deals_open,
    MAX(IF(period='current',  deals_total,  NULL)) AS deals_total,
    MAX(IF(period='current',  revenue_won,  NULL)) AS revenue_won,
    MAX(IF(period='previous', revenue_won,  NULL)) AS revenue_won_prev,
    MAX(IF(period='current',  amount_lost,  NULL)) AS amount_lost,
    MAX(IF(period='current',  amount_open,  NULL)) AS amount_open,
    MAX(IF(period='current',  amount_total, NULL)) AS amount_total,
    MAX(IF(period='previous', amount_total, NULL)) AS amount_total_prev,
    MAX(IF(period='current',  roas,         NULL)) AS roas,
    MAX(IF(period='previous', roas,         NULL)) AS roas_prev,
    MAX(IF(period='current',  new_biz_deals_won,    NULL)) AS new_biz_deals_won,
    MAX(IF(period='current',  new_biz_deals_lost,   NULL)) AS new_biz_deals_lost,
    MAX(IF(period='current',  new_biz_deals_open,   NULL)) AS new_biz_deals_open,
    MAX(IF(period='current',  new_biz_deals_total,  NULL)) AS new_biz_deals_total,
    MAX(IF(period='current',  new_biz_revenue_won,  NULL)) AS new_biz_revenue_won,
    MAX(IF(period='current',  new_biz_amount_lost,  NULL)) AS new_biz_amount_lost,
    MAX(IF(period='current',  new_biz_amount_open,  NULL)) AS new_biz_amount_open,
    MAX(IF(period='current',  new_biz_amount_total, NULL)) AS new_biz_amount_total,
    MAX(IF(period='current',  new_biz_roas, NULL)) AS new_biz_roas,
    MAX(IF(period='previous', new_biz_roas, NULL)) AS new_biz_roas_prev
  FROM agg
  GROUP BY channel
)
SELECT
  channel,
  ROUND(spend, 2)                                                                                  AS spend,
  ROUND(SAFE_DIVIDE(spend - spend_prev,                 NULLIF(spend_prev, 0)) * 100, 1)           AS spend_change_pct,
  leads,
  ROUND(SAFE_DIVIDE(leads - leads_prev,                 NULLIF(leads_prev, 0)) * 100, 1)           AS leads_change_pct,
  sqls,
  ROUND(SAFE_DIVIDE(sqls - sqls_prev,                   NULLIF(sqls_prev, 0)) * 100, 1)            AS sqls_change_pct,
  disq_leads,
  ROUND(qual_rate_pct, 1)                                                                          AS qual_rate_pct,
  ROUND(qual_rate_pct - qual_rate_pct_prev, 1)                                                     AS qual_rate_change_pp,
  ROUND(disq_rate_pct, 1)                                                                          AS disq_rate_pct,
  ROUND(disq_rate_pct - disq_rate_pct_prev, 1)                                                     AS disq_rate_change_pp,
  ROUND(cpl, 2)                                                                                    AS cpl,
  ROUND(SAFE_DIVIDE(cpl - cpl_prev,                     NULLIF(cpl_prev, 0)) * 100, 1)             AS cpl_change_pct,
  ROUND(cpql, 2)                                                                                   AS cpql,
  ROUND(SAFE_DIVIDE(cpql - cpql_prev,                   NULLIF(cpql_prev, 0)) * 100, 1)            AS cpql_change_pct,
  -- Deal counts (all pipelines)
  deals_won,
  deals_lost,
  deals_open,
  deals_total,
  -- Deal amounts (all pipelines)
  ROUND(amount_total, 2)                                                                           AS amount_total,
  ROUND(SAFE_DIVIDE(amount_total - amount_total_prev,   NULLIF(amount_total_prev, 0)) * 100, 1)    AS amount_total_change_pct,
  ROUND(revenue_won, 2)                                                                            AS revenue_won,
  ROUND(SAFE_DIVIDE(revenue_won  - revenue_won_prev,    NULLIF(revenue_won_prev,  0)) * 100, 1)    AS revenue_won_change_pct,
  ROUND(amount_lost, 2)                                                                            AS amount_lost,
  ROUND(amount_open, 2)                                                                            AS amount_open,
  -- New business
  new_biz_deals_won,
  new_biz_deals_lost,
  new_biz_deals_open,
  new_biz_deals_total,
  ROUND(new_biz_revenue_won,  2)                                                                   AS new_biz_revenue_won,
  ROUND(new_biz_amount_lost,  2)                                                                   AS new_biz_amount_lost,
  ROUND(new_biz_amount_open,  2)                                                                   AS new_biz_amount_open,
  ROUND(new_biz_amount_total, 2)                                                                   AS new_biz_amount_total,
  -- ROAS — two flavors side-by-side
  ROUND(roas, 2)                                                                                   AS roas,
  ROUND(SAFE_DIVIDE(roas - roas_prev,                   NULLIF(roas_prev, 0)) * 100, 1)            AS roas_change_pct,
  ROUND(new_biz_roas, 2)                                                                           AS new_biz_roas,
  ROUND(SAFE_DIVIDE(new_biz_roas - new_biz_roas_prev,   NULLIF(new_biz_roas_prev, 0)) * 100, 1)    AS new_biz_roas_change_pct
FROM pivot
-- Hide channels that are inactive in the selected period.
-- A channel with $0 spend in BOTH periods is paused on the platform side
-- (Microsoft / LinkedIn currently). Showing them with NULL CPL / ∞ ROAS
-- is misleading. They reappear automatically once spend resumes.
WHERE COALESCE(spend, 0) > 0 OR COALESCE(spend_prev, 0) > 0
ORDER BY spend DESC NULLS LAST
