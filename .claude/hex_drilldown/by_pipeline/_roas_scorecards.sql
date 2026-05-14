-- ─────────────────────────────────────────────────────────────────────────────
-- TAB 2 — Two-ROAS scorecards with period-over-period comparison
-- Variables: start_date, end_date
--
-- Returns TWO rows:
--   Row 0 = current period
--   Row 1 = previous period (same length)
--
-- Wire 2 scorecard tiles:
--   - "New Business ROAS"  → column new_biz_roas    (Sales Pipeline + Bookkeeping + Qflavours)
--   - "All Paid ROAS"      → column all_paid_roas   (every pipeline)
-- Plus optional component tiles: new_biz_won, all_paid_won, total_spend
--
-- Why two ROAS:
--   New Biz ROAS  = how much "new acquisition + bookkeeping" revenue paid drove
--   All Paid ROAS = total revenue from paid-attributed customers, INCLUDING renewals
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
  SELECT p.period, p.sort_order, SUM(c.spend) AS total_spend
  FROM periods p
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.campaigns_daily` c
    ON c.date BETWEEN p.start_d AND p.end_d
   AND c.channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY p.period, p.sort_order
),
deals_agg AS (
  SELECT p.period, p.sort_order,
    -- New business (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_won,   0)) AS new_biz_deals_won,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_lost,  0)) AS new_biz_deals_lost,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_open,  0)) AS new_biz_deals_open,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_total, 0)) AS new_biz_deals_total,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_won,  0)) AS new_biz_won,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_lost, 0)) AS new_biz_amount_lost,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_open, 0)) AS new_biz_amount_open,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.amount_total,0)) AS new_biz_amount_total,
    -- All paid (every pipeline including renewals)
    SUM(d.amount_won)        AS all_paid_won,
    SUM(d.amount_total)      AS all_paid_amount_total,
    SUM(d.amount_lost)       AS all_paid_amount_lost,
    SUM(d.amount_open)       AS all_paid_amount_open,
    SUM(d.deals_won)         AS all_paid_deals_won,
    SUM(d.deals_lost)        AS all_paid_deals_lost,
    SUM(d.deals_open)        AS all_paid_deals_open,
    SUM(d.deals_total)       AS all_paid_deals_total
  FROM periods p
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily` d
    ON d.date BETWEEN p.start_d AND p.end_d
   AND d.qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY p.period, p.sort_order
)
SELECT
  s.period,
  ROUND(s.total_spend,         2) AS total_spend,
  -- New business (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
  d.new_biz_deals_won                       AS new_biz_deals_won,
  d.new_biz_deals_lost                      AS new_biz_deals_lost,
  d.new_biz_deals_open                      AS new_biz_deals_open,
  d.new_biz_deals_total                     AS new_biz_deals_total,
  ROUND(d.new_biz_won,          2)          AS new_biz_won,
  ROUND(d.new_biz_amount_lost,  2)          AS new_biz_amount_lost,
  ROUND(d.new_biz_amount_open,  2)          AS new_biz_amount_open,
  ROUND(d.new_biz_amount_total, 2)          AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(d.new_biz_won, NULLIF(s.total_spend, 0)), 2) AS new_biz_roas,
  -- All paid (every pipeline including renewals)
  ROUND(d.all_paid_won,          2) AS all_paid_won,
  ROUND(d.all_paid_amount_lost,  2) AS all_paid_amount_lost,
  ROUND(d.all_paid_amount_open,  2) AS all_paid_amount_open,
  ROUND(d.all_paid_amount_total, 2) AS all_paid_deal_amount,
  d.all_paid_deals_won              AS all_paid_deals_won,
  d.all_paid_deals_lost             AS all_paid_deals_lost,
  d.all_paid_deals_open             AS all_paid_deals_open,
  d.all_paid_deals_total            AS all_paid_deals_total,
  ROUND(SAFE_DIVIDE(d.all_paid_won, NULLIF(s.total_spend, 0)), 2) AS all_paid_roas
FROM spend_agg s
LEFT JOIN deals_agg d USING (period, sort_order)
ORDER BY s.sort_order
