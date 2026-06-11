---
name: daily-slack-audit
description: Run daily at 10:00 Riyadh. Checks if yesterday's #approvals digest received a ✅ or ❌ reaction within 24h. Replies in-thread if unanswered. Flags approved-but-unexecuted actions to Asana.
schedule: "0 7 * * *"
timezone: Asia/Riyadh
agent: project-coordinator
connectors: [slack, bigquery, asana]
---

# /daily-slack-audit — Daily Approval Flow Audit

You are the **Project Coordinator** running the daily Slack approval audit. Your job is to close the loop between what the system posted and what the human approved.

## What this skill does

1. Reads #approvals channel history for the last 26h (buffer for digest timing)
2. Finds messages posted by the system bot
3. Checks reaction status for each
4. Replies in-thread if unanswered → one reminder per thread, max
5. Checks BQ `agent_activity_log` for execution after each ✅ approval
6. Creates Asana task if approved action has no execution log entry

## Step 1 — Fetch recent digest messages

Read `SLACK_CHANNEL_APPROVAL` history for the last 26h. Filter to messages where:
- `bot_id` is set (system-posted messages)
- Message contains "ACTIONS:" block (the nightly digest format)

For each such message, note: `ts` (timestamp), `text` preview, reaction list.

## Step 2 — Reaction check

For each digest message:

| Reaction state | Age | Action |
|---|---|---|
| No reaction | < 2h | Skip — too early |
| No reaction | 2h–24h | Reply in-thread (once) |
| No reaction | > 24h | Reply in-thread + create Asana escalation |
| ✅ received | any | Check execution (Step 3) |
| ❌ received | any | Log "rejected" to BQ, no further action |

**Reply format (in-thread):**
> No approval received yet on this digest. Please react with ✅ to approve all scale/pause actions, or ❌ to skip. Review-only items (Asana tasks) don't need a reaction.

Post this reply only once per thread. Before posting, check thread replies for an existing reminder — skip if already posted.

## Step 3 — Execution check (for ✅ messages)

When a ✅ reaction is found on a digest message:

Query BQ:
```sql
SELECT action, status, ts
FROM `{PROJECT}.{DATASET}.agent_activity_log`
WHERE action IN (
  'scale_campaign_executed', 'pause_campaign_executed',
  'pause_ad_executed', 'budget_redeployment_executed',
  'action_approved_via_slack'
)
  AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), ts, HOUR) <= 4
ORDER BY ts DESC
LIMIT 20
```

If `action_approved_via_slack` exists for this digest's `ts` window but NO subsequent `*_executed` entry exists within 4h → create an Asana escalation task.

## Step 4 — Asana escalation (approved but not executed)

```
APPROVAL NOT EXECUTED — {date}

An action was approved in #approvals but no execution was logged in BQ.

Approval timestamp: {ts}
Digest summary: {first 200 chars of digest text}

WHAT TO CHECK:
1. Railway logs for the operational scheduler around approval time
2. agent_activity_log for any errors from the executor
3. Was the approval reaction added after the 30-min reaction timeout window?

This task auto-closes when an execution entry appears for the same digest.

Created: {date}
Due: {date}
Priority: High
Type: System Health
Channel: all
Asset level: campaign
Action: investigate → [Project Coordinator]
```

## Step 5 — Log to BQ

```python
log_activity_async(
    role="project_coordinator",
    action="slack_audit_complete",
    status="success",
    details={
        "digests_checked": N,
        "no_reaction": N,
        "reminders_sent": N,
        "execution_gaps": N,
    }
)
```

## Hard rules

- **Scope: #approvals only.** Never audit `SLACK_CHANNEL_NOTIFY` or other channels.
- **One reminder per thread.** Check thread replies before posting. Silent if already reminded.
- **No Asana tasks for missing reactions** — only post a reminder in-thread. Asana is only for execution gaps (Step 4).
- **Never escalate to another agent.** Flag in Asana; a human routes it.
- **Run at 10:00 Riyadh** (07:00 UTC) — 2h after the nightly digest posts. Earlier runs will always find no reactions.

## Done means

All digest messages in the last 26h checked. Unanswered items replied-to in thread. Execution gaps flagged in Asana. BQ log entry written.
