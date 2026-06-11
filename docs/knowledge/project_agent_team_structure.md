---
name: project-agent-team-structure
description: "The team is 9 Claude Code subagents (1 manager + 3 depts) matching the live \"Nexa Operations HQ — The Team\" dashboard; NOT the 13 agent_activity_log labels"
metadata: 
  node_type: memory
  type: project
  originSessionId: 65bd8805-d45b-4ce6-bf9e-a7a6627b67c1
---

The Nexa team is **9 agents**, matching the live "NEXA OPERATIONS HQ — The Team"
dashboard (the authoritative org chart). Built as Claude Code subagents 2026-06-08.

**Manager:** `ai-orchestrator` — 8-step loop daily 08:00 Riyadh, gates every write
on the #approvals ✅, owns all cross-dept handoffs.

**Dept 1 — Performance** (LEAD `performance-lead`): `campaign-manager` ∥
`creative-strategist` (the two directs run in PARALLEL).

**Dept 2 — CRO / Landing Page** (sequential): `cro-specialist` → `ui-ux-designer`
→ `developer`.

**Dept 3 — Support** (serve both depts, NO internal handoff, parallel):
`project-coordinator` (UTM/pixel/secrets) ∥ `growth-analyst` (owns memory/, 8-step loop
on live BQ, forecasts).

**Critical trap:** do NOT build agents from `agent_activity_log` — its 13 `role`
values are LOGGING labels (infra: health_monitor/bq_refresh/collector/ops_scheduler;
human: user; function buckets: performance_audit/keyword_management/task_creator/
daily_digest/campaign_creator/llm_cadence/paid_media_strategist), not the team. I
made that mistake once (built 15 wrong paid-media seats, then read the log table and
got 13). The org chart is the only roster source.

**Layout:** agents `.claude/agents/*.md` · playbooks `docs/playbooks/<dept>/<role>.md`
· per-agent memory `memory/agents/<dept>/<role>/` · shared docs `docs/_shared/`
(org-chart, handoff-protocol, communication-rules). Flat `memory/NN_*.md` = shared
org memory (runtime + CLAUDE.md reference exact paths; don't move). `.claude/agents/`
allowlisted in .gitignore. Production runtime `claude/roles.py` is a separate,
untouched layer. New subagents dispatchable by name after a Claude Code reload.

**Why this matters:** the whole revamp was triggered because the org chart was
never in memory, so I kept asking the user for it. Now it is — read here first.
