---
name: _readme
description: NOT AN AGENT. Index and activation guide for the 3-layer team.
---

# Nexa Agent Team — 3-Layer Hierarchy

## Architecture

```
Layer 1   AI Orchestrator
              ↕ only
Layer 2a  Project Coordinator          Layer 2b  QA Auditor
          (routing + OPS)                       (output validation)
                ↓ routes                              ↑ validates all
Layer 3   ┌─────────────────────────────────────────────────┐
          │  Growth Analyst                                 │
          │    └─ triggers → CRO Specialist               │
          │                    └─ Developer                │
          ├─────────────────────────────────────────────────┤
          │  Performance Lead (strategic only)              │
          │  Campaign Manager (KPI flags, optimization)     │
          │  Creative Strategist (copy + creative)          │
          └─────────────────────────────────────────────────┘
```

## Agent roster

| Agent | Layer | Receives from | Sends to |
|---|---|---|---|
| ai-orchestrator | 1 | Human, any agent escalating | project-coordinator, qa-auditor |
| qa-auditor | 2 | Any Layer 3 agent output, hygiene scan reports | Orchestrator (QA_PASSED), originating agent (QA_FAILED) |
| project-coordinator | 2 | Orchestrator, Layer 3 status | Orchestrator, Layer 3 agents (campaign-manager for KPI flags directly) |
| growth-analyst | 3 | project-coordinator | qa-auditor, cro-specialist |
| performance-lead | 3 | orchestrator (strategic cases only) | campaign-manager, creative-strategist, qa-auditor |
| campaign-manager | 3 | project-coordinator (KPI flags direct), performance-lead (strategic follow-through) | qa-auditor, performance-lead (sales escalation) |
| creative-strategist | 3 | project-coordinator | qa-auditor, cro-specialist (LP asset alignment) |
| cro-specialist | 3 | growth-analyst, creative-strategist, orchestrator | developer (brief+design package), qa-auditor, orchestrator (test results) |
| developer | 3 | cro-specialist (brief+design package) | qa-auditor, cro-specialist (sign-off) |

## Communication rules (non-negotiable)
1. Orchestrator talks ONLY to project-coordinator and qa-auditor
2. Every Layer 3 output goes through qa-auditor BEFORE reaching Orchestrator
3. Orchestrator receives QA_PASSED output only — does NOT re-validate
4. project-coordinator is the task router — no Layer 3 agent self-assigns
5. QA Auditor never fixes — returns QA_FAILED to originating agent
6. CRO chain is now 2 steps: cro-specialist (brief + design) → developer. No separate UI/UX step.
7. KPI flags go project-coordinator → campaign-manager DIRECTLY. Performance Lead is NOT in this path.
8. Performance Lead is reserved for 4 strategic cases: budget reallocation, channel launch/sunset, KPI threshold change, weekly channel mix review.

## Activation

Dispatch agents via the `Agent` tool with `subagent_type`:
- `ai-orchestrator` — for routing, daily loop, cross-dept decisions
- `qa-auditor` — to validate any agent output before it reaches Orchestrator
- `project-coordinator` — for OPS, task routing, UTM/pixel/connector issues, KPI flag dispatch
- `growth-analyst` — for BQ analysis, period comparisons, LP data pull, Sunday hygiene scan
- `performance-lead` — for budget reallocation, channel launch/sunset, KPI threshold changes, weekly channel mix review
- `campaign-manager` — for KPI flag response, campaign optimization, scaling, keyword audit
- `creative-strategist` — for creative briefs, OCEAN mapping, copy direction
- `cro-specialist` — for LP brief + design spec, qual ratio analysis, test decisions
- `developer` — for LP build, deploy, pixel verification

## Golden rules
- No write action without ✅ from human in #approvals
- Minimum 14 days of data before pause/scale decisions
- QA Auditor validates before Orchestrator decides — Orchestrator does not re-validate
- HubSpot is read-only (no PATCH/DELETE/POST without Amar's Slack sign-off)
- Spend always reported in USD
- CPQL ≤ $60 = scale territory
- ROAS < 1x on a channel → check qual/CPQL/volume before reallocation
