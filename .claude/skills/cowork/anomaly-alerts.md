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

## Actionability gate (non-negotiable)

Every alert must answer the question: **"What do I do now?"** before it fires.
An alert is only valid if the reader can take a concrete action because of it.
If there is no concrete action, suppress it silently. Never post noise.

| Signal | Post to Slack? | Why |
|---|---|---|
| CAMPAIGN DARK (had spend 3–7d ago, silent 2d) | Yes | Actionable: investigate budget / bid / policy |
| CAMPAIGN DARK (paused the whole time) | Never | Not actionable — already paused |
| CAMPAIGN DARK (never had spend) | Never | Not actionable — never ran |
| Spend spike > 2× 7d average | Yes | Actionable: check budget, duplicate charges |
| Lead drop ≥ 50% overnight | Yes | Actionable: check collectors, LP, bidding |
| CPQL spike > 2× 7d average | Yes | Actionable: pause/optimize |
| Any metric with fewer than 3 days of baseline data | Never | Too little data to be meaningful |

## Anomaly volume guard (non-negotiable)

**If the total count of new anomalies exceeds 5 in a single run:**
- Do NOT list them all. Something is wrong with the detector itself — a scheduled budget pause, platform outage, or a collector failure is triggering everything at once.
- Post ONE message only:
  ```
  ⚠️ *Multiple anomalies detected — {YYYY-MM-DD}*
  {count} checks fired simultaneously. Likely cause: scheduled budget pause or platform outage. Check the dashboard — no individual action needed until the cause is clear.

  📊 Dashboard: <https://nexa-web-production-6a6b.up.railway.app/activity|activity dashboard>
  ```
- Create a single Asana task: `[Anomaly] Mass-fire — {date}` with the count and a note to investigate the cause before acting.
- Do NOT create one task per anomaly when the mass-fire guard triggers.

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
**Fires if:** yesterday spend > 2× 7-day average. Skip if fewer than 3 days of baseline data exist.

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
**Fires if:** yesterday leads < 50% of 7-day average. Skip if fewer than 3 days of baseline data exist.

### Check 3 — Campaign went dark

A campaign is DARK only if it had **confirmed spend 3–7 days ago** AND has been **silent for the last 2 days** (spend = 0 AND impressions = 0). Paused campaigns and campaigns that never ran are silently excluded — they are not actionable.

```sql
-- A campaign qualifies as DARK only if:
--   1. It had spend > 0 during days 3–7 ago (confirmed it was running, not just newly launched)
--   2. It has spend = 0 AND impressions = 0 for the entire last 2 days
-- Campaigns with no spend in days 3–7 → never ran or always paused → skip silently.
-- Campaigns with spend=0 but impressions>0 in the last 2d → still live (limited budget) → skip.
WITH prior_activity AS (
  SELECT campaign_name, channel
  FROM `{PROJECT}.{DATASET}.campaigns_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
                 AND DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
  GROUP BY campaign_name, channel
  HAVING SUM(spend) > 0
),
recent_silence AS (
  SELECT campaign_name, channel
  FROM `{PROJECT}.{DATASET}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)
  GROUP BY campaign_name, channel
  HAVING SUM(spend) = 0 AND SUM(impressions) = 0
)
SELECT pa.campaign_name, pa.channel,
  (SELECT MAX(date) FROM `{PROJECT}.{DATASET}.campaigns_daily` c2
   WHERE c2.campaign_name = pa.campaign_name AND c2.channel = pa.channel
     AND c2.spend > 0) AS last_spend_date
FROM prior_activity pa
INNER JOIN recent_silence rs
  ON pa.campaign_name = rs.campaign_name AND pa.channel = rs.channel
```
**Fires if:** campaign had spend > 0 in days 3–7 ago AND spend = 0 AND impressions = 0 for the last 2 days.
Paused campaigns (silent the entire window) → silently skipped. Campaigns that never ran → silently skipped.

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
**Fires if:** yesterday blended CPQL > 2× 7-day average. Skip if fewer than 3 days of baseline data exist.

## Step 1 — Anomaly volume check (BEFORE creating any tasks or posting Slack)

After all 4 checks run, count the total NEW anomalies (those without an existing open Asana task).

- If new anomaly count > 5 → trigger the **anomaly volume guard** (see top of file). Post one summary message, create one Asana task, stop.
- If new anomaly count ≤ 5 → proceed to Steps 2 and 3 below.

## Step 2 — BQ confirm before any Asana task (CAMPAIGN DARK only)

For every campaign flagged by Check 3, **re-query BQ** before creating or updating any Asana task:

```sql
SELECT SUM(spend) AS spend_today, SUM(impressions) AS impressions_today
FROM `{PROJECT}.{DATASET}.campaigns_daily`
WHERE campaign_name = '{campaign_name}'
  AND date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
```

- If `spend_today > 0` → campaign already recovered. Skip task creation. Log: `"[campaign_name] already recovered — skipping task"`.
- If `spend_today = 0 AND impressions_today = 0` → campaign is paused. Skip task creation. Log: `"[campaign_name] is paused (spend=0, impressions=0) — skipping task"`.
- If `spend_today = 0 AND impressions_today > 0` or no row → anomaly still present (active but not spending). Proceed to Step 3 (Asana task).

This BQ-confirm step does not apply to Checks 1, 2, or 4 — those are aggregate metrics confirmed by their own SQL above.

## Step 3 — Asana task (full details go here, not in Slack)

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
  Action: Investigate → [Growth Analyst]
  ```

## Step 4 — Slack alert (compact, only if something NEW changed)

Post to `SLACK_CHANNEL_HEALTH` **only if at least one anomaly is new** (not previously reported in an already-open Asana task from a prior run). If every firing anomaly already has an open task from yesterday, stay silent — the team already knows.

**Message format:**

```
🚨 *Anomaly detected — {YYYY-MM-DD}*
{summary line — e.g. "3 campaigns went dark (Check 3)" or "Spend spiked 2.4× (Check 1)"}

🔗 Asana: {task_url}
📊 Dashboard: <https://nexa-web-production-6a6b.up.railway.app/activity|activity dashboard>
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
- **Silent on paused campaigns.** Never alert on campaigns with spend=0 AND impressions=0 for the full window — these are paused, not dark.
- **Silent on campaigns that never ran.** No historical spend = never launched = not actionable.
- **Skip checks with fewer than 3 days of baseline data.** A single data point vs. 1-day average is not a meaningful signal.
- **Mass-fire guard:** if > 5 new anomalies fire at once, post one summary alert — not individual alerts. Mass-fires usually indicate a systemic event (platform outage, budget pause), not individual campaign problems.
- Runs at 07:00 Riyadh (04:00 UTC) — before the team starts, before the nightly digest.
- Posts to `SLACK_CHANNEL_HEALTH` only, never `SLACK_CHANNEL_APPROVAL`.
- Checks are independent — multiple can fire at once (subject to the mass-fire guard above).
- BQ confirm (Step 2) is mandatory for Check 3 before any task write — never create a task for a campaign that already recovered.

## Done means

All 4 checks run against yesterday's data. Dedup map built from open Asana tasks (Step 0). Anomaly volume checked — mass-fire guard applied if > 5 new anomalies (Step 1). Campaign Dark anomalies BQ-confirmed still present (Step 2). Asana tasks created or updated (Step 3). Compact Slack alert posted only for new anomalies (Step 4). BQ log entry written. Silent if all clear or all anomalies already tracked.
