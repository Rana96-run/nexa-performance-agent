-- ─────────────────────────────────────────────────────────────────────────────
-- HEX CELL — Campaign name list (filter/dropdown data source)
-- Variables: start_date, end_date, channel_filter (optional)
--
-- Previously queried paid_channel_campaign_daily (dropped 2026-06-16).
-- Now queries wide_ads directly — same data, no intermediate table needed.
--
-- Usage: paste into the Hex filter cell that lists campaign names.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT DISTINCT campaign_name
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND campaign_name IS NOT NULL
  {% if channel_filter %}
  AND channel = {{ channel_filter }}
  {% endif %}
ORDER BY campaign_name
