-- TAB 3 / Chart 1 — ROAS trend (weekly, last 90 days)
-- One row per ISO week. Two ROAS series + spend + revenue for chart layering.
-- Use as line chart: x = week_start, y = new_biz_roas + all_paid_roas.
WITH weeks AS (
  SELECT DATE_TRUNC(d, WEEK(MONDAY)) AS week_start
  FROM UNNEST(GENERATE_DATE_ARRAY(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY),
                                  CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)) AS d
  GROUP BY 1
),
spend AS (
  SELECT DATE_TRUNC(date, WEEK(MONDAY)) AS week_start, SUM(spend) AS spend
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
    AND channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY 1
),
deals AS (
  SELECT
    DATE_TRUNC(date, WEEK(MONDAY)) AS week_start,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_won, 0)) AS new_biz_won,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_lost, 0)) AS new_biz_lost,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_open, 0)) AS new_biz_open,
    SUM(amount_won)  AS all_paid_won,
    SUM(amount_lost) AS all_paid_lost,
    SUM(amount_open) AS all_paid_open
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 90 DAY)
    AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY 1
)
SELECT
  w.week_start,
  ROUND(COALESCE(s.spend, 0), 2)         AS spend,
  -- Won amounts
  ROUND(COALESCE(d.new_biz_won,  0), 2)  AS new_biz_won,
  ROUND(COALESCE(d.all_paid_won, 0), 2)  AS all_paid_won,
  -- Lost + open amounts (parallel set)
  ROUND(COALESCE(d.new_biz_lost,  0), 2) AS new_biz_lost,
  ROUND(COALESCE(d.all_paid_lost, 0), 2) AS all_paid_lost,
  ROUND(COALESCE(d.new_biz_open,  0), 2) AS new_biz_open,
  ROUND(COALESCE(d.all_paid_open, 0), 2) AS all_paid_open,
  -- ROAS
  ROUND(SAFE_DIVIDE(d.new_biz_won,  NULLIF(s.spend, 0)), 2) AS new_biz_roas,
  ROUND(SAFE_DIVIDE(d.all_paid_won, NULLIF(s.spend, 0)), 2) AS all_paid_roas
FROM weeks w
LEFT JOIN spend s USING (week_start)
LEFT JOIN deals d USING (week_start)
ORDER BY week_start
