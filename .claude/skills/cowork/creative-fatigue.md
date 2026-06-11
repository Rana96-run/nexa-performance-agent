---
name: creative-fatigue
description: Catches ads where CTR has dropped 20%+ from their peak in the last 30 days. Flags them before they tank ROAS. Creates Asana task for Creative Strategist to refresh before performance degrades.
agent: creative-strategist
connectors: [bigquery, asana]
---

# /creative-fatigue — Creative Fatigue Detector

You are the **Creative Strategist** catching fatigue early — before CTR decline turns into CPL regression and ROAS damage.

## What this skill does

1. Computes peak CTR for each ad in the last 30 days (7-day rolling window)
2. Compares current 7-day CTR to peak CTR
3. Flags ads where CTR dropped ≥ 20% from peak AND spend is still active
4. Creates Asana task for Creative Strategist to brief a refresh

## BQ query

```sql
WITH daily_ctr AS (
  SELECT
    channel,
    ad_name,
    ad_id,
    date,
    SUM(clicks)      AS clicks,
    SUM(impressions) AS impressions,
    SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0)) AS ctr_day
  FROM `{PROJECT}.{DATASET}.ads_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    AND impressions > 100
  GROUP BY channel, ad_name, ad_id, date
),
rolling_ctr AS (
  SELECT *,
    AVG(ctr_day) OVER (
      PARTITION BY channel, ad_name, ad_id
      ORDER BY date
      ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS ctr_7d_rolling
  FROM daily_ctr
),
peak_and_current AS (
  SELECT
    channel,
    ad_name,
    ad_id,
    MAX(ctr_7d_rolling)                                        AS peak_ctr,
    MAX(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
             THEN ctr_7d_rolling END)                          AS current_ctr,
    SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
             THEN clicks END)                                  AS clicks_7d,
    SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
             THEN impressions END)                             AS impr_7d
  FROM rolling_ctr
  GROUP BY channel, ad_name, ad_id
)
SELECT *,
  SAFE_DIVIDE(peak_ctr - current_ctr, NULLIF(peak_ctr, 0)) AS ctr_drop_pct
FROM peak_and_current
WHERE current_ctr IS NOT NULL
  AND peak_ctr > 0
  AND SAFE_DIVIDE(peak_ctr - current_ctr, NULLIF(peak_ctr, 0)) >= 0.20
  AND impr_7d > 500
ORDER BY channel, ctr_drop_pct DESC
```

## Output

```
CREATIVE FATIGUE REPORT — {date}
{N} ads showing CTR decline ≥ 20% from peak

{channel}:
• {ad_name}
  Peak CTR: {peak_ctr%} → Current CTR: {current_ctr%} (↓ {drop%})
  Impressions last 7d: {impr_7d} | Still spending: yes
  → Brief a refresh variant with same format, new hook
  
[repeat per ad]
```

## Asana task

```
CREATIVE FATIGUE — {N} ads — {date}

CTR decline ≥ 20% from peak detected on the following ads:

{for each ad: channel, ad name, peak CTR → current CTR, drop %}

RECOMMENDED ACTION FOR CREATIVE STRATEGIST:
For each fatigued ad:
1. Identify the hook type (static / video / carousel)
2. Brief a new variant: same format and CTA, new opening 3 seconds / headline
3. Scope 1–2 A/B variants per fatigued ad, aligned to OCEAN persona for that channel
4. Do NOT pause the original until the variant has 3+ days of data

Created: {date}
Due: {date + 3 days}
Priority: Medium
Type: Recommendation
Channel: all
Asset level: ad
Action: creative-refresh → [Creative Strategist]
```

## Hard rules

- CTR drop threshold: 20% from peak (not from average — peak is the benchmark).
- Minimum impressions: 500 in the last 7 days. Don't flag paused or low-traffic ads.
- Never auto-pause a fatigued ad. The variant must prove itself first.
- If 0 fatigued ads found, log "No creative fatigue detected" and stop — no Asana task.

## Done means

All active ads checked for CTR decline ≥ 20% from peak, Asana task created with refresh brief for Creative Strategist.
