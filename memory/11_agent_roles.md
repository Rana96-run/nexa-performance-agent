# Agent Roles — What Lives Here vs Elsewhere

## In this repo (3 roles)

| Role | File | Job |
|---|---|---|
| **Paid Media** | `md_files/qoyod-paid-media-agent.md` | Propose pause/scale/budget/bid changes; execute on Slack ✅ |
| **Analyst / Strategist** | `md_files/qoyod-analyst-agent.md` | Continuous + periodic analysis — LPs, bounce, traffic, converters, ads behavior, **scaling signals**, **lead-quality monitoring** |
| **Project Manager** | `md_files/qoyod-task-flow.md` | Classifies signals → routes → tasks → chases → closes |

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
