-- TAB 3 / Chart 6 — CAC (Customer Acquisition Cost) by channel + period comparison
-- CAC = paid spend / paid-attributed won deals
-- Different from CPL because it's per *paying customer*, not per lead.
-- Industry rule of thumb: CAC ≤ 1/3 of customer LTV.
--
-- Returns one row per channel × 2 periods (current vs previous, same length).
-- Use as horizontal bar chart with vs-previous-period comparison column.
WITH params AS (
  SELECT
    DATE({{ start_date }})                                                AS curr_start,
    DATE({{ end_date }})                                                  AS curr_end,
    DATE_DIFF(DATE({{ end_date }}), DATE({{ start_date }}), DAY) + 1      AS period_days
),
periods AS (
  SELECT 'current'  AS period, curr_start AS start_d, curr_end AS end_d FROM params
  UNION ALL
  SELECT 'previous' AS period,
         DATE_SUB(curr_start, INTERVAL period_days DAY) AS start_d,
         DATE_SUB(curr_start, INTERVAL 1 DAY)           AS end_d
  FROM params
),
spend AS (
  SELECT p.period, c.channel, SUM(c.spend) AS spend
  FROM periods p
  JOIN `angular-axle-492812-q4.qoyod_marketing.campaigns_daily` c
    ON c.date BETWEEN p.start_d AND p.end_d
  WHERE c.channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY p.period, c.channel
),
deals AS (
  SELECT p.period,
    CASE d.qoyod_source
      WHEN 'Google Ads'    THEN 'google_ads'
      WHEN 'Meta Ads'      THEN 'meta'
      WHEN 'Snapchat Ads'  THEN 'snapchat'
      WHEN 'Tiktok Ads'    THEN 'tiktok'
      WHEN 'Microsoft Ads' THEN 'microsoft_ads'
      WHEN 'LinkedIn Ads'  THEN 'linkedin'
    END AS channel,
    SUM(IF(d.pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           d.deals_won, 0)) AS new_biz_deals_won
  FROM periods p
  JOIN `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily` d
    ON d.date BETWEEN p.start_d AND p.end_d
  WHERE d.qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY 1, 2
),
agg AS (
  SELECT
    s.period, s.channel, s.spend,
    COALESCE(d.new_biz_deals_won, 0) AS new_biz_deals_won,
    SAFE_DIVIDE(s.spend, NULLIF(d.new_biz_deals_won, 0)) AS new_biz_cac
  FROM spend s
  LEFT JOIN deals d USING (period, channel)
),
pivot AS (
  SELECT channel,
    MAX(IF(period='current',  spend,             NULL)) AS spend,
    MAX(IF(period='previous', spend,             NULL)) AS spend_prev,
    MAX(IF(period='current',  new_biz_deals_won, NULL)) AS new_biz_deals_won,
    MAX(IF(period='current',  new_biz_cac,       NULL)) AS new_biz_cac,
    MAX(IF(period='previous', new_biz_cac,       NULL)) AS new_biz_cac_prev
  FROM agg GROUP BY channel
)
SELECT
  channel,
  CAST(ROUND(spend, 2)             AS FLOAT64) AS spend,
  new_biz_deals_won,
  CAST(ROUND(new_biz_cac, 2)       AS FLOAT64) AS new_biz_cac,
  CAST(ROUND(new_biz_cac_prev, 2)  AS FLOAT64) AS new_biz_cac_prev,
  CAST(ROUND(SAFE_DIVIDE(new_biz_cac - new_biz_cac_prev, NULLIF(new_biz_cac_prev, 0)) * 100, 1) AS FLOAT64) AS new_biz_cac_change_pct
FROM pivot
-- Hide channels without active spend in the period.
WHERE new_biz_deals_won > 0 AND COALESCE(spend, 0) > 0
ORDER BY new_biz_cac ASC NULLS LAST
