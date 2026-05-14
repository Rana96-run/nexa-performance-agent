-- ─────────────────────────────────────────────────────────────────────────────
-- HEX CELL — Keywords (hybrid drill-down, leaf level — Google + Microsoft only)
-- Variables consumed: channel, selected_campaign (optional), start_date, end_date
--
-- Behavior:
--   - No campaign selected → shows ALL keywords for this channel.
--   - Campaign clicked      → filters to that campaign's keywords.
-- Strict grain separation: only keyword-level columns. No campaign_name / adgroup_name.
--
-- Returns 0 rows for channels without keyword tracking (Meta, Snap, TikTok, LinkedIn).
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
  utm_term                                                                       AS keyword,
  match_type,
  ROUND(AVG(quality_score), 1)                                                  AS quality_score,
  ROUND(SUM(spend), 2)                                                          AS spend,
  SUM(impressions)                                                               AS impressions,
  SUM(clicks)                                                                    AS clicks,
  ROUND(SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) * 100, 2)         AS ctr_pct,
  SUM(leads)                                                                     AS leads,
  SUM(leads_qualified)                                                           AS sqls,
  SUM(leads_disqualified)                                                        AS disqualified,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified),     NULLIF(SUM(leads), 0)) * 100, 1)  AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(leads_disqualified),  NULLIF(SUM(leads), 0)) * 100, 1)  AS disq_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),           0)), 2)            AS cpl,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)), 2)            AS cpql
FROM `angular-axle-492812-q4.qoyod_marketing.v_keyword_performance`
WHERE channel = 'microsoft_ads'
  AND date BETWEEN {{ start_date }} AND {{ end_date }}
  {% if effective_campaign %}
  AND LOWER(TRIM(utm_campaign)) = LOWER(TRIM({{ effective_campaign }}))
  {% endif %}
GROUP BY utm_term, match_type
ORDER BY spend DESC NULLS LAST
