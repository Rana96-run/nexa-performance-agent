-- TAB 3 / Chart 7 — Disqualification reasons (paid leads only)
-- Returns one row per (channel × campaign × reason × sub_reason) with counts.
-- Default sort by disqualified_count DESC.
--
-- Use as a Pivot Table or Drilldown Table in Hex:
--   Group by: channel → reason → sub_reason → campaign
--   OR filter by channel to see per-channel breakdown
--
-- Helps answer:
--   - Which channel/campaign produces the most "wrong audience" disqualifications? (targeting fix)
--   - Which campaign has the most "no response" disqualifications? (sales follow-up issue)
WITH paid_disq AS (
  SELECT
    m.paid_channel                                                          AS channel,
    COALESCE(NULLIF(TRIM(l.lead_utm_campaign), ''), '(no UTM)')             AS campaign,
    COALESCE(NULLIF(TRIM(l.lead_utm_audience), ''), '(no UTM)')             AS adset_or_audience,
    COALESCE(NULLIF(TRIM(l.top_disq_reason), ''),     'Unknown / not set') AS reason,
    COALESCE(NULLIF(TRIM(l.top_disq_sub_reason), ''), 'Unknown / not set') AS sub_reason,
    SUM(l.leads_disqualified)                                               AS disqualified_count
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily` l
  JOIN `angular-axle-492812-q4.qoyod_marketing.v_channel_key_map` m
    ON l.qoyod_source = m.qoyod_source
  WHERE l.date BETWEEN {{ start_date }} AND {{ end_date }}
    AND m.paid_channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
    AND l.leads_disqualified > 0
  GROUP BY 1, 2, 3, 4, 5
),
totals AS (
  SELECT SUM(disqualified_count) AS total_disqualified FROM paid_disq
)
SELECT
  p.channel,
  p.reason,
  p.sub_reason,
  p.campaign,
  p.adset_or_audience,
  p.disqualified_count,
  CAST(ROUND(SAFE_DIVIDE(p.disqualified_count, t.total_disqualified) * 100, 1) AS FLOAT64) AS share_of_total_pct
FROM paid_disq p
CROSS JOIN totals t
ORDER BY p.disqualified_count DESC NULLS LAST
