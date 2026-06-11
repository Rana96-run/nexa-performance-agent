---
name: weekly-review
description: Run the Monday weekly ops review. Produces a 5-section performance summary for leadership covering 7-day vs prior 7-day performance, task velocity, approval flow health, connector uptime, and a month-end forecast.
schedule: "0 5 * * 1"
timezone: Asia/Riyadh
agent: ai-orchestrator
connectors: [bigquery, slack, asana]
---

# /weekly-review — Monday Weekly Ops Summary

You are the **AI Orchestrator** running the Monday weekly ops review. Produce a 5-section summary for leadership and route any flags to the right department.

## What this skill does

Pulls 7-day performance data from BQ, compares to prior week, assesses task velocity and approval health, checks connector uptime, and posts a structured Slack summary with a month-end forecast.

## The 5 sections

### 1. Performance (7d vs prior 7d)

Pull from `paid_channel_daily`:
```sql
SELECT channel,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend END) AS spend_curr,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
            AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend END) AS spend_prior,
  SAFE_DIVIDE(
    SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) THEN spend END),
    NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
                    THEN qualified END), 0)
  ) AS cpql_curr
FROM paid_channel_daily
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
GROUP BY channel ORDER BY spend_curr DESC
```

Format: `| Channel | Spend | Leads | CPQL | vs Prior |`

### 2. Task velocity

From Asana (via connector): tasks created this week vs completed. Approval queue backlog (items pending > 48h).

Flag if: completion rate < 70% OR any approval pending > 48h.

### 3. Approval flow health

Average time from digest posted → ✅ received this week. Target: < 24h.

### 4. Connector uptime

From BQ `connector_health_log`: count of HEALTHY / WARNING / BROKEN checks per channel this week. Flag any channel with > 2 BROKEN in the week.

### 5. Month-end forecast

Based on current pace (MTD spend ÷ days elapsed × days remaining):
- Projected spend
- Projected leads
- Projected CPQL (assuming current pace)
- Gap to CPQL target ($85)

## Slack output format

```
*Nexa Weekly Review — {Mon date} to {Sun date}*  |  {dashboard_url}

PERFORMANCE vs PRIOR WEEK
{table}

TASK VELOCITY: {N} created / {N} completed  ·  Approval backlog: {N} items
CONNECTOR UPTIME: {N} healthy / {N} warning / {N} broken this week
MONTH-END FORECAST: ${spend_proj} spend · {leads_proj} leads · ${cpql_proj} CPQL

{flag block if any escalation needed}
```

## Hard rules

- 7d vs prior 7d comparison always. Never single-week snapshot without context.
- Escalate to `performance-lead` if CPQL_curr > $130 on any channel.
- Escalate to `project-coordinator` if any connector has been BROKEN for 3+ consecutive checks.
- Month-end forecast based on live BQ MTD data — never from memory.

## Done means

5-section summary posted to Slack, flags routed to department leads, month-end forecast included.
