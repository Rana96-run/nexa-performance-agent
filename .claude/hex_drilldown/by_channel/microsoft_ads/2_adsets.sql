-- ─────────────────────────────────────────────────────────────────────────────
-- HEX CELL — Ad Sets / Ad Groups drill-down (Microsoft Ads)
-- Variables: channel (slug), selected_campaign (optional), start_date, end_date
-- Row-click output: selected_adset (column: adset_name)
--
-- Source: wide_ads (ad-grain base table — GROUP BY adset_id rolls up to
-- adset grain). spend/impressions/clicks from ads_daily; leads from
-- hubspot_leads_individual; deals from hubspot_deals_individual.
-- All amounts are USD.
--
-- Why the subquery wrap: aggregating `spend` and aliasing it AS `spend` shadows
-- the underlying column. A HAVING/ORDER-BY clause then sees `spend` as the
-- alias (an aggregation) and wrapping it in SUM/comparison can trigger
-- "Aggregations of aggregations are not allowed". Wrapping in a subquery
-- makes `spend` a plain column in the outer query.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT * FROM (
  SELECT
    adset_id,
    MAX(adset_name)                                                                          AS adset_name,
    ROUND(SUM(spend), 2)                                                                  AS spend,
    SUM(impressions)                                                                      AS impressions,
    SUM(clicks)                                                                           AS clicks,
    ROUND(SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) * 100, 2)                 AS ctr_pct,
    -- Leads
    SUM(leads_total)                                                                      AS leads,
    SUM(leads_qualified)                                                                  AS sqls,
    SUM(leads_disqualified)                                                               AS disq_leads,
    ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total),           0)), 2)              AS cpl,
    ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)                    AS cpql,
    ROUND(SAFE_DIVIDE(SUM(leads_qualified),    NULLIF(SUM(leads_qualified) + SUM(leads_disqualified), 0)) * 100, 1) AS qual_rate_pct,
    ROUND(SAFE_DIVIDE(SUM(leads_disqualified), NULLIF(SUM(leads_qualified) + SUM(leads_disqualified), 0)) * 100, 1) AS disq_rate_pct,
    -- New business (Sales Pipeline + Bookkeeping + Qflavours) — full parallel set
    SUM(new_biz_deals_won)                                                                AS new_biz_deals_won,
    SUM(new_biz_deals_lost)                                                               AS new_biz_deals_lost,
    SUM(new_biz_deals_open)                                                               AS new_biz_deals_open,
    SUM(new_biz_deals_total)                                                              AS new_biz_deals_total,
    ROUND(SUM(new_biz_revenue_won),  2)                                                   AS new_biz_revenue_won,
    ROUND(SUM(new_biz_amount_lost),  2)                                                   AS new_biz_amount_lost,
    ROUND(SUM(new_biz_amount_open),  2)                                                   AS new_biz_amount_open,
    ROUND(SUM(new_biz_revenue_won) + SUM(new_biz_amount_lost) + SUM(new_biz_amount_open), 2) AS new_biz_amount_total,
    ROUND(SAFE_DIVIDE(SUM(new_biz_revenue_won), NULLIF(SUM(spend), 0)), 2)                AS new_biz_roas
  FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
  WHERE channel = 'microsoft_ads'
    AND date BETWEEN {{ start_date }} AND {{ end_date }}
    {% if effective_campaign %}
    AND LOWER(TRIM(campaign_name)) = LOWER(TRIM({{ effective_campaign }}))
    {% endif %}
  GROUP BY adset_id
) sub
WHERE spend > 0
ORDER BY spend DESC
