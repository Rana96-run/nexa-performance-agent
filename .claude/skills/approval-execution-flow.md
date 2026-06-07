---
name: approval-execution-flow
description: |
  Workflow Skill — Approval execution protocol.
  Defines the complete flow from "agent identifies a recommended action"
  to "action is executed in the platform". Covers the #approvals Slack
  digest format, the ✅/❌ reaction protocol, and the exact execution
  sequence for scale, pause, optimize, and junk actions.
  Load whenever preparing the nightly digest OR executing approved actions.
---

# Approval Execution Flow

## The Rule (non-negotiable)

**Every write action — scale, pause, enable, create — requires a ✅ reaction
in #approvals before execution. No exceptions. The agent never auto-executes.**

The only exemption: **negative keyword additions** (zero spend at risk).

---

## Stage 1 — Agent Identifies Actions (Nightly)

Triggered by `main.py daily` or `operational_scheduler.py` nightly sweep.

Action types and their routing:

| Action type | Goes to | Execution |
|---|---|---|
| `scale` | #approvals digest + Asana | Executes ONLY after ✅ |
| `pause` | #approvals digest + Asana | Executes ONLY after ✅ |
| `optimize` | Asana only (review task) | No platform execution — team reviews |
| `junk` | Asana only (review task) | No platform execution — team reviews |
| `drilldown` | Asana only (FYI task) | No platform execution |
| `add_negative_kw` | Direct-execute silently | No approval needed |

All actions that need approval are **batched into a single nightly digest** —
never posted individually throughout the day.

---

## Stage 2 — Build the Nightly #approvals Digest

Post one Slack message to `#approvals`. Format:

```
*Nightly Actions — {date} ({N} items need approval)*

*SCALE ({n} items):*
• {Campaign > Ad Set > Ad} — Budget +{X}% → ${new}/day | CPQL ${x} (14d) ✅ Asana: {url}
• ...

*PAUSE ({n} items):*
• {Campaign > Ad Set > Ad} — ${spend} / {days}d / {reason} ✅ Asana: {url}
• ...

*REVIEW ONLY — no action needed:*
• Optimize: {n} items in Asana
• Junk leads: {n} items in Asana
• Drilldown: {n} items in Asana

React ✅ to execute ALL scale + pause items above.
React ❌ to skip all.
Individual overrides: comment the item number to exclude.
```

**Rules:**
- One message only — never split across threads for the same digest
- No keywords in Slack (keyword changes go to Asana only)
- No abbreviations (IS = Impression Share — spell it out or omit)
- Dashboard link is the short slug URL, not full Looker URL
- Date ranges must be explicit (`YYYY-MM-DD to YYYY-MM-DD`) for every data point

---

## Stage 3 — Wait for Reaction

The agent polls `#approvals` for a ✅ or ❌ reaction on the digest message.
Polling happens via Slack MCP — check the thread reactions, not just replies.

| Reaction | Action |
|---|---|
| ✅ | Execute ALL scale + pause items in the digest |
| ❌ | Skip all — no execution |
| No reaction after 24h | Escalate in thread: "⏰ No approval received. Items expire in 24h." |
| No reaction after 48h | Cancel batch, log to BQ as `expired`, create Asana escalation task |

**Individual override:** If a comment says "skip item 2", the agent excludes
item 2 from execution and proceeds with the rest.

---

## Stage 4 — Execute Approved Actions

Execute in this order (lowest risk first):
1. **Pause** ads (removing spend — safe to do first)
2. **Scale** campaigns/ad sets (increasing budget — do after pauses so budget math is fresh)

### Scale execution (via Adspirer or platform API)
```python
# Meta — budget change on ad set
mcp__adspirer__meta_ads({
    "action": "update_budget",
    "adset_id": "{id}",
    "daily_budget": {new_budget_cents}
})

# Google — campaign budget update
mcp__adspirer__google_ads({
    "action": "update_budget",
    "campaign_id": "{id}",
    "amount_micros": {new_budget_micros}
})
```

### Pause execution
```python
# Meta — pause ad
mcp__adspirer__meta_ads({
    "action": "update_status",
    "ad_id": "{id}",
    "status": "PAUSED"
})
```

**After execution:**
- Reply in the #approvals thread: "✅ {N} actions executed. {errors if any}."
- Update each Asana task status to `in_progress`
- Log execution to BQ `action_log` table

---

## Stage 5 — 7-Day and 14-Day Outcome Check

Every executed action is re-evaluated. The operational scheduler checks:
- 7 days post-execution: CPQL delta vs baseline
- 14 days post-execution: final outcome verdict

**Outcome verdict logic:**
| Result | Verdict | Memory update |
|---|---|---|
| CPQL improved > 10% | `SUCCESS` | Log to `memory/14_learning_patterns.md` as confirmed pattern |
| CPQL flat (±10%) | `NEUTRAL` | Note — insufficient signal, hold |
| CPQL worse > 10% | `FAILURE` | Log as anti-pattern; revert if > 20% degradation |

Update the Asana task with the 14-day outcome before closing it.

---

## BQ Logging

Every approval action (approved, skipped, expired, executed, outcome) is
written to BQ `action_log`:

```sql
-- Schema
action_id        STRING   -- UUID
date             DATE
campaign_name    STRING
action_type      STRING   -- scale | pause | optimize | junk
channel          STRING
approval_status  STRING   -- pending | approved | skipped | expired
executed_at      TIMESTAMP
outcome_7d_cpql  FLOAT64
outcome_14d_cpql FLOAT64
outcome_verdict  STRING   -- SUCCESS | NEUTRAL | FAILURE
asana_task_gid   STRING
```

---

## Rules & Guardrails

1. **One nightly digest, never ad-hoc Slack messages** for approvals
2. **Never auto-execute** scale or pause — even if ✅ was given in a prior message
3. **Never execute during a data gap** — if connector health is RED for the
   channel being actioned, skip that action and note it in the thread
4. **Pause always precedes scale** in execution order (spend math)
5. **No execution on campaigns < 14 days old** — minimum data window is 14 days
6. **Always log to BQ** — execution without a log entry is invisible to future analysis
7. **Asana task must exist before execution** — the approval digest links to the task; if the task was not created, do not execute
