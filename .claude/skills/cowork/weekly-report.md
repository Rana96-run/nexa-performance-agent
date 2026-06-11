---
name: weekly-report
description: One-page stakeholder performance summary — total spend, leads, SQLs, CPQL, top channel, biggest win and biggest gap vs last week. Clean, no ops detail. Post every Monday to the notify channel.
schedule: "30 5 * * 1"
timezone: Asia/Riyadh
agent: performance-lead
connectors: [bigquery, slack]
---

# /weekly-report — Monday Stakeholder Summary

You are the **Performance Lead** posting the weekly executive summary. This is for stakeholders, not the ops team — one glance, no noise.

## What this skill does

Pulls last 7 days vs prior 7 days from BQ. Formats a clean 6-line Slack message. Runs 30 minutes after `/weekly-review` (05:00 UTC) so ops and stakeholder posts don't collide.

## BQ query

```sql
SELECT
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
           THEN spend END)                                           AS spend_curr,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
            AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
           THEN spend END)                                           AS spend_prior,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
           THEN leads_total END)                                     AS leads_curr,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
            AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
           THEN leads_total END)                                     AS leads_prior,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
           THEN qualified END)                                       AS sqls_curr,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
            AND date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
           THEN qualified END)                                       AS sqls_prior
FROM `{PROJECT}.{DATASET}.paid_channel_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
```

Also pull best and worst channel (by CPQL) for the current 7-day window from `paid_channel_daily` grouped by channel.

## Slack message format

Post to `SLACK_CHANNEL_NOTIFY`:

```
*Nexa — Week of {Mon date} to {Sun date}*

Spend:   ${spend_curr}   ({▲/▼}{delta%} vs prior week)
Leads:   {leads_curr}    ({▲/▼}{delta%})
SQLs:    {sqls_curr}     ({▲/▼}{delta%})
CPQL:    ${cpql_curr}    {✅/⚠️/🔴}  ({▲/▼}{delta%})

Best channel:  {channel} — ${cpql} CPQL
Needs work:    {channel} — ${cpql} CPQL

{dashboard_url}
```

CPQL icon: ✅ < $85 | ⚠️ $85–$130 | 🔴 > $130

Delta format: `▲12%` (up) or `▼8%` (down). No decimal places on percentages.

## Hard rules

- Max 10 lines including the header. No tables, no bullet lists of campaigns.
- No ops detail (no approval queue, no connector status, no keyword counts) — that's for `/weekly-review`.
- If CPQL is 🔴 for 2+ consecutive weeks, add one line: `Action needed — see #approvals`.
- Runs at 05:30 UTC Monday (30 min after `/weekly-review` at 05:00).
- Posts to `SLACK_CHANNEL_NOTIFY` only.

## Done means

6-line Slack summary posted. CPQL icon correct. Delta direction arrows correct. Dashboard link included.
