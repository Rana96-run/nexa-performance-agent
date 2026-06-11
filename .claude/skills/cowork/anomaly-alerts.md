---
name: anomaly-alerts
description: Detects sudden anomalies — spend doubling overnight, leads dropping 50%+, a campaign going dark, CPQL spiking 2× the 7-day average. Posts an immediate Slack alert. Runs daily in the morning loop before the nightly digest.
schedule: "0 4 * * *"
timezone: Asia/Riyadh
agent: growth-analyst
connectors: [bigquery, slack]
---

# /anomaly-alerts — Real-Time Anomaly Detection

You are the **Growth Analyst** running the morning anomaly sweep. You catch what went wrong overnight before the team starts the day.

## What this skill does

Runs 4 checks against yesterday vs the 7-day average. If any check fires, posts an immediate Slack alert to `SLACK_CHANNEL_HEALTH`. If nothing fires, stays silent.

## The 4 checks

### Check 1 — Spend spike (overnight doubling)
```sql
WITH daily AS (
  SELECT date, SUM(spend) AS total_spend
  FROM `{PROJECT}.{DATASET}.paid_channel_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY)
  GROUP BY date
),
avg_7d AS (
  SELECT AVG(total_spend) AS avg_spend
  FROM daily
  WHERE date < DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
)
SELECT d.date, d.total_spend, a.avg_spend,
  SAFE_DIVIDE(d.total_spend, a.avg_spend) AS ratio
FROM daily d, avg_7d a
WHERE d.date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  AND SAFE_DIVIDE(d.total_spend, a.avg_spend) > 2.0
```
**Fires if:** yesterday spend > 2× 7-day average.

### Check 2 — Lead drop (overnight crash)
```sql
WITH daily AS (
  SELECT date, SUM(leads_total) AS leads
  FROM `{PROJECT}.{DATASET}.paid_channel_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY)
  GROUP BY date
),
avg_7d AS (
  SELECT AVG(leads) AS avg_leads
  FROM daily
  WHERE date < DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
)
SELECT d.date, d.leads, a.avg_leads,
  SAFE_DIVIDE(a.avg_leads - d.leads, a.avg_leads) AS drop_pct
FROM daily d, avg_7d a
WHERE d.date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  AND SAFE_DIVIDE(a.avg_leads - d.leads, a.avg_leads) >= 0.50
```
**Fires if:** yesterday leads < 50% of 7-day average.

### Check 3 — Campaign went dark
```sql
SELECT campaign_name, channel, MAX(date) AS last_seen
FROM `{PROJECT}.{DATASET}.campaigns_daily`
WHERE spend > 0
GROUP BY campaign_name, channel
HAVING DATE_DIFF(CURRENT_DATE(), MAX(date), DAY) BETWEEN 1 AND 3
   AND MAX(date) < DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
```
**Fires if:** a campaign that was spending 2+ days ago has 0 spend for 1–3 days (silent death).

### Check 4 — CPQL spike
```sql
WITH daily AS (
  SELECT date,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql
  FROM `{PROJECT}.{DATASET}.paid_channel_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY)
  GROUP BY date
),
avg_7d AS (
  SELECT AVG(cpql) AS avg_cpql
  FROM daily
  WHERE date < DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
)
SELECT d.date, d.cpql, a.avg_cpql,
  SAFE_DIVIDE(d.cpql, a.avg_cpql) AS ratio
FROM daily d, avg_7d a
WHERE d.date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  AND SAFE_DIVIDE(d.cpql, a.avg_cpql) > 2.0
```
**Fires if:** yesterday blended CPQL > 2× 7-day average.

## Slack alert format (only when at least one check fires)

Post to `SLACK_CHANNEL_HEALTH`:

```
🚨 *Anomaly detected — {date}*

{for each fired check:}
• SPEND SPIKE: ${yesterday_spend} vs ${avg_7d} avg (×{ratio})
• LEAD CRASH: {yesterday_leads} leads vs {avg_7d_leads} avg (−{drop%}%)
• CAMPAIGN DARK: {campaign_name} ({channel}) — no spend for {N} days
• CPQL SPIKE: ${yesterday_cpql} vs ${avg_cpql} avg (×{ratio})

Check the dashboard: {DASHBOARD_URL}
```

## Hard rules

- **Silent if clean.** No "all clear" message — silence is the signal.
- Runs at 07:00 Riyadh (04:00 UTC) — before the team starts, before the nightly digest.
- Posts to `SLACK_CHANNEL_HEALTH` only, never `SLACK_CHANNEL_APPROVAL`.
- Does NOT create Asana tasks. Slack ping only — team investigates manually.
- Checks are independent — multiple can fire at once.

## Done means

All 4 checks run against yesterday's data. Slack alert posted if any fire. Silent if all clear. BQ log entry written.
