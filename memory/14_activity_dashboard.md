# Activity Dashboard — Design Reference & Build Spec

## Purpose
The "Nexa Agent Activity" Hex published app shows what the agent did and when.
URL: https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/Nexa-Agent-Activity-033ArC9Xytz3SK6tPXwk9D/latest
Railway redirect: /activity → ACTIVITY_DEST_URL env var → above URL
Hex notebook (draft): .../hex/Nexa-Agent-Activity-033ArC9Xytz3SK6tPXwk9D/draft/logic

## BQ source table
`angular-axle-492812-q4.qoyod_marketing.agent_activity_log`

Schema:
- activity_id  STRING
- ts           TIMESTAMP  (UTC, partitioned)
- session_id   STRING
- role         STRING     (bq_refresh | daily_digest | pause_watcher | ops_scheduler)
- action       STRING
- status       STRING     (success | failed | skipped | pending_approval | approved | rejected)
- channel      STRING
- campaign_name STRING
- details      STRING (JSON)
- rows_affected INT64
- duration_s   FLOAT64

Riyadh timezone: DATETIME(ts, 'Asia/Riyadh')

## Reference design (shared by Amar 2026-05-05)
Modelled on the "Qoyod Growth Agent — Activity" dashboard. Layout:

1. HEADER — app title + last updated timestamp
2. DATE FILTER — dropdown preset (Last 24h / Last 7 days / Last 30 days / Last 90 days / All time)
3. CONTRIBUTION HEATMAP — GitHub-style calendar: x=day, y=role, color=count
4. SUMMARY STAT CARDS — one card per role showing:
   - Total actions
   - ✅ success count
   - ❌ failed count
   - 🔔 pending_approval count
5. PER-ROLE ACTIVITY TABLES — one section per role (10 rows visible):
   - bq_refresh   → "Data Collection"
   - daily_digest → "Daily Report & Decisions"
   - pause_watcher → "Campaign Actions"
   - ops_scheduler → "Ops Scheduler"
   Each row: time_riyadh | action | status | channel | campaign_name | rows_affected | duration_s

## Hex notebook cell plan
All cells added from App Builder view (so they appear on canvas).
SQL cells named with descriptive variable names via Python cells.

### SQL cells (Notebook)
| Cell name        | Variable        | Purpose                              |
|------------------|-----------------|--------------------------------------|
| stats_by_role    | dataframe       | role × status counts (date-filtered) |
| heatmap_data     | dataframe_2     | day × role × count (90 days fixed)   |
| bq_refresh_feed  | dataframe_3     | last 100 rows for bq_refresh role    |
| digest_feed      | dataframe_4     | last 100 rows for daily_digest role  |
| watcher_feed     | dataframe_5     | last 100 rows for pause_watcher role |
| ops_feed         | dataframe_6     | last 100 rows for ops_scheduler role |

### SQL — stats_by_role (date-filtered, parameterised via interval)
```sql
SELECT
  role,
  COUNT(*) AS total,
  COUNTIF(status = 'success')            AS success_cnt,
  COUNTIF(status = 'failed')             AS failed_cnt,
  COUNTIF(status = 'pending_approval')   AS pending_cnt,
  COUNTIF(status IN ('approved','rejected')) AS actioned_cnt
FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY role
ORDER BY total DESC
```
(interval 24 HOUR / 168 HOUR / 720 HOUR / 2160 HOUR controls preset)

### SQL — heatmap_data
```sql
SELECT
  DATE(DATETIME(ts, 'Asia/Riyadh')) AS day,
  role,
  COUNT(*) AS cnt
FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
GROUP BY day, role
ORDER BY day, role
```

### SQL — per-role feeds (template, swap role value)
```sql
SELECT
  FORMAT_DATETIME('%d %b %H:%M', DATETIME(ts, 'Asia/Riyadh')) AS time_riyadh,
  action,
  status,
  COALESCE(channel, '—')        AS channel,
  COALESCE(campaign_name, '—')  AS campaign,
  rows_affected,
  ROUND(duration_s, 1)          AS duration_s
FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
WHERE role = 'bq_refresh'
  AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY ts DESC
LIMIT 100
```

## App Canvas layout (App Builder)
```
[Text]   Nexa Agent Activity
[Text]   Today's Summary (last 24h)   ← stats_by_role table
[Table]  Table 10 → dataframe (stats_by_role)
[Chart]  Heatmap → dataframe_2 (heatmap_data)  x=day, y=role, color=cnt
[Text]   Data Collection (bq_refresh)
[Table]  → dataframe_3 (bq_refresh_feed)
[Text]   Daily Report & Decisions (daily_digest)
[Table]  → dataframe_4 (digest_feed)
[Text]   Campaign Actions (pause_watcher)
[Table]  → dataframe_5 (watcher_feed)
[Text]   Ops Scheduler (ops_scheduler)
[Table]  → dataframe_6 (ops_feed)
```

## Build status
- 2026-05-05: Initial v1 built with only 2 cells (today_summary + 7-day feed). NOT matching reference.
- 2026-05-05: Rebuild planned to match reference (heatmap + stat cards + per-role tables).

## Notes
- "Never lose reference" rule: always save design references to this file immediately.
- Previous 48h of data: use INTERVAL 48 HOUR in WHERE clause for "last session" context.
- The accidentally-created "Value 12" (Single value cell) still exists in notebook but removed from canvas — delete it when rebuilding.
