-- ─────────────────────────────────────────────────────────────────────────────
-- TAB 2 — Pipelines overview table (paid only)
-- One row per HubSpot pipeline. Won/lost/open/total counts + revenue + ROAS.
-- Variables: start_date, end_date
-- ROAS = pipeline_won_amount / total_paid_spend (USD/USD).
-- All revenue numbers attributed to deal createdate (after rebuild).
-- ─────────────────────────────────────────────────────────────────────────────
WITH spend AS (
  SELECT SUM(spend) AS total_spend
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
),
deals AS (
  -- Per-pipeline aggregate (each row is ONE pipeline). All-pipeline rollup
  -- doesn't apply here — these ARE the pipeline's own metrics.
  SELECT
    pipeline,
    SUM(deals_total)  AS total_deals,
    SUM(deals_won)    AS won_deals,
    SUM(deals_lost)   AS lost_deals,
    SUM(deals_open)   AS open_deals,
    SUM(amount_total) AS deal_amount,
    SUM(amount_won)   AS revenue_won,
    SUM(amount_lost)  AS lost_amount,
    SUM(amount_open)  AS open_amount
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
    AND pipeline IS NOT NULL
  GROUP BY pipeline
)
SELECT
  d.pipeline,
  d.total_deals,
  d.won_deals,
  d.lost_deals,
  d.open_deals,
  ROUND(SAFE_DIVIDE(d.won_deals, NULLIF(d.total_deals, 0)) * 100, 1) AS win_rate_pct,
  ROUND(d.deal_amount, 2)                                           AS deal_amount,
  ROUND(d.revenue_won, 2)                                           AS revenue_won,
  ROUND(d.lost_amount, 2)                                           AS lost_amount,
  ROUND(d.open_amount, 2)                                           AS open_amount,
  ROUND(SAFE_DIVIDE(d.revenue_won, NULLIF(d.won_deals, 0)), 2)      AS avg_won_deal,
  ROUND(SAFE_DIVIDE(d.revenue_won, NULLIF(s.total_spend, 0)), 2)    AS roas_vs_total_spend
FROM deals d
CROSS JOIN spend s
ORDER BY d.revenue_won DESC NULLS LAST
