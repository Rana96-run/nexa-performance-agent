-- ─────────────────────────────────────────────────────────────────────────────
-- HEX SCORECARD — top-level KPI tiles with period-over-period comparison
-- Variables consumed: start_date, end_date
--
-- Returns TWO rows:
--   Row 0 = current period  (start_date → end_date)
--   Row 1 = previous period (same length, immediately before start_date)
--
-- In each Hex scorecard tile:
--   Value      → Row 0   (current)
--   Comparison → Row 1   (previous)
--   Label      → "vs previous period"
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
  SELECT 'current'  AS period, curr_start AS start_d, curr_end AS end_d, 1 AS sort_order FROM params
  UNION ALL
  SELECT 'previous' AS period,
         DATE_SUB(curr_start, INTERVAL period_days DAY) AS start_d,
         DATE_SUB(curr_start, INTERVAL 1 DAY)           AS end_d,
         2 AS sort_order
  FROM params
),
spend_agg AS (
  SELECT p.period, p.sort_order, SUM(c.spend) AS spend
  FROM periods p
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.campaigns_daily` c
    ON c.date BETWEEN p.start_d AND p.end_d
   AND c.channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY p.period, p.sort_order
),
leads_agg AS (
  SELECT p.period, p.sort_order,
    SUM(l.leads_total)        AS leads,
    SUM(l.leads_qualified)    AS qualified,
    SUM(l.leads_disqualified) AS disqualified
  FROM periods p
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily` l
    ON l.date BETWEEN p.start_d AND p.end_d
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.v_channel_key_map` m
    ON l.qoyod_source = m.qoyod_source
   AND m.paid_channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  WHERE m.paid_channel IS NOT NULL
  GROUP BY p.period, p.sort_order
),
deals_agg AS (
  SELECT p.period, p.sort_order,
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
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily` d
    ON d.date BETWEEN p.start_d AND p.end_d
   AND d.qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY p.period, p.sort_order
)
SELECT
  s.period,
  ROUND(s.spend, 2)                                                                AS total_spend,
  -- Leads
  COALESCE(l.leads, 0)                                                             AS total_leads,
  COALESCE(l.qualified, 0)                                                         AS sqls,
  COALESCE(l.disqualified, 0)                                                      AS disqualified_leads,
  ROUND(SAFE_DIVIDE(s.spend, NULLIF(l.leads,     0)), 2)                           AS cpl,
  ROUND(SAFE_DIVIDE(s.spend, NULLIF(l.qualified, 0)), 2)                           AS cpql,
  ROUND(SAFE_DIVIDE(l.qualified,    NULLIF(l.leads, 0)) * 100, 1)                  AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(l.disqualified, NULLIF(l.leads, 0)) * 100, 1)                  AS disq_rate_pct,
  -- Deal counts
  -- New business only (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
  COALESCE(d.new_biz_deals_won,   0)                                               AS new_biz_deals_won,
  COALESCE(d.new_biz_deals_lost,  0)                                               AS new_biz_deals_lost,
  COALESCE(d.new_biz_deals_open,  0)                                               AS new_biz_deals_open,
  COALESCE(d.new_biz_deals_total, 0)                                               AS new_biz_deals_total,
  ROUND(COALESCE(d.new_biz_revenue_won,  0), 2)                                    AS new_biz_revenue_won,
  ROUND(COALESCE(d.new_biz_amount_lost,  0), 2)                                    AS new_biz_amount_lost,
  ROUND(COALESCE(d.new_biz_amount_open,  0), 2)                                    AS new_biz_amount_open,
  ROUND(COALESCE(d.new_biz_amount_total, 0), 2)                                    AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(d.new_biz_revenue_won, NULLIF(s.spend, 0)), 2)                 AS new_biz_roas
FROM spend_agg s
LEFT JOIN leads_agg l USING (period, sort_order)
LEFT JOIN deals_agg d USING (period, sort_order)
ORDER BY s.sort_order
