# Agent Roles — What Lives Here vs Elsewhere

> **Canonical roster is now `docs/_shared/org-chart.md`.** As of 2026-06-08 the
> team is **15 separate Claude Code subagents** in `.claude/agents/`, across 3
> departments (Performance Marketing, Growth Marketing, Marketing Operations),
> each with its own playbook (`docs/playbooks/<dept>/<role>.md`) and private
> memory (`memory/agents/<dept>/<role>/`). This file is kept as a quick map; the
> org-chart is the source of truth.

## Two layers — don't confuse them
- **Dev-time subagents** (`.claude/agents/*.md`) — the team you and Claude work
  with in Claude Code. Isolated context per role → less hallucination. This is
  the new structure.
- **Production runtime** (`claude/roles.py` + `claude/manager.py`) — the
  autonomous Railway product; makes one Anthropic API call per role at cadence.
  Still live, untouched by the subagent revamp. Phase 2 will point it at the
  same playbooks so there's one source of truth.

## In this repo (the 3 departments)

| Dept | Manager | Roles |
|---|---|---|
| **Performance Marketing** | `performance-lead` | media-buyer · paid-media-analyst · paid-media-strategist · data-engineer · connector-police · cro-paid-specialist · keyword-strategist |
| **Growth Marketing** | `growth-lead` | growth-strategist · market-expansion-analyst |
| **Marketing Operations** | `ops-manager` | ops-reporter · approval-coordinator |
| _routing above all_ | `cmo-orchestrator` | — |

### Legacy persona files (superseded)
The old `md_files/qoyod-*.md` personas (paid-media, analyst, strategist, daily-report,
creative, hubspot-cro, manager-os) are the **runtime's** prompt sources, loaded by
`claude/roles.py`. They are NOT the dev-time agents. Don't edit them to change a
subagent — edit `.claude/agents/` + `docs/playbooks/`.

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
