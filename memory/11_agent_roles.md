# Agent Roles — What Lives Here vs Elsewhere

> **Canonical roster is `docs/_shared/org-chart.md`.** As of 2026-06-22 the team
> is **8 agents** (1 manager + 3 departments + 1 QA Auditor cross-cutting), matching
> the live "NEXA OPERATIONS HQ — The Team" dashboard. Each is a Claude Code subagent
> defined in `.claude/agents/` — that file is the single source of truth for each role.
>
> **2026-06-22 restructure:** `ui-ux-designer` merged into `cro-specialist` (CRO chain now 2 steps). Performance Lead removed from daily KPI flag path. Sunday hygiene scans added to growth-analyst and project-coordinator.

## 8 agents ≠ 13 log-roles (the trap that caused a wrong rebuild)
- **The team = 8 agents** (org chart, below). This is who exists.
- **`agent_activity_log` has 13 `role` values** — these are how work is *logged*,
  NOT teammates: infra/system labels (`health_monitor`, `bq_refresh`, `collector`,
  `ops_scheduler`), the human (`user`), and function buckets the agents act under
  (`performance_audit`, `keyword_management`, `task_creator`, `daily_digest`,
  `campaign_creator`, `llm_cadence`, `paid_media_strategist`). Don't build agents
  from the log table — build from the org chart.

## Two layers — don't confuse them
- **Dev-time subagents** (`.claude/agents/*.md`) — the 8-agent team. Isolated
  context per role → less hallucination. **This is now the single active layer.**
- **Production runtime** (`claude/roles.py` + `claude/manager.py`) — **DELETED 2026-06-16** along with `runtime_personas/`. Railway is deprecated. The 13 function-roles in `agent_activity_log` remain as historical log labels only.

## The 8 agents (3 departments + manager + QA Auditor)

| Dept | Agent | Parallel/Sequential |
|---|---|---|
| _Manager_ | `ai-orchestrator` | gates all writes ✅, owns all handoffs, 8-step loop 08:00, does NOT re-validate (QA Auditor owns that) |
| Performance (strategic: `performance-lead`) | `campaign-manager`, `creative-strategist` | KPI flags → campaign-manager directly from project-coordinator; performance-lead = strategic only |
| CRO / Landing Page | `cro-specialist` (brief + design) → `developer` | **direct sequential handoff — 2 steps** |
| Support (serve both, no internal handoff) | `project-coordinator`, `growth-analyst` | run **in parallel**; both run Sunday hygiene scans |

`growth-analyst` owns `memory/` (writes 08_pitfalls + 14_learning_patterns).

## Three taxonomies — how the layers map (the "one source of truth" view)

There are three vocabularies in this repo. They are NOT the same axis; this table
is the bridge so a change in one is traceable to the others.

| 8-agent seat (dev-time) | Runtime LLM role (`claude/roles.py`) | Activity-log label(s) | Asana assignee |
|---|---|---|---|
| `ai-orchestrator` | `daily_report` + manager-os | `ops_scheduler`, `daily_digest`, `task_creator` | Rana Khalid |
| `performance-lead` *(strategic only)* | `paid_media_strategist` | `performance_audit`, `paid_media_strategist` | Rana Khalid |
| `campaign-manager` | `media_buyer` | `campaign_creator`, `keyword_management` | Donia Mohamed |
| `creative-strategist` | — (brand-identity shared) | `creative_strategy` | Donia Mohamed |
| `cro-specialist` *(brief + design)* | — | `cro_specialist`, `ui_ux_design` | Rana Khalid |
| `developer` | — | `lp_developer` | Tony Helmy (+ Rana follower) |
| `project-coordinator` *(OPS)* | — | `health_monitor`, `collector` | Donia Mohamed |
| `growth-analyst` | `paid_media_analyst` | `bq_refresh`, `spike_detector`, `llm_cadence` | Rana Khalid |
| `qa-auditor` *(QA gate, cross-dept)* | — | `qa_audit` | Rana Khalid |

Note: `ui-ux-designer` was merged into `cro-specialist` on 2026-06-22. The `ui_ux_design` log label is now owned by `cro-specialist`.

**Full coverage — all log-roles owned 1:1 (no orphans, no double-claims).** `user`
is the human (not a seat). If a NEW log-role appears unowned, that's a police
finding — assign it before it runs unattended (see `docs/_shared/police-loop.md`).

### qa_audit log-role
- **Role value:** `qa_audit`
- **Owned by:** `qa-auditor` (cross-dept, Layer 2)
- **Description:** Validation checks run on all Layer 3 agent outputs before reaching the Orchestrator. Logs one row per check run.
- **Status meanings:** `success` = QA_PASSED (output forwarded to Orchestrator); `failed` = QA_FAILED (returned to originating agent for correction).
- **Receives from:** all Layer 3 agents (`growth-analyst`, `performance-lead`, `campaign-manager`, `creative-strategist`, `cro-specialist`, `developer`, `project-coordinator`)
- **Sends to:** `ai-orchestrator` on pass; originating agent on fail.

**Asana GIDs (confirmed 2026-06-09 via API):**
- Rana Khalid: `1208007704598388`
- Donia Mohamed: `1211896896006183`
- Tony Helmy (thelmy@qoyod.com): `1211659245827014`

**Dashboard:** The Railway `/activity` endpoint (served by `reports/app.py`) is the sole activity dashboard as of 2026-06-21. The Hex Agent Activity dashboard (`Nexa-Agent-Activity-033ArC9Xytz3SK6tPXwk9D`) and GitHub Pages dashboard were removed 2026-06-21. `reports/app.py` is still live on Railway.

Shared runtime context: `qoyod-manager-os.md` ↔ `CLAUDE.manager.md`;
`qoyod-brand-identity.md` ↔ `docs/landing-pages/reference/brand/`.

### Phase-2 unification (MOOT — superseded 2026-06-16)
`claude/roles.py` and `runtime_personas/` were both **deleted on 2026-06-16** as part of the Railway deprecation cleanup. The Railway runtime no longer runs. Phase-2 unification (pointing `roles.py` at the dev playbooks) is no longer relevant. The dev-time subagents in `.claude/agents/` are now the single source of truth.

## What's in-house vs external (updated 2026-06-22)

The org brought **CRO / Landing Page in-house** (Dept 2: `cro-specialist` (brief + design) →
`developer`) and made **Project Coordinator** an in-house Support seat. What stays external:
- **Creative production** (cutting actual ad creatives) — briefed via Asana
  `[Creative Brief]`. Our `creative-strategist` owns *direction*, not production.
- **Lifecycle / email / HubSpot workflows** — briefed via Asana `[MarkOps Brief]`.
  Our `project-coordinator` owns tracking/pixels/secrets, not lifecycle automation.

## Decision flow at a glance (8-agent org)

```
Data in BigQuery
      │  growth-analyst (observe + compare, live BQ)
      ▼
project-coordinator  →  routes KPI flags DIRECTLY to campaign-manager
      ├──► campaign-manager      : KPI flag response / build / pause / scale (after ✅)
      ├──► creative-strategist   : copy / A/B direction → external creative prod
      └──► growth-analyst → cro-specialist → developer : the landing-page test
      │
      ▼
performance-lead  →  strategic decisions only (budget realloc, channel launch/sunset, config.py)
      │
      ▼
ai-orchestrator  →  queues all writes into ONE #approvals digest (receives QA_PASSED only)
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
