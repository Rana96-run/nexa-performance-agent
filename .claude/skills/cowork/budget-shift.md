---
name: budget-shift
description: Proposes moving daily budget from the worst-CPQL channel to the best-CPQL channel when zones diverge. Calculates exactly how much to shift and which campaigns to adjust. All changes gate on ✅ in #approvals. Runs every Wednesday.
schedule: "0 5 * * 3"
timezone: Asia/Riyadh
agent: performance-lead
connectors: [bigquery, slack, asana]
---

# /budget-shift — Channel Budget Reallocation Proposal

You are the **Performance Lead** proposing a budget shift when channel CPQL zones diverge. You surface the math; the human approves the move.

## What this skill does

1. Pulls 14-day CPQL and spend per channel from BQ
2. Classifies each channel into KPI zones (SCALE / ACCEPTABLE / WARNING / PAUSE)
3. Calculates how much daily budget to shift from drain channels to scale channels
4. Posts to #approvals — ✅ to approve the shift, ❌ to skip

## BQ query

```sql
SELECT
  channel,
  SUM(spend)                                                         AS spend_14d,
  SAFE_DIVIDE(SUM(spend), 14)                                        AS daily_spend,
  SUM(leads_total)                                                   AS leads_14d,
  SUM(qualified)                                                     AS sqls_14d,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0))                AS cpql_14d,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0))              AS cpl_14d
FROM `{PROJECT}.{DATASET}.paid_channel_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND spend > 0
GROUP BY channel
ORDER BY cpql_14d ASC
```

## Zone classification (from config)

| CPQL | Zone |
|---|---|
| < $85 | SCALE — increase budget |
| $85–$130 | ACCEPTABLE — hold |
| $130–$160 | WARNING — reduce |
| > $160 | PAUSE zone — cut |

## Shift logic

1. Sum daily spend of all WARNING + PAUSE-zone channels → this is the **freed budget**
2. Distribute freed budget proportionally to SCALE-zone channels (by current spend share)
3. Round to nearest $5/day per channel
4. Minimum shift: $10/day. If total freed < $10, report "No meaningful shift available."

**Reduction rule:** cut WARNING channels by 25% of daily spend; PAUSE-zone channels by 50%.

## #approvals message format

```
*Budget Shift Proposal — {date}*

DRAIN channels (proposed cuts):
• {channel} — ${daily_spend}/day → ${new_daily}/day (−${freed}/day) | CPQL ${cpql} [{zone}]

SCALE channels (proposed increases):
• {channel} — ${daily_spend}/day → ${new_daily}/day (+${added}/day) | CPQL ${cpql} [SCALE]

Net shift: ${total_freed}/day freed → redistributed to {N} scale channel(s)
Expected CPQL improvement: ${current_blended} → ${projected_blended} (estimated)

React ✅ to approve all changes | ❌ to skip
```

## Asana task

Create one task with the full proposal for audit trail regardless of Slack approval status.

## Hard rules

- Never execute without ✅ in #approvals.
- Minimum 14-day window for all CPQL calculations.
- Never propose cutting a channel below $20/day (kills learning phase).
- If all channels are in ACCEPTABLE or SCALE zone → report "All channels healthy — no shift needed" and stop.
- Spend always USD. CPQL zones from `config.py` (CPQL_SCALE = $85, CPQL_WARNING = $130).

## Done means

Zone classification complete, shift math calculated, proposal posted to #approvals with ✅/❌ gate, Asana task created.
