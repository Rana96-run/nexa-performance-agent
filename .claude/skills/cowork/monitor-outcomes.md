---
name: monitor-outcomes
description: Daily check on approved pause/scale/budget actions at +7 and +14 days. Queries agent_activity_log for approved actions from exactly 7 and 14 days ago, posts a re-evaluation prompt to #approvals. No ✅ needed — review only. Ensures every approved action is measured, not just executed.
schedule: "0 5 * * *"
timezone: Asia/Riyadh
agent: ai-orchestrator
connectors: [bigquery, slack]
---

# /monitor-outcomes — Approved Action Follow-Up (+7 and +14 Days)

You are the **AI Orchestrator** running the daily outcome monitor. Your job is to make sure every approved action gets evaluated 7 and 14 days after it was executed — not just filed in Asana and forgotten.

## What this skill does

1. Queries `agent_activity_log` for approved actions from exactly 7 and 14 days ago
2. If any are found: posts a structured check-in to Slack #approvals asking the team to evaluate outcomes
3. If none are found: posts nothing

## BQ query

```sql
SELECT
  action,
  details,
  ts,
  role,
  DATE(ts, 'Asia/Riyadh') AS action_date
FROM `{PROJECT}.{DATASET}.agent_activity_log`
WHERE status = 'approved'
  AND action IN (
    'scale_campaign', 'pause_keyword', 'pause_ad',
    'budget_increase', 'budget_decrease', 'pause_campaign',
    'scale_task_created', 'pause_task_created'
  )
  AND DATE(ts, 'Asia/Riyadh') IN (
    DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY),
    DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
  )
ORDER BY ts DESC
LIMIT 30
```

## Slack message format

Post to Slack #approvals channel:

```
*Outcome check — approved actions due for review*

*7-day check-in (approved on {7_days_ago}):*
{for each action from 7 days ago:}
• {action_type}: {campaign or keyword name} — did it work? Pull the period compare and reply here.

*14-day check-in (approved on {14_days_ago}):*
{for each action from 14 days ago:}
• {action_type}: {campaign or keyword name} — final verdict? Close the Asana task with the outcome.

No ✅ needed — reply in-thread with: working ✓ / not working ✗ / reversed ↩
```

Only include the sections (7-day / 14-day) that have actions. If both are empty, post nothing.

## Extracting context from details

The `details` field is JSON. Extract:
- `details.campaign` or `details.campaign_name` → campaign name
- `details.keyword` → keyword text
- `details.ad_name` → ad name
- `details.channel` → channel
- `details.spend_delta` or `details.budget_delta` → amount changed

If none of the above resolve, fall back to `action + role` as the label.

## Hard rules

- Post to #approvals only. Never post to #notifications or #general.
- No ✅/❌ reaction needed — this is a review prompt, not an execution gate.
- Post nothing if no actions are due today.
- Only approved actions — ignore pending, rejected, or failed statuses.
- Max 30 rows per run to keep the message readable.

## Done means

If actions are due: one Slack message posted to #approvals with a check-in for each. If none are due: nothing posted.
