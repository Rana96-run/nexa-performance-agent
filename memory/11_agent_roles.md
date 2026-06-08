# Agent Roles — What Lives Here vs Elsewhere

> **Canonical roster is `docs/_shared/org-chart.md`.** As of 2026-06-08 the team
> is **9 agents** (1 manager + 3 departments), matching the live "NEXA OPERATIONS
> HQ — The Team" dashboard. Each is a Claude Code subagent in `.claude/agents/`
> with its own playbook (`docs/playbooks/<dept>/<role>.md`) and memory
> (`memory/agents/<dept>/<role>/`).

## 9 agents ≠ 13 log-roles (the trap that caused a wrong rebuild)
- **The team = 9 agents** (org chart, below). This is who exists.
- **`agent_activity_log` has 13 `role` values** — these are how work is *logged*,
  NOT teammates: infra/system labels (`health_monitor`, `bq_refresh`, `collector`,
  `ops_scheduler`), the human (`user`), and function buckets the agents act under
  (`performance_audit`, `keyword_management`, `task_creator`, `daily_digest`,
  `campaign_creator`, `llm_cadence`, `paid_media_strategist`). Don't build agents
  from the log table — build from the org chart.

## Two layers — don't confuse them
- **Dev-time subagents** (`.claude/agents/*.md`) — the 9-agent team. Isolated
  context per role → less hallucination.
- **Production runtime** (`claude/roles.py` + `claude/manager.py`) — the
  autonomous Railway product; logs under the 13 function-roles above. Untouched.

## The 9 agents (3 departments + manager)

| Dept | Agent | Parallel/Sequential |
|---|---|---|
| _Manager_ | `ai-orchestrator` | gates all writes ✅, owns all handoffs, 8-step loop 08:00 |
| Performance (LEAD `performance-lead`) | `campaign-manager`, `creative-strategist` | the two directs run **in parallel** |
| CRO / Landing Page | `cro-specialist` → `ui-ux-designer` → `developer` | **direct sequential handoff** |
| Support (serve both, no internal handoff) | `marketing-ops`, `growth-analyst` | run **in parallel** |

`growth-analyst` owns `memory/` (writes 08_pitfalls + 14_learning_patterns).

## Separate agents (NOT in this repo)

| Role | What it owns | How we reach it |
|---|---|---|
| **Creative agent** | Ad creatives, LP builds, **CRO** (bounce fixes, form fixes, LP copy) | Asana `[Creative Brief]` tasks |
| **Marketing Ops agent** | Lifecycle, HubSpot workflows, email sequences, list building | Asana `[MarkOps Brief]` tasks |

## What was removed from this repo

- `qoyod-creative-agent.md` — moved to external Creative agent
- `qoyod-hubspot-cro-agent.md` — CRO merged into external Creative agent
- Old "Marketing Ops" duties inside the PM flow — moved to external Marketing Ops agent
- `qoyod-reporter-agent.md` — renamed to `qoyod-analyst-agent.md` and scoped
  up to cover continuous analysis + scaling + lead-quality, not just digests

## Decision flow at a glance

```
Data in BigQuery
      │
      ▼
Analyst agent  →  flags: scale / pause / LP / lead-quality
      │
      ▼
Project Manager  →  routes + opens Asana task to correct owner
      ├──► Paid Media agent (in repo): approval + execution
      ├──► Creative agent (external): creative / LP / CRO
      └──► Marketing Ops agent (external): lifecycle / workflow / email
      │
      ▼
Human approves in Slack (for anything that touches a live ad account)
      │
      ▼
Action executed · logged · monitored for stop condition
```

## Non-negotiables

- **Scaling** is the highest-leverage work this system does — Analyst
  surfaces, PM routes, Paid Media drafts approval, human ✅, revert is
  pre-approved as a stop condition.
- **Lead-quality monitoring** is continuous, not periodic — Analyst watches
  qual ratio + disqual-reason concentration + time-to-qualify per ad.
- **This repo never does creative work or lifecycle work** — it briefs the
  external agent via Asana with complete context and data.
- **Lead ≠ SQL.** CPL from Lead module; CPQL from SQL (Contact module). Ad
  platforms optimize on Contact events only.
