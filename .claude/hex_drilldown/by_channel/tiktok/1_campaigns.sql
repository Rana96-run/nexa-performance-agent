-- ─────────────────────────────────────────────────────────────────────────────
-- HEX CELL — Campaigns drill-down (TikTok Ads)
-- Variables consumed: start_date, end_date, channel_filter (optional)
-- Row-click output:   selected_campaign  (column: campaign_name)
--
-- Source: paid_channel_campaign_daily (one table — spend, leads, AND all deal
-- metrics now live here after the createdate rebuild).
-- All revenue/won/lost/open amounts are USD and attributed to deal createdate.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
  campaign_id,
  MAX(campaign_name) AS campaign_name,
  ROUND(SUM(spend), 2)                                                                  AS spend,
  SUM(impressions)                                                                      AS impressions,
  SUM(clicks)                                                                           AS clicks,
  ROUND(SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) * 100, 2)                 AS ctr_pct,
  -- Leads
  SUM(leads)                                                                            AS leads,
  SUM(qualified)                                                                        AS sqls,
  SUM(disqualified)                                                                     AS disq_leads,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),     0)), 2)                          AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)), 2)                          AS cpql,
  ROUND(SAFE_DIVIDE(SUM(qualified),    NULLIF(SUM(qualified) + SUM(disqualified), 0)) * 100, 1)  AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(disqualified), NULLIF(SUM(qualified) + SUM(disqualified), 0)) * 100, 1)  AS disq_rate_pct,
  -- New business (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
  SUM(new_biz_deals_won)                                                                AS new_biz_deals_won,
  SUM(new_biz_deals_lost)                                                               AS new_biz_deals_lost,
  SUM(new_biz_deals_open)                                                               AS new_biz_deals_open,
  SUM(new_biz_deals_total)                                                              AS new_biz_deals_total,
  ROUND(SUM(new_biz_revenue_won),  2)                                                   AS new_biz_revenue_won,
  ROUND(SUM(new_biz_amount_lost),  2)                                                   AS new_biz_amount_lost,
  ROUND(SUM(new_biz_amount_open),  2)                                                   AS new_biz_amount_open,
  ROUND(SUM(new_biz_amount_total), 2)                                                   AS new_biz_amount_total,
  ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)                AS new_biz_roas
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_campaign_daily`
WHERE channel = 'tiktok'
  AND date BETWEEN {{ start_date }} AND {{ end_date }}
  {% if campaign_filter %}
  AND LOWER(TRIM(campaign_name)) = LOWER(TRIM({{ campaign_filter }}))
  {% endif %}
GROUP BY campaign_id
ORDER BY spend DESC
