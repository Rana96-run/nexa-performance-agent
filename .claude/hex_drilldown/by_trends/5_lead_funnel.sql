-- TAB 3 / Chart 5 — Lead → Qualified → Won funnel by channel
-- Stage progression per channel. Reveals where leakage happens.
-- Use as horizontal stacked bar (one bar per channel) OR side-by-side columns.
-- 'qual_rate_pct' = qualified / (qualified + disqualified) * 100
-- 'lead_to_won_pct' = deals_won / leads * 100  (overall conversion)
WITH leads AS (
  SELECT m.paid_channel AS channel,
    SUM(l.leads_total)        AS leads,
    SUM(l.leads_qualified)    AS qualified,
    SUM(l.leads_disqualified) AS disqualified
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily` l
  JOIN `angular-axle-492812-q4.qoyod_marketing.v_channel_key_map` m
    ON l.qoyod_source = m.qoyod_source
  WHERE l.date BETWEEN {{ start_date }} AND {{ end_date }}
    AND m.paid_channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
  GROUP BY m.paid_channel
),
deals AS (
  SELECT
    CASE qoyod_source
      WHEN 'Google Ads'    THEN 'google_ads'
      WHEN 'Meta Ads'      THEN 'meta'
      WHEN 'Snapchat Ads'  THEN 'snapchat'
      WHEN 'Tiktok Ads'    THEN 'tiktok'
      WHEN 'Microsoft Ads' THEN 'microsoft_ads'
      WHEN 'LinkedIn Ads'  THEN 'linkedin'
    END AS channel,
    SUM(deals_won) AS deals_won,
    SUM(IF(pipeline IN ('Sales Pipeline','Bookkeeping','Qflavours'),
           deals_won, 0)) AS new_biz_deals_won
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_deals_daily`
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND qoyod_source IN ('Google Ads','Meta Ads','Snapchat Ads','Tiktok Ads','Microsoft Ads','LinkedIn Ads')
  GROUP BY 1
)
SELECT
  l.channel,
  l.leads,
  l.qualified,
  l.disqualified,
  ROUND(SAFE_DIVIDE(l.qualified, NULLIF(l.qualified + l.disqualified, 0)) * 100, 1) AS qual_rate_pct,
  -- All-pipeline conversion
  d.deals_won                                                                       AS deals_won,
  ROUND(SAFE_DIVIDE(d.deals_won,         NULLIF(l.qualified, 0)) * 100, 1)          AS won_per_qualified_pct,
  ROUND(SAFE_DIVIDE(d.deals_won,         NULLIF(l.leads, 0))     * 100, 1)          AS lead_to_won_pct,
  -- New business conversion
  d.new_biz_deals_won                                                               AS new_biz_deals_won,
  ROUND(SAFE_DIVIDE(d.new_biz_deals_won, NULLIF(l.qualified, 0)) * 100, 1)          AS new_biz_won_per_qualified_pct,
  ROUND(SAFE_DIVIDE(d.new_biz_deals_won, NULLIF(l.leads, 0))     * 100, 1)          AS new_biz_lead_to_won_pct
FROM leads l
LEFT JOIN deals d USING (channel)
ORDER BY l.leads DESC
