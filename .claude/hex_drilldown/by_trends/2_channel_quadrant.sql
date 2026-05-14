-- TAB 3 / Chart 2 — Channel efficiency quadrant
-- Each channel as one point. Use scatter plot:
--   x_axis = spend_share_pct (% of total paid spend)
--   y_axis = revenue_share_pct (% of total paid revenue)
--   size   = leads
-- Channels above the diagonal = over-performing (low spend share, high revenue share).
-- Channels below the diagonal = burning (high spend share, low revenue share).
WITH spend_per_channel AS (
  SELECT channel, SUM(spend) AS spend
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY channel
),
deals_per_channel AS (
  SELECT
    CASE qoyod_source
      WHEN 'Google Ads'    THEN 'google_ads'
      WHEN 'Meta Ads'      THEN 'meta'
      WHEN 'Snapchat Ads'  THEN 'snapchat'
      WHEN 'Tiktok Ads'    THEN 'tiktok'
      WHEN 'Microsoft Ads' THEN 'microsoft_ads'
      WHEN 'LinkedIn Ads'  THEN 'linkedin'
    END AS channel,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           amount_won, 0)) AS new_biz_revenue_won
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY 1
),
leads_per_channel AS (
  SELECT m.paid_channel AS channel, SUM(l.leads_total) AS leads
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily` l
  JOIN `angular-axle-492812-q4.qoyod_marketing.v_channel_key_map` m
    ON l.qoyod_source = m.qoyod_source
  WHERE l.date BETWEEN {{ start_date }} AND {{ end_date }}
    AND m.paid_channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY 1
),
totals AS (
  SELECT (SELECT SUM(spend)               FROM spend_per_channel)  AS total_spend,
         (SELECT SUM(new_biz_revenue_won) FROM deals_per_channel)  AS total_revenue
)
SELECT
  s.channel,
  ROUND(s.spend, 2)                                                   AS spend,
  COALESCE(l.leads, 0)                                                AS leads,
  ROUND(SAFE_DIVIDE(s.spend,               t.total_spend)   * 100, 1) AS spend_share_pct,
  ROUND(SAFE_DIVIDE(d.new_biz_revenue_won, t.total_revenue) * 100, 1) AS revenue_share_pct,
  COALESCE(ROUND(d.new_biz_revenue_won, 2), 0)                        AS new_biz_revenue_won,
  ROUND(SAFE_DIVIDE(d.new_biz_revenue_won, NULLIF(s.spend, 0)), 2)    AS new_biz_roas
FROM spend_per_channel s
CROSS JOIN totals t
LEFT JOIN deals_per_channel d ON s.channel = d.channel
LEFT JOIN leads_per_channel l ON s.channel = l.channel
ORDER BY spend DESC
