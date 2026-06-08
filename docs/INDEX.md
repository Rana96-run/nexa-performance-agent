# MASTER INDEX — Nexa Operations HQ

The one front door to the whole system. Everything below is either **shared
(one-for-all)** or **per-role**. Start at the top; drill into a role as needed.

## 0. Read-first (shared rules)
- `../CLAUDE.md` — project non-negotiables (always win)
- `../CLAUDE.manager.md` — Manager OS: the 8-step loop, routing, the ✅ gate
- `memory/CRITICAL_KPI_RULES.md` — KPI rules (hook-enforced)

## 1. The team (agents)
- `../.claude/agents/README.md` — roster + how to dispatch
- `_shared/org-chart.md` — who/what, departments, parallel vs sequential
- `_shared/how-to-use-the-team.md` — how to talk to each agent (example asks)

## 2. Playbooks
- **Shared (one for all):** `playbooks/_shared.md` — shared data + activities every role uses
- **Index:** `playbooks/_index.md`
- **Per role:** `playbooks/performance/*` · `playbooks/cro/*` · `playbooks/support/*` · `playbooks/ai-orchestrator.md`

## 3. Memory
- **Shared (one for all):** `../memory/00_index.md` (master) · `../memory/NN_*.md` (topical) · `../memory/CRITICAL_KPI_RULES.md` · `../memory/knowledge_base/` (reference guides)
- **Per role:** `../memory/agents/<dept>/<role>/MEMORY.md` (see `../memory/agents/README.md`)

## 4. How the team works together
- `_shared/handoff-protocol.md` — handoff packet, who→whom, parallel vs sequential
- `_shared/communication-rules.md` — behaviour rules

## 5. CRO / Landing Page workspace
- `landing-pages/README.md` — briefs → designs → specs flow
- `landing-pages/reference/` — LP knowledge (design system, brand, prompts; snapshot of `D:\Landing Page Agent\`)
- `landing-pages/_templates/` — 8-section brief + ZATCA/pixel/UTM checklist

## 6. Layers & taxonomies (avoid confusion)
- `../memory/11_agent_roles.md` — the 9-agent team vs the runtime LLM roles vs the
  13 activity-log labels, and how they map. **The team is 9 agents.**

## Quick map: shared vs per-role
| Layer | One-for-all (shared) | One-per-role |
|---|---|---|
| Memory | `memory/` + `00_index.md` + `knowledge_base/` | `memory/agents/<dept>/<role>/` |
| Playbook | `playbooks/_shared.md` | `playbooks/<dept>/<role>.md` |
| Index | **this file** + `playbooks/_index.md` + `memory/00_index.md` | each role's `MEMORY.md` header |
