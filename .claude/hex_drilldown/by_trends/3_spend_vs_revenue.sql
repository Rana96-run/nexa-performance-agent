-- TAB 3 / Chart 3 — Spend vs Revenue daily (last 90 days)
-- One row per day. Use as dual-axis line chart:
--   left axis  = spend (or spend_7d_avg)
--   right axis = revenue_won (or revenue_7d_avg)
-- 7d rolling averages smooth out daily noise so the trend is clearer.
WITH days AS (
  SELECT d AS date
  FROM UNNEST(GENERATE_DATE_ARRAY(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY),
                                  CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)) AS d
),
spend AS (
  SELECT date, SUM(spend) AS daily_spend
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
    AND channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY date
),
deals AS (
  SELECT date,
    SUM(amount_won)  AS daily_revenue,
    SUM(amount_lost) AS daily_lost,
    SUM(amount_open) AS daily_open,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_won, 0))  AS daily_new_biz_revenue,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_lost, 0)) AS daily_new_biz_lost,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_open, 0)) AS daily_new_biz_open
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
    AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY date
)
SELECT
  d.date,
  ROUND(COALESCE(s.daily_spend, 0),            2) AS spend,
  -- All-pipeline amounts
  ROUND(COALESCE(de.daily_revenue, 0),         2) AS revenue_won,
  ROUND(COALESCE(de.daily_lost,    0),         2) AS amount_lost,
  ROUND(COALESCE(de.daily_open,    0),         2) AS amount_open,
  -- New business amounts
  ROUND(COALESCE(de.daily_new_biz_revenue, 0), 2) AS new_biz_revenue_won,
  ROUND(COALESCE(de.daily_new_biz_lost, 0), 2)    AS new_biz_amount_lost,
  ROUND(COALESCE(de.daily_new_biz_open, 0), 2)    AS new_biz_amount_open,
  -- 7-day rolling averages
  ROUND(AVG(COALESCE(s.daily_spend, 0))            OVER (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS spend_7d_avg,
  ROUND(AVG(COALESCE(de.daily_revenue, 0))         OVER (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg,
  ROUND(AVG(COALESCE(de.daily_new_biz_revenue, 0)) OVER (ORDER BY d.date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS new_biz_revenue_7d_avg
FROM days d
LEFT JOIN spend s  USING (date)
LEFT JOIN deals de USING (date)
ORDER BY d.date
