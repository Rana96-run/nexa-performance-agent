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

## Three taxonomies — how the layers map (the "one source of truth" view)

There are three vocabularies in this repo. They are NOT the same axis; this table
is the bridge so a change in one is traceable to the others.

| 9-agent seat (dev-time) | Runtime LLM role (`claude/roles.py` → `md_files/`) | Activity-log label(s) |
|---|---|---|
| `ai-orchestrator` | `daily_report` (qoyod-daily-report.md) + manager-os | `ops_scheduler`, `daily_digest`, `task_creator` |
| `performance-lead` | `paid_media_strategist` (nexa-strategist.md) | `performance_audit`, `paid_media_strategist` |
| `campaign-manager` | `media_buyer` (qoyod-paid-media-agent.md) | `campaign_creator`, `keyword_management` |
| `creative-strategist` | — (brand-identity shared) | — (creative work isn't logged) |
| `cro-specialist` / `ui-ux-designer` / `developer` | — (CRO was external in the runtime era) | — (LP work isn't logged) |
| `marketing-ops` | — | `health_monitor`, `collector` |
| `growth-analyst` | `paid_media_analyst` (qoyod-analyst-agent.md) | `bq_refresh`, `spike_detector`, `llm_cadence` |

**Full coverage — all 13 log-roles owned 1:1 (no orphans, no double-claims).** `user`
is the human (not a seat). If a NEW log-role appears unowned, that's a police
finding — assign it before it runs unattended (see `docs/_shared/police-loop.md`).

**Dashboard must mirror this.** `reports/app.py` team `roles` sets are the dashboard
display of this mapping — they must match the column above, or activity shows as
unattributed. (As of 2026-06-08 app.py had orphans: `task_creator`, `collector`,
`paid_media_strategist`, `campaign_creator` unassigned — align to this table.)

Shared runtime context: `qoyod-manager-os.md` ↔ `CLAUDE.manager.md`;
`qoyod-brand-identity.md` ↔ `docs/landing-pages/reference/brand/`.

### Phase-2 unification (NOT done — deliberate)
Pointing `claude/roles.py` directly at the dev playbooks would shrink the runtime
prompts (rich ~23KB personas → tight procedures) and **degrade production**. The
correct unify is to (a) keep `md_files/` as the runtime's rich source, and (b)
have each persona and its dev playbook cross-reference this table so neither
drifts — or, if we want true single-source, *grow* the playbooks to runtime depth
first, then repoint. Either way it's a reviewed change to live code, not a blind
repoint. Left for an explicit go.

## What's in-house vs external (updated 2026-06-08)

The new org brought **CRO / Landing Page in-house** (Dept 2: `cro-specialist` →
`ui-ux-designer` → `developer`) and made **Marketing Ops** an in-house Support
seat. What stays external:
- **Creative production** (cutting actual ad creatives) — briefed via Asana
  `[Creative Brief]`. Our `creative-strategist` owns *direction*, not production.
- **Lifecycle / email / HubSpot workflows** — briefed via Asana `[MarkOps Brief]`.
  Our `marketing-ops` owns tracking/pixels/secrets, not lifecycle automation.

## Decision flow at a glance (9-agent org)

```
Data in BigQuery
      │  growth-analyst (observe + compare, live BQ)
      ▼
performance-lead  →  routes the flag to the right seat
      ├──► campaign-manager      : build / pause / scale (after ✅)
      ├──► creative-strategist   : copy / A/B direction → external creative prod
      └──► cro-specialist → ui-ux-designer → developer : the landing-page test
      │
      ▼
ai-orchestrator  →  queues all writes into ONE #approvals digest
      │
      ▼
Human ✅ in Slack (anything touching a live ad account or LP deploy)
      │
      ▼
Executed · approval-tracked · re-evaluated 7d/14d · outcome → memory
```

## Non-negotiables

- **Scaling** is the highest-leverage work — `growth-analyst` surfaces,
  `performance-lead` routes, `campaign-manager` drafts approval, human ✅, revert
  is the pre-approved stop condition.
- **Lead-quality monitoring** is continuous — qual ratio + disqual-reason
  concentration + time-to-qualify per ad.
- **Creative production + lifecycle stay external** — briefed via Asana with full
  context. CRO/LP and tracking are now in-house.
- **Lead ≠ SQL.** CPL from Lead module; CPQL from SQL (Contact module). Ad
  platforms optimize on Contact events only.
