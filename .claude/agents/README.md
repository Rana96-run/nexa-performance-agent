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
          │                    └─ UI/UX Designer           │
          │                          └─ Developer          │
          ├─────────────────────────────────────────────────┤
          │  Performance Lead                               │
          │    ├─ Campaign Manager                         │
          │    └─ Creative Strategist                      │
          └─────────────────────────────────────────────────┘
```

## Agent roster

| Agent | Layer | Receives from | Sends to |
|---|---|---|---|
| ai-orchestrator | 1 | Human, any agent escalating | project-coordinator, qa-auditor |
| qa-auditor | 2 | Any Layer 3 agent output | Orchestrator (QA_PASSED), originating agent (QA_FAILED) |
| project-coordinator | 2 | Orchestrator, Layer 3 status | Orchestrator, Layer 3 agents |
| growth-analyst | 3 | project-coordinator | qa-auditor, cro-specialist |
| performance-lead | 3 | project-coordinator | campaign-manager, creative-strategist, qa-auditor |
| campaign-manager | 3 | performance-lead | qa-auditor, performance-lead (escalation) |
| creative-strategist | 3 | performance-lead | qa-auditor, cro-specialist (LP asset alignment) |
| cro-specialist | 3 | growth-analyst, performance-lead | ui-ux-designer, qa-auditor |
| ui-ux-designer | 3 | cro-specialist | developer, qa-auditor |
| developer | 3 | ui-ux-designer | qa-auditor, cro-specialist (sign-off) |

## Communication rules (non-negotiable)
1. Orchestrator talks ONLY to project-coordinator and qa-auditor
2. Every Layer 3 output goes through qa-auditor BEFORE reaching Orchestrator
3. project-coordinator is the task router — no Layer 3 agent self-assigns
4. QA Auditor never fixes — returns QA_FAILED to originating agent
5. CRO chain is strict: cro → ui-ux → developer. No skipping links.
6. Performance Lead must be the single point receiving performance flags — never bypass to campaign-manager directly

## Activation

Dispatch agents via the `Agent` tool with `subagent_type`:
- `ai-orchestrator` — for routing, daily loop, cross-dept decisions
- `qa-auditor` — to validate any agent output before it reaches Orchestrator
- `project-coordinator` — for OPS, task routing, UTM/pixel/connector issues
- `growth-analyst` — for BQ analysis, period comparisons, LP data pull
- `performance-lead` — for KPI threshold decisions, triage
- `campaign-manager` — for campaign optimization, scaling, keyword audit
- `creative-strategist` — for creative briefs, OCEAN mapping, copy direction
- `cro-specialist` — for LP briefs, qual ratio analysis, test decisions
- `ui-ux-designer` — for LP design from brief
- `developer` — for LP build, deploy, pixel verification

## Golden rules
- No write action without ✅ from human in #approvals
- Minimum 14 days of data before pause/scale decisions
- QA Auditor validates before Orchestrator decides
- HubSpot is read-only (no PATCH/DELETE/POST without Amar's Slack sign-off)
- Spend always reported in USD
- CPQL ≤ $60 = scale territory
- ROAS < 1x on a channel → check qual/CPQL/volume before reallocation
