-- ─────────────────────────────────────────────────────────────────────────────
-- HEX CELL — Ads drill-down, leaf level (Google Ads)
-- Variables: channel, selected_campaign (optional), selected_adset (optional),
--            start_date, end_date
-- Row output: utm_content
--
-- Source: v_ad_performance (materialized). spend from ads_daily; leads from
-- utm_paid_attribution_daily; deals from hubspot_deals_daily (createdate
-- attributed after rebuild). All amounts USD.
-- Note: ad_name = utm_content; many Google RSAs have NULL utm_content → blank
-- rows expected.
--
-- Subquery wrap: avoids "Aggregations of aggregations" error caused by alias
-- `spend` shadowing the source column when used in HAVING/ORDER BY.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT * FROM (
  SELECT
    utm_content                                                                           AS ad_name,
    ROUND(SUM(spend), 2)                                                                  AS spend,
    SUM(impressions)                                                                      AS impressions,
    SUM(clicks)                                                                           AS clicks,
    ROUND(SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) * 100, 2)                 AS ctr_pct,
    -- Leads
    SUM(leads)                                                                            AS leads,
    SUM(leads_qualified)                                                                  AS sqls,
    SUM(leads_disqualified)                                                               AS disq_leads,
    ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),           0)), 2)                    AS cpl,
    ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)                    AS cpql,
    ROUND(SAFE_DIVIDE(SUM(leads_qualified),    NULLIF(SUM(leads_qualified) + SUM(leads_disqualified), 0)) * 100, 1) AS qual_rate_pct,
    ROUND(SAFE_DIVIDE(SUM(leads_disqualified), NULLIF(SUM(leads_qualified) + SUM(leads_disqualified), 0)) * 100, 1) AS disq_rate_pct,
    -- Deal counts (all pipelines)
    SUM(deals_won)                                                                        AS deals_won,
    SUM(deals_lost)                                                                       AS deals_lost,
    SUM(deals_open)                                                                       AS deals_open,
    -- Deal amounts (all pipelines)
    ROUND(SUM(revenue_won + amount_lost + amount_open), 2)                                AS total_deal_amount,
    ROUND(SUM(revenue_won), 2)                                                            AS closed_won_amount,
    ROUND(SUM(amount_lost), 2)                                                            AS closed_lost_amount,
    ROUND(SUM(amount_open), 2)                                                            AS open_deal_amount,
    -- New business (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
    SUM(new_biz_deals_won)                                                                AS new_biz_deals_won,
    SUM(new_biz_deals_lost)                                                               AS new_biz_deals_lost,
    SUM(new_biz_deals_open)                                                               AS new_biz_deals_open,
    SUM(new_biz_deals_total)                                                              AS new_biz_deals_total,
    ROUND(SUM(new_biz_revenue_won),  2)                                                   AS new_biz_revenue_won,
    ROUND(SUM(new_biz_amount_lost),  2)                                                   AS new_biz_amount_lost,
    ROUND(SUM(new_biz_amount_open),  2)                                                   AS new_biz_amount_open,
    ROUND(SUM(new_biz_amount_total), 2)                                                   AS new_biz_amount_total,
    -- ROAS — two flavors side-by-side
    ROUND(SAFE_DIVIDE(SUM(revenue_won),         NULLIF(SUM(spend), 0)), 2)                AS roas,
    ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)                AS new_biz_roas,
    -- Creative type: NULL for Google Ads (no ad-level creative type in the API)
    MAX(creative_type)                                                                    AS creative_type,
    -- Status: ACTIVE | PAUSED (NULL for channels where not collected)
    MAX(status)                                                                           AS status,
    MAX(data_source)                                                                      AS spend_source
  FROM `angular-axle-492812-q4.qoyod_marketing.v_ad_performance`
  WHERE channel = 'google_ads'
    AND date BETWEEN {{ start_date }} AND {{ end_date }}
    {% if effective_campaign %}
    AND LOWER(TRIM(utm_campaign)) = LOWER(TRIM({{ effective_campaign }}))
    {% endif %}
    {% if selected_adset %}
    AND LOWER(TRIM(utm_audience)) = LOWER(TRIM({{ selected_adset }}))
    {% endif %}
  GROUP BY utm_content
) sub
WHERE spend > 0
ORDER BY spend DESC NULLS LAST
