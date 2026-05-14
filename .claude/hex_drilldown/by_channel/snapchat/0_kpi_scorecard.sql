-- ─────────────────────────────────────────────────────────────────────────────
-- HEX SCORECARD — per-channel KPI tiles (Snapchat Ads) with period comparison
-- Variables consumed: start_date, end_date  (channel hardcoded per-tab)
--
-- Returns TWO rows:
--   Row 0 = current period
--   Row 1 = previous period (same length, immediately before)
--
-- Wire each scorecard tile:
--   Value      → Row 0
--   Comparison → Row 1
--   Label      → "vs previous period"
--
-- Currency: all USD. spend converted at ad-platform collectors; deal/revenue
-- converted at hubspot_deals_bq.py via to_usd(). Use columns as-is.
-- Date semantics: every deal row is keyed by createdate (won deals were moved
-- from closedate to createdate so ROAS attribution aligns with spend period).
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
agg AS (
  SELECT
    p.period,
    p.sort_order,
    SUM(d.spend)                  AS spend,
    SUM(d.hs_leads)               AS leads,
    SUM(d.hs_qualified)           AS qualified,
    SUM(d.hs_disqualified)        AS disqualified,
    -- New business: Sales Pipeline + Bookkeeping + Qflavours — full parallel set
    SUM(d.new_biz_deals_won)      AS new_biz_deals_won,
    SUM(d.new_biz_deals_lost)     AS new_biz_deals_lost,
    SUM(d.new_biz_deals_open)     AS new_biz_deals_open,
    SUM(d.new_biz_deals_total)    AS new_biz_deals_total,
    SUM(d.new_biz_revenue_won)    AS new_biz_revenue_won,
    SUM(d.new_biz_amount_lost)    AS new_biz_amount_lost,
    SUM(d.new_biz_amount_open)    AS new_biz_amount_open,
    SUM(d.new_biz_amount_total)   AS new_biz_amount_total
  FROM periods p
  LEFT JOIN `angular-axle-492812-q4.qoyod_marketing.channel_roas_daily` d
    ON d.date BETWEEN p.start_d AND p.end_d
   AND d.channel = 'snapchat'
  GROUP BY p.period, p.sort_order
)
SELECT
  period,
  -- Spend & leads
  ROUND(COALESCE(spend, 0), 2)                                                            AS spend,
  COALESCE(leads, 0)                                                                      AS leads,
  COALESCE(qualified, 0)                                                                  AS sqls,
  COALESCE(disqualified, 0)                                                               AS disq_leads,
  -- Cost metrics (SAFE_DIVIDE guards against /0)
  ROUND(SAFE_DIVIDE(spend, NULLIF(leads,        0)), 2)                                   AS cpl,
  ROUND(SAFE_DIVIDE(spend, NULLIF(qualified,    0)), 2)                                   AS cpql,
  -- Lead quality ratios (denom = qualified+disqualified, excludes open)
  ROUND(SAFE_DIVIDE(qualified,    NULLIF(qualified + disqualified, 0)) * 100, 1)          AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(disqualified, NULLIF(qualified + disqualified, 0)) * 100, 1)          AS disq_rate_pct,
  -- New business metrics (Sales Pipeline + Bookkeeping + Qflavours only) — full parallel set
  COALESCE(new_biz_deals_won,   0)                                                        AS new_biz_deals_won,
  COALESCE(new_biz_deals_lost,  0)                                                        AS new_biz_deals_lost,
  COALESCE(new_biz_deals_open,  0)                                                        AS new_biz_deals_open,
  COALESCE(new_biz_deals_total, 0)                                                        AS new_biz_deals_total,
  ROUND(COALESCE(new_biz_revenue_won,  0), 2)                                             AS new_biz_revenue_won,
  ROUND(COALESCE(new_biz_amount_lost,  0), 2)                                             AS new_biz_amount_lost,
  ROUND(COALESCE(new_biz_amount_open,  0), 2)                                             AS new_biz_amount_open,
  ROUND(COALESCE(new_biz_amount_total, 0), 2)                                             AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(new_biz_revenue_won, NULLIF(spend, 0)), 2)                            AS new_biz_roas
FROM agg
ORDER BY sort_order
