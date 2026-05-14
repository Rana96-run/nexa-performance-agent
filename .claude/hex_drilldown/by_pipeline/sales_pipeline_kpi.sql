-- KPI scorecard for: Sales Pipeline pipeline (current vs previous period)
-- Variables: start_date, end_date
-- Row 0 = current; Row 1 = previous (same length)
-- Wire each tile: Value Row 0, Comparison Row 1, Label "vs previous period".
WITH params AS (
  SELECT
    DATE({{ start_date }})                                                AS curr_start,
    DATE({{ end_date }})                                                  AS curr_end,
    DATE_DIFF(DATE({{ end_date }}), DATE({{ start_date }}), DAY) + 1  AS period_days
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
agg AS (
  -- This view is filtered to a SINGLE pipeline so deals_won here IS the
  -- pipeline-specific count, not an all-pipeline aggregate.
  SELECT
    p.period, p.sort_order,
    SUM(d.deals_total)  AS deals,
    SUM(d.deals_won)    AS deals_won,
    SUM(d.amount_total) AS amount_total_sar,
    SUM(d.amount_won)   AS amount_won_sar,
    SUM(d.amount_lost)  AS amount_lost_sar
  FROM periods p
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily` d
    ON d.date BETWEEN p.start_d AND p.end_d
   AND d.qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
   AND d.pipeline = 'Sales Pipeline'
  GROUP BY p.period, p.sort_order
)
SELECT
  period,
  deals,
  deals_won,
  ROUND(amount_total_sar, 2)                                  AS deal_amount,
  ROUND(amount_won_sar, 2)                                    AS won_amount,
  ROUND(amount_lost_sar, 2)                                   AS lost_amount,
  ROUND(SAFE_DIVIDE(deals_won, NULLIF(deals, 0)) * 100, 1)    AS win_rate_pct,
  ROUND(SAFE_DIVIDE(amount_won_sar, NULLIF(deals_won, 0)), 2) AS avg_won_deal
FROM agg
ORDER BY sort_order
