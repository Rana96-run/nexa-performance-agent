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

Runs 4 checks against yesterday vs the 7-day average. If any check fires, creates Asana tasks (with dedup) and posts a compact Slack alert to `SLACK_CHANNEL_HEALTH`. If nothing fires, stays silent.

## Step 0 — Daily Asana dedup guard (run FIRST, before anything else)

Before running any BQ check, query open Asana tasks in `ASANA_PROJECT_DAILY_ACTIVITY` and build a dedup map:

1. Fetch all open (incomplete) tasks from `ASANA_PROJECT_DAILY_ACTIVITY`.
2. Build a lookup: `existing_tasks = { task_name_normalized → task_gid }`.
3. Carry this map through every subsequent step. When a check fires and would create an Asana task:
   - If `campaign_name` (or anomaly label) matches an existing open task → **update** that task's due date and append a note — do NOT create a new one.
   - Only create a new task if no open task exists for that campaign/anomaly.

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

## Step 1 — BQ confirm before any Asana task (CAMPAIGN DARK only)

For every campaign flagged by Check 3, **re-query BQ** before creating or updating any Asana task:

```sql
SELECT SUM(spend) AS spend_today
FROM `{PROJECT}.{DATASET}.campaigns_daily`
WHERE campaign_name = '{campaign_name}'
  AND date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
```

- If `spend_today > 0` → campaign already recovered. Skip task creation. Log: `"[campaign_name] already recovered — skipping task"`.
- If `spend_today = 0` or no row → anomaly still present. Proceed to Step 2 (Asana task).

This BQ-confirm step does not apply to Checks 1, 2, or 4 — those are aggregate metrics confirmed by their own SQL above.

## Step 2 — Asana task (full details go here, not in Slack)

For each confirmed anomaly, create or update one Asana task in `ASANA_PROJECT_DAILY_ACTIVITY`:

- **Task name:** `[Anomaly] {Check label} — {campaign_name or date}` (e.g. `[Anomaly] Campaign Dark — Meta_LeadGen_AR_Invoice_Interests`)
- **Task description:** full detail — campaign name, channel, last-seen date, spend/lead/CPQL numbers, ratio vs 7-day avg, date range of the anomaly.
- **Due date:** today (Riyadh).
- **Dedup rule (from Step 0):** if an open task with a matching name already exists → update due date + append a note with today's confirmed numbers. Do NOT create a duplicate.
- **Task footer (required on every task):**
  ```
  Created: {YYYY-MM-DD}
  Due: {YYYY-MM-DD}
  Priority: High
  Type: Anomaly
  Channel: {channel}
  Check: {Check 1 / Check 2 / Check 3 / Check 4}
  Action: Investigate
  ```

## Step 3 — Slack alert (compact, only if something NEW changed)

Post to `SLACK_CHANNEL_HEALTH` **only if at least one anomaly is new** (not previously reported in an already-open Asana task from a prior run). If every firing anomaly already has an open task from yesterday, stay silent — the team already knows.

**Message format:**

```
🚨 *Anomaly detected — {YYYY-MM-DD}*
{summary line — e.g. "3 campaigns went dark (Check 3)" or "Spend spiked 2.4× (Check 1)"}

🔗 Asana: {task_url}
📊 Dashboard: {activity_dashboard_url}
```

Rules:
- No per-campaign bullet lists in the Slack message.
- No channel-by-channel breakdown in the Slack message.
- Full details are in the Asana task description only.
- One summary line per fired check (not per campaign). If multiple checks fire, stack the summary lines.
- If multiple campaigns fired Check 3, summarize as `"{N} campaigns went dark (Check 3)"`.

## Hard rules

- **Silent if clean.** No "all clear" message — silence is the signal.
- **Silent if no new anomalies.** If all firing anomalies already have open Asana tasks from a prior run, do not post to Slack.
- Runs at 07:00 Riyadh (04:00 UTC) — before the team starts, before the nightly digest.
- Posts to `SLACK_CHANNEL_HEALTH` only, never `SLACK_CHANNEL_APPROVAL`.
- Checks are independent — multiple can fire at once.
- BQ confirm (Step 1) is mandatory for Check 3 before any task write — never create a task for a campaign that already recovered.

## Done means

All 4 checks run against yesterday's data. Dedup map built from open Asana tasks (Step 0). Campaign Dark anomalies BQ-confirmed still present (Step 1). Asana tasks created or updated (Step 2). Compact Slack alert posted only for new anomalies (Step 3). BQ log entry written. Silent if all clear or all anomalies already tracked.
