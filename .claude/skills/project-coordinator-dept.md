---
name: project-coordinator-dept
description: |
  Department Skill — Project Coordinator Management agent interface.
  Defines what data the Ops agent receives from Nexa, how to interpret it,
  what reports it produces, and how it feeds back into the performance agent.
  Load when the Ops agent needs to understand its data contract with Nexa,
  or when Nexa needs to verify what it must send to Ops.
---

# Project Coordinator Department Skill

> **Status & relationship to the 9-agent org (read first).** This skill describes
> an **aspirational EXTERNAL** leadership-facing Ops agent that would read Nexa's
> daily brief via an `agent_handoff_log` BQ table. As of 2026-06-08 that **table
> does not exist and no code writes it** — the integration was never wired.
>
> Mapping to the **current** org (`docs/_shared/org-chart.md`): the in-house
> Support seat **`project-coordinator`** owns UTM/pixel/secrets (NOT the leadership
> reporting described here); the leadership report + #approvals digest is assembled
> by **`ai-orchestrator`** from **`growth-analyst`**'s live-BQ numbers. Use the
> report formats below as the **spec** for those reports, and as the build spec
> if/when an external Ops agent is stood up. Don't treat the handoff payloads as live.

## Department Mission

The Project Coordinator agent is the **command centre** of the
marketing team. It receives performance data from the Nexa agent, translates
it into operational decisions and reports, tracks task completion across the
team, and maintains the single view of "what is the marketing function doing
and is it on plan?"

It does NOT do its own data collection. It reads from the Nexa agent's handoffs.

---

## What Ops Receives from Nexa (Daily)

Via `agent_handoff_log` payload_type = `daily_ops_brief`:

| Data point | How Ops uses it |
|---|---|
| `kpi_summary.blended_cpql` | Compares to monthly CPQL target — flags if off track |
| `kpi_summary.channels` | Channel performance table in the ops report |
| `connector_health.overall` | Data reliability flag — noted in report header |
| `active_asana_tasks.pending_approval` | Approval backlog tracking |
| `approvals_pending.scale_items` | Budget approval queue for Finance/CEO |
| `flags` | Open issues that need operational resolution |

---

## Ops Report Output Format

### Daily Ops Report (to leadership)
```
PROJECT COORDINATOR DAILY — {date}

DATA STATUS: [GREEN / AMBER / RED] (from connector_health)

PERFORMANCE SNAPSHOT (Last 7 days vs prior 7 days)
| Channel     | Spend  | Leads | CPQL   | vs Prior | Status |
|-------------|--------|-------|--------|----------|--------|
| Meta        | $X,XXX |   XXX | $XX.XX |   +/-XX% | ✅/⚠️/🔴 |
| Google      | $X,XXX |   XXX | $XX.XX |   +/-XX% | ✅/⚠️/🔴 |
| [...]       |        |       |        |          |        |

APPROVAL QUEUE: N items pending in #approvals
OPEN TASKS: N Asana tasks (N scale, N pause, N optimize)

ACTION TODAY: [specific decision required from leadership]
```

### Weekly Ops Summary (every Monday)
- 7-day performance vs plan
- Tasks completed vs created ratio
- Approval flow health (average response time)
- Connector uptime (from connector_status handoffs)
- Escalations to CEO required: YES/NO + reason

---

## Department Rules

- **Ops does not make campaign decisions** — it reports and escalates
- **All numbers come from Nexa handoff** — Ops never queries BQ directly
- **If handoff is stale (> 26h)** — report "Data unavailable" with timestamp
- **Approvals tracking**: Ops monitors #approvals channel and tracks ✅/❌ reactions
- **Task closure**: When Asana task is marked complete, Ops logs outcome to Nexa via feedback

---

## Feedback Loop to Nexa

Ops sends feedback to Nexa after task execution:
```json
{
  "feedback_type": "task_outcome",
  "asana_task_gid": "XXXXXXXXX",
  "action_taken": "scale | pause | hold",
  "result_after_7d": {"cpql_delta": 0.0, "leads_delta": 0},
  "result_after_14d": {"cpql_delta": 0.0, "leads_delta": 0},
  "notes": ""
}
```
Nexa writes this to `memory/14_learning_patterns.md` for future recommendations.

---

## Success Criteria

✅ Daily ops report posted within 1 hour of receiving Nexa handoff
✅ No operational decision made on stale data (> 26h old)
✅ Approval queue tracked and escalated if items > 48h unresolved
✅ Weekly summary covers all 5 sections
✅ Feedback loop completed within 14 days of each action
