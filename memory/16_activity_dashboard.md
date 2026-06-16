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
- role         STRING     — see "Role taxonomy" below
- action       STRING
- status       STRING     (success | failed | skipped | pending_approval | approved | rejected)
- channel      STRING
- campaign_name STRING
- details      STRING (JSON)
- rows_affected INT64
- duration_s   FLOAT64

Riyadh timezone: DATETIME(ts, 'Asia/Riyadh')

## ⚠️ Log-roles ≠ team agents (corrected 2026-06-08)
`agent_activity_log.role` is a **logging taxonomy**, not the team roster. The team
is **9 agents** (see `docs/_shared/org-chart.md` / `11_agent_roles.md`). A live
`SELECT DISTINCT role` on 2026-06-08 returned **13** values — this file previously
documented only 7, which caused a wrong agent rebuild. The full live set:

| role | rows (all-time, 2026-06-08) | kind |
|---|---|---|
| `health_monitor` | 10790 | infra (heartbeat) |
| `bq_refresh` | 2104 | infra (collector pass) |
| `task_creator` | 659 | function (Asana tasks) |
| `ops_scheduler` | 446 | infra (cron orchestration) |
| `performance_audit` | 256 | function (audits) |
| `llm_cadence` | 155 | function (LLM analysis) |
| `user` | 75 | human (approvals) |
| `spike_detector` | 37 | function (anomalies) |
| `keyword_management` | 34 | function (keywords) |
| `collector` | 15 | infra (manual/test runs) |
| `daily_digest` | 8 | function (digest post) |
| `paid_media_strategist` | 6 | function (LLM strategist) |
| `campaign_creator` | 3 | function (campaign create) |

Keep this table refreshed whenever a new `role` appears (the heatmap auto-adds rows).

## Role taxonomy (function-based; renamed 2026-05-06)

| Role                 | What it does                                                              |
|----------------------|---------------------------------------------------------------------------|
| `bq_refresh`         | Collects from APIs into BQ (all 22 collectors + view + Hex refresh + auto-heal) |
| `performance_audit`  | All channel performance audits (IS/QS/search-terms for Google + MS, CPL/CPQL/scale/pause for all paid channels via campaign_health). Channel column distinguishes which channel was audited |
| `keyword_management` | Keyword adds, pauses, deletes, negative direct-execute, weekly autofix    |
| `daily_digest`       | Posts the daily Slack approvals digest                                    |
| `ops_scheduler`      | Orchestration layer — fires the right cadence at the right time           |
| `spike_detector`     | Detects daily anomalies (yesterday vs 7d baseline)                        |
| `llm_cadence`        | LLM-based weekly/monthly/quarterly analysis (rarely used now)             |

**Renamed (legacy → new):**
- `pause_watcher` → `performance_audit`
- `google_ads_audit` → `performance_audit`
- `keyword_approval` → `keyword_management`
- `daily_agent` → `llm_cadence`

Historical rows in `agent_activity_log` were migrated 2026-05-06 — no `WHERE role IN (...)` clauses need to handle both names.

## Reference design (shared by Amar 2026-05-05)
Modelled on the "Qoyod Growth Agent — Activity" dashboard. Layout:

1. HEADER — app title + last updated timestamp
2. DATE FILTER — dropdown preset (Last 7 days [DEFAULT] / Last 24h / Last 30 days / Last 90 days / All time)
3. CONTRIBUTION HEATMAP — GitHub-style calendar: x=day, y=role (sorted by total activity desc), color=count
4. SUMMARY STAT CARDS — one card per role showing:
   - Total actions
   - ✅ success count
   - ❌ failed count
   - 🔔 pending_approval count
5. PER-ROLE ACTIVITY TABLES — one section per role (10 rows visible):
   - bq_refresh         → "Data Collection"
   - performance_audit  → "Performance Audit (all channels)"
   - keyword_management → "Keyword Management"
   - daily_digest       → "Daily Report & Decisions"
   - spike_detector     → "Anomaly Detection"
   - ops_scheduler      → "Ops Scheduler"
   - llm_cadence        → "LLM Analysis (weekly/monthly)"

   Each row: time_riyadh | action | status | channel | campaign_name | rows_affected | duration_s

## Hex notebook cell plan
All cells added from App Builder view (so they appear on canvas).
SQL cells named with descriptive variable names via Python cells.

### SQL cells (Notebook)
| Cell name              | Variable    | Purpose                                       |
|------------------------|-------------|-----------------------------------------------|
| stats_by_role          | dataframe   | role × status counts (date-filtered)          |
| heatmap_data           | dataframe_2 | day × role × count (90 days fixed, sorted)    |
| bq_refresh_feed        | dataframe_3 | last 100 rows for bq_refresh role             |
| performance_audit_feed | dataframe_4 | last 100 rows for performance_audit role      |
| keyword_mgmt_feed      | dataframe_5 | last 100 rows for keyword_management role     |
| digest_feed            | dataframe_6 | last 100 rows for daily_digest role           |
| spike_feed             | dataframe_7 | last 100 rows for spike_detector role         |
| ops_feed               | dataframe_8 | last 100 rows for ops_scheduler role          |
| llm_feed               | dataframe_9 | last 100 rows for llm_cadence role            |

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
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 168 HOUR)  -- DEFAULT 7 days
GROUP BY role
ORDER BY total DESC
```
(interval 24 HOUR / 168 HOUR / 720 HOUR / 2160 HOUR controls preset; DEFAULT = 168 = 7 days)

### SQL — heatmap_data (sorted by total activity descending)
```sql
WITH counts AS (
  SELECT
    DATE(DATETIME(ts, 'Asia/Riyadh')) AS day,
    role,
    COUNT(*) AS cnt
  FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  GROUP BY day, role
),
totals AS (
  SELECT role, SUM(cnt) AS total_cnt
  FROM counts
  GROUP BY role
)
SELECT c.day, c.role, c.cnt, t.total_cnt
FROM counts c
JOIN totals t USING (role)
ORDER BY t.total_cnt DESC, c.day
```
Hex chart Y-axis: order by `total_cnt DESC` so busiest roles appear on top.

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
WHERE role = 'bq_refresh'           -- swap per cell
  AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY ts DESC
LIMIT 100
```

## App Canvas layout (App Builder)
```
[Text]   Nexa Agent Activity
[Input]  Time Range — DEFAULT 168 (Last 7 days)
[Text]   Today's Summary
[Table]  stats_by_role          → dataframe
[Chart]  Heatmap                → dataframe_2 (heatmap_data)  x=day, y=role, color=cnt
                                  Y-axis sorted by total_cnt DESC
[Text]   Data Collection (bq_refresh)
[Table]  → dataframe_3 (bq_refresh_feed)
[Text]   Performance Audit (all channels)
[Table]  → dataframe_4 (performance_audit_feed)
[Text]   Keyword Management
[Table]  → dataframe_5 (keyword_mgmt_feed)
[Text]   Daily Report & Decisions
[Table]  → dataframe_6 (digest_feed)
[Text]   Anomaly Detection
[Table]  → dataframe_7 (spike_feed)
[Text]   Ops Scheduler
[Table]  → dataframe_8 (ops_feed)
[Text]   LLM Analysis (weekly/monthly)
[Table]  → dataframe_9 (llm_feed)
```

## Build status
- 2026-05-05: Initial v1 built with 2 cells.
- 2026-05-05: Rebuild matched reference (heatmap + stat cards + 4 per-role tables).
- 2026-05-06: Roles renamed to function-based; spec expanded to 7 per-role sections.
  Hex notebook needs:
    a. Rename existing `watcher_feed` SQL cell role filter `pause_watcher` → `performance_audit`
       (BQ migration already done, so this cell now shows merged data)
    b. Update title text "Campaign Actions (pause_watcher)" → "Performance Audit (all channels)"
    c. Add 3 new SQL cells: `keyword_mgmt_feed`, `spike_feed`, `llm_feed`
    d. Add 3 new title cells + table cells on canvas
    e. Default Time Range input value: 168 (was 24)
    f. Heatmap sort: Y-axis ordering by total_cnt DESC

## Notes
- "Never lose reference" rule: always save design references to this file immediately.
- Heatmap SQL has no role filter — any new role auto-appears as a new row.
- `channel` column distinguishes which platform was audited under `performance_audit`
  (e.g., `performance_audit | scale_task_created | google_ads`).

## QA Audit Feed (new cell — add to Hex)

SQL for qa_audit feed cell (add after the ops_feed section in canvas):

    SELECT
      FORMAT_DATETIME('%d %b %H:%M', DATETIME(ts, 'Asia/Riyadh')) AS time_riyadh,
      action,
      status,
      JSON_VALUE(details, '$.originating_agent') AS from_agent,
      JSON_VALUE(details, '$.error') AS error,
      ROUND(duration_s, 1) AS duration_s
    FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
    WHERE role = 'qa_audit'
      AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
    ORDER BY ts DESC
    LIMIT 100

Canvas addition: Add a [Text] "QA Gate" header + [Table] qa_audit_feed after the ops_feed section.
Status color: success = green (#3fb950), failed = red (#ff7b72).
