-- Pipeline: Renewal — per-source breakdown
-- Currency: all USD (collector already converted via to_usd()).
SELECT
  qoyod_source                                                                    AS source,
  SUM(deals_total)                                                                AS deals,
  SUM(deals_won)                                                                  AS deals_won,
  SUM(deals_lost)                                                                 AS deals_lost,
  SUM(deals_open)                                                                 AS deals_open,
  ROUND(SUM(amount_total), 2)                                                     AS deal_amount,
  ROUND(SUM(amount_won), 2)                                                       AS won_amount,
  ROUND(SUM(amount_lost), 2)                                                      AS lost_amount,
  ROUND(SUM(amount_open), 2)                                                      AS open_amount,
  ROUND(SAFE_DIVIDE(SUM(deals_won),  NULLIF(SUM(deals_total), 0)) * 100, 1)       AS win_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(amount_won), NULLIF(SUM(deals_won), 0)), 2)               AS avg_won_deal
FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  AND pipeline = 'Renewal'
GROUP BY qoyod_source
ORDER BY deal_amount DESC NULLS LAST
