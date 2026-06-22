# Generic System Reference — Nexa Operations HQ

The one document that explains the **whole system**: what it is, why it exists,
how it works, what it contains, what it fixes, and how it was built. Read this to
understand the system end-to-end. For navigation use [`INDEX.md`](INDEX.md); for
how the manager runs day-to-day use [`../CLAUDE.manager.md`](../CLAUDE.manager.md).

---

## 1. What it is
A **team of 10 AI agents** that runs Qoyod's paid-media + landing-page operation.
One manager (`ai-orchestrator`) over **3 departments** — Performance, CRO/Landing
Page, and Support — plus a cross-cutting QA Auditor. Each agent is a real Claude
Code subagent with its own isolated context, playbook, and memory. It mirrors the
live "NEXA OPERATIONS HQ — The Team" org chart.

## 2. Why we need it (the problem it solves)
Before, everything ran as **one giant agent** carrying all context at once — which
caused **hallucination** (too much in one window), made files **impossible to
find**, and meant the agent was effectively "talking to itself." Splitting into 9
role-scoped agents gives each one a **small, focused context** (its own playbook +
memory), so it reasons reliably and you can "talk to a teammate" instead of one
overloaded brain.

## 3. How it works (architecture — a tree)
**Root → departments → role leaves.**
- **Root (full scope):** the main session, governed by `CLAUDE.md` + `CLAUDE.manager.md`.
- **Manager:** `ai-orchestrator` — runs the daily 8-step loop (08:00 Riyadh),
  routes every request, gates **every write on the human ✅**, owns all handoffs.
- **Dept 1 — Performance** (LEAD `performance-lead`): `campaign-manager` ∥ `creative-strategist` (parallel).
- **Dept 2 — CRO / Landing Page** (sequential): `cro-specialist` (brief + design) → `developer`.
- **Dept 3 — Support** (parallel, serve both): `project-coordinator` ∥ `growth-analyst` (owns memory/).

**Flow:** observe live BQ → compare period-over-period → investigate → decide with
full setup → **execute only after ✅** → monitor 7d/14d → learn → forecast.
**Handoffs** use the packet in `_shared/handoff-protocol.md`; any agent can be
linked to any other (default flow is structured; the orchestrator can wire any pair).

## 4. What it contains (the file map)
| Area | Path | Holds |
|---|---|---|
| Agents | `.claude/agents/*.md` | the 8 subagents + `_TEMPLATE` + `_archived/` |
| Manager OS | `CLAUDE.manager.md` | how `ai-orchestrator` runs the team |
| Shared playbook | `docs/playbooks/_shared.md` | shared data + activities every role reads |
| Per-role playbooks | `docs/playbooks/<dept>/<role>.md` | each seat's procedure |
| Shared docs | `docs/_shared/` | org-chart, handoff-protocol, communication-rules, how-to |
| Shared memory | `memory/*.md` + `memory/knowledge_base/` | architecture, BQ, pitfalls, learnings, KPI rules, reference guides |
| Per-role memory | `memory/agents/<dept>/<role>/` | each seat's feedback / learnings / critical |
| CRO workspace | `docs/landing-pages/` | briefs → designs → specs + LP reference (snapshot of `D:\Landing Page Agent`) |
| Creative reference | `docs/creative/reference/` | design knowledge (snapshot of `D:\Design Agent`) |
| Indexes | `docs/INDEX.md` (master) + `playbooks/_index.md` + `memory/00_index.md` | navigation |
| n8n workflows | 7 workflows in n8n Cloud — see `memory/05_scheduler.md` | all scheduling, analysis, Slack, Asana |
| GitHub Actions | `.github/workflows/collectors.yml` | Python BQ collector cadence (every 6h) |

## 5. What it fixes / what it can solve
- **Hallucination** → isolated per-role context (each agent loads only its files).
- **Scattered knowledge** → consolidated: one shared layer + one per-role layer for
  memory, playbooks, and indexes.
- **"Which roles exist?" confusion** → the org chart is the single roster (8 agents),
  not the 13 `agent_activity_log` log-labels.
- **Lost learnings** → `growth-analyst` owns `memory/`; every trap → `08_pitfalls.md`,
  every outcome → `14_learning_patterns.md`.
- **Unsafe writes** → the single ✅ approval gate; nothing scales/pauses/launches without it.
- **Day-to-day paid-media work** → CPQL/CPL health, pause/scale, keyword policy,
  LP tests, tracking/pixels, forecasts — each owned by a clear seat.

## 6. What it has (capabilities, by seat)
Budget/channel strategy + KPI thresholds (`performance-lead`) · campaign build, naming,
pixels, keyword policy, KPI flag response (`campaign-manager`) · persona/creative direction +
A/B (`creative-strategist`) · LP test brief+design+build+verify (`cro-specialist` → `developer`) ·
UTM/pixel/secrets + Sunday infra hygiene (`project-coordinator`) · live-BQ
analysis, period-compare, forecasts, memory ownership, Sunday data hygiene (`growth-analyst`) ·
routing + the daily loop + the gate, QA_PASSED only (`ai-orchestrator`).

## 7. How we built it
1. Read the live org chart (the dashboard) → the team is **8 agents** (as of 2026-06-22 restructure), not the
   15 I first invented nor the 13 activity-log labels.
2. Built each as a Claude Code subagent (`.claude/agents/`) with tight identity +
   tools + model; gave each a playbook (`docs/playbooks/`) and memory (`memory/agents/`).
3. Added the shared layer: org-chart, handoff-protocol, communication-rules, the
   shared playbook, the master index, the Manager OS, and this overview.
4. Pulled reusable knowledge in: LP knowledge → `docs/landing-pages/reference/`,
   design knowledge → `docs/creative/reference/`.
5. Verified the memory read/write loop end-to-end on real agents; cleaned scratch
   files; hardened `.gitignore` (secrets, node_modules).
6. Migrated from Railway monolith → n8n Cloud (7 workflows) + GitHub Actions (14 collectors). Railway deprecated 2026-06-16. See `memory/05_scheduler.md` for the full workflow inventory and `memory/11_agent_roles.md` for the 3-taxonomy map.

## 8. Three layers (don't confuse them)
- **Dev-time** (this system): the 10 subagents you work with in Claude Code.
- **n8n Cloud**: 7 workflows that own all scheduling, analysis, Slack posts, Asana tasks, and approval gates. These run autonomously on a cron. See `memory/05_scheduler.md` for the full workflow inventory.
- **GitHub Actions**: Python BQ collectors only (`collectors/*.py`). Runs every 6h. No analysis, no Slack. See `.github/workflows/collectors.yml`.
- **Railway**: DEPRECATED (2026-06-16). Pending shutdown. No schedulers or analysis run there anymore.

## 9. How to use it
Name a seat (*"ask the `growth-analyst` to…"*) or let `ai-orchestrator` route. New
agents need a `/agents` reload to dispatch by name. Full how-to:
`docs/_shared/how-to-use-the-team.md`.
