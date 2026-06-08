# Agents — The Marketing Team (index + how to use)

This folder holds the **real Claude Code subagents**. Each `*.md` here (except
`README.md` and `_TEMPLATE.md`) is one teammate with its own isolated context,
its own playbook, and its own memory. Splitting roles this way is what stops the
"one giant agent talking to itself" problem and cuts hallucination — each agent
loads only its own small context, not the whole repo.

## How to talk to a teammate
Say it in plain language and name the seat:
- *"Ask the **media-buyer** to draft a scale plan for Meta_LeadGen_AR_Invoice_Interests."*
- *"Have the **paid-media-analyst** explain why CPQL jumped on Google last week."*
- *"**cmo-orchestrator**: leads are down this month — who should look at it?"*

When you name a seat, that single subagent runs in its own context and answers
**as that role.** When you're not sure who, ask the **cmo-orchestrator** — it
routes to the right department and role.

## The roster

| Agent | Dept | Role |
|---|---|---|
| `cmo-orchestrator` | — | Top manager / router. Receives any request, routes to a dept. |
| `performance-lead` | Performance | Dept manager — owns the daily cycle + #approvals digest. |
| `media-buyer` | Performance | Pause/scale/budget/bid, cloning, audiences. Executes after ✅. |
| `paid-media-analyst` | Performance | Period comparison, anomaly attribution, lead quality. |
| `paid-media-strategist` | Performance | Channel mix, scale plans, quarterly bets. |
| `data-engineer` | Performance | BQ schema, collectors, views, backfills. |
| `connector-police` | Performance | Connector health + data freshness gate. |
| `cro-paid-specialist` | Performance | LP audit/specs, CPQL→LP loop. |
| `keyword-strategist` | Performance | Google Ads keyword policy engine. |
| `growth-lead` | Growth | Dept manager — weekly brief + budget/channel directive. |
| `growth-strategist` | Growth | SOSTAC-X planning, roadmap, audience/creative direction. |
| `market-expansion-analyst` | Growth | New channel/city/sector/product test proposals. |
| `ops-manager` | Ops | Dept manager — leadership reports + escalations. |
| `ops-reporter` | Ops | Builds report tables from handoffs; flags stale data. |
| `approval-coordinator` | Ops | Tracks #approvals; logs 7d/14d outcomes. |

## The map (read these to understand the team)
- `../../docs/_shared/org-chart.md` — who exists, who manages whom, who owns what
- `../../docs/_shared/handoff-protocol.md` — how work passes between seats
- `../../docs/_shared/communication-rules.md` — how the team behaves
- `../../docs/playbooks/_index.md` — every agent's playbook
- `../../memory/agents/` — per-agent memory (feedback + learnings)

## Adding / renaming a role
Copy `_TEMPLATE.md`, then create the matching playbook and memory folder, then
update `org-chart.md` and this table. Keep each agent file small — that is the
whole point.

## Relationship to the production runtime
These subagents are **dev-time** — they help you (and Claude) work on the repo.
The autonomous Railway product still runs through `claude/roles.py` +
`claude/manager.py`. The two are kept in sync by pointing both at the same
playbooks (a later phase). Editing an agent here does NOT change Railway.
