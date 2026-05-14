-- TAB 3 / Chart 4 — Top 5 winners + Bottom 5 burners (per selected period)
-- Filtered to campaigns with min $200 spend (avoids tiny-sample noise).
-- 'rank' column = 'TOP' for highest 5 ROAS or 'BOTTOM' for lowest 5 ROAS.
-- Display as table grouped by rank, with conditional formatting on roas column.
WITH base AS (
  SELECT
    c.channel,
    c.campaign_name,
    SUM(c.spend) AS spend
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily` c
  WHERE c.date BETWEEN {{ start_date }} AND {{ end_date }}
    AND c.channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY c.channel, c.campaign_name
  HAVING SUM(c.spend) >= 200
),
deals AS (
  SELECT
    deal_utm_campaign  AS campaign_name,
    -- New business — full parallel set
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_won, 0))  AS new_biz_revenue_won,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_lost, 0)) AS new_biz_amount_lost,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_open, 0)) AS new_biz_amount_open,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           deals_won, 0))   AS new_biz_deals_won,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           deals_lost, 0))  AS new_biz_deals_lost,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           deals_open, 0))  AS new_biz_deals_open
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
    AND deal_utm_campaign IS NOT NULL
  GROUP BY deal_utm_campaign
),
joined AS (
  SELECT
    b.channel,
    b.campaign_name,
    ROUND(b.spend, 2)                              AS spend,
    -- New business — full parallel set
    COALESCE(d.new_biz_deals_won,  0)              AS new_biz_deals_won,
    COALESCE(d.new_biz_deals_lost, 0)              AS new_biz_deals_lost,
    COALESCE(d.new_biz_deals_open, 0)              AS new_biz_deals_open,
    ROUND(COALESCE(d.new_biz_revenue_won, 0), 2)   AS new_biz_revenue_won,
    ROUND(COALESCE(d.new_biz_amount_lost, 0), 2)   AS new_biz_amount_lost,
    ROUND(COALESCE(d.new_biz_amount_open, 0), 2)   AS new_biz_amount_open,
    ROUND(SAFE_DIVIDE(d.new_biz_revenue_won, NULLIF(b.spend, 0)), 2) AS new_biz_roas
  FROM base b
  LEFT JOIN deals d ON LOWER(TRIM(b.campaign_name)) = LOWER(TRIM(d.campaign_name))
),
ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (ORDER BY new_biz_roas DESC NULLS LAST) AS top_rank,
    ROW_NUMBER() OVER (ORDER BY new_biz_roas ASC NULLS LAST)  AS bottom_rank
  FROM joined
)
SELECT
  CASE WHEN top_rank <= 5 THEN 'TOP' ELSE 'BOTTOM' END AS rank,
  campaign_name,
  channel,
  spend,
  new_biz_deals_won,
  new_biz_deals_lost,
  new_biz_deals_open,
  new_biz_revenue_won,
  new_biz_amount_lost,
  new_biz_amount_open,
  new_biz_roas
FROM ranked
WHERE top_rank <= 5 OR bottom_rank <= 5
ORDER BY rank DESC, new_biz_roas DESC
