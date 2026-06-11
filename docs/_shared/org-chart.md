# Org Chart — Nexa Operations HQ · The Team

Single source of truth for the team: **9 agents, 1 manager, 3 departments.**
This mirrors the live "NEXA OPERATIONS HQ — The Team" dashboard. When a role
changes, edit this file first. (The `agent_activity_log` *function labels* —
bq_refresh, health_monitor, performance_audit, etc. — are how work is **logged**,
not who the team **is**. Don't confuse the two.)

```
                        ┌──────────────────────────┐
                        │      AI ORCHESTRATOR      │  Manager · all 3 depts
                        │  8-step loop daily 08:00  │  receives all reports,
                        │  Riyadh · gates writes ✅ │  queues #approvals,
                        └─────────────┬────────────┘  manages all handoffs
          ┌───────────────────────────┼───────────────────────────┐
          ▼                            ▼                            ▼
 ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
 │ DEPT 1: PERF.     │        │ DEPT 2: CRO / LP │        │ DEPT 3: SUPPORT  │
 │ LEAD:             │        │ (sequential)     │        │ serve both depts │
 │  performance-lead │        │                  │        │ NO internal      │
 ├──────────────────┤        │ cro-specialist   │        │ handoff          │
 │ campaign-manager │        │       │ →         ├────────┤                  │
 │      ∥           │        │ ui-ux-designer   │        │ project-coordinator    │
 │ creative-        │        │       │ →         │        │      ∥           │
 │   strategist     │        │ developer        │        │ growth-analyst   │
 └──────────────────┘        └──────────────────┘        └──────────────────┘
   (parallel directs)         (direct handoff chain)        (parallel, independent)
```

## Manager
**`ai-orchestrator`** — runs the 8-step loop daily 08:00 Riyadh. Receives reports
from all departments, queues every write decision into ONE #approvals digest,
**gates every write action on the ✅ reaction**, and manages all cross-department
handoffs. Does not execute work.

## Dept 1 — Performance · LEAD `performance-lead`
| Agent | Owns |
|---|---|
| **performance-lead** *(lead)* | KPI thresholds in `config.py` (CPQL/CPL zones), 14-day minimum window, channel mix + budget allocation. Reacts to #approvals with ✅/❌ — all writes gated on it. No launches without sign-off. |
| **campaign-manager** | 12-field naming spec on every build; both Meta pixels (CRM 1782671302631317 + Web 3036579196577051); keyword policy buckets (ALWAYS_NEGATIVE / BRAND_ONLY / COMPETITOR); audience Interests/Lookalike (Prospecting→ValueError). Never executes without ✅. |
| **creative-strategist** | OCEAN persona mapping for all copy/creative; scopes A/B variants per audience segment per channel; aligns LP assets with cro-specialist before any test goes live. |

`campaign-manager` and `creative-strategist` work **in parallel — no handoff between them.**

## Dept 2 — CRO / Landing Page · sequential chain
| Agent | Owns |
|---|---|
| **cro-specialist** *(chain lead)* | 8-section LP brief template + test hypothesis; success criteria from 14-day CPQL + destination_url; ZATCA badge above fold (non-negotiable); coordinates UI/UX + Developer; owns test-result decisions. |
| **ui-ux-designer** | LP variant design aligned to OCEAN; ZATCA badge above fold (mandatory); annotated design + interaction notes for Developer. Shared product resource. |
| **developer** | Builds variant; UTM passthrough on every form field; wires both pixel fires; deploys to production; verifies pixel fires in Events Manager before sign-off. Shared product resource. |

Direct handoff: **cro-specialist → ui-ux-designer → developer**, result back to cro-specialist.

## Dept 3 — Support · serve both depts above, NO internal handoff
| Agent | Owns |
|---|---|
| **project-coordinator** *(Project Coordinator — OPS)* | UTM structure policy; pixel health (both Meta pixels); HubSpot lead_utm_campaign field mapping; Railway env vars + credential rotation (single source of truth for secrets). GTM containers (web + server). Fires #nexa-health on RED only, never all-clears. |
| **growth-analyst** *(DATA)* | Owns `memory/` (writes 08_pitfalls.md on every API trap, updates 14_learning_patterns.md after every outcome). One analyst for everything: 8-step loop on live BQ, period comparisons, CRO A/B results, monthly forecasts (forecaster.py). Never reports without live BQ. |

`project-coordinator` and `growth-analyst` run **in parallel — no internal handoff.**

## Parallel vs sequential, at a glance
- **Parallel:** campaign-manager ∥ creative-strategist · project-coordinator ∥ growth-analyst.
- **Sequential (direct handoff):** cro-specialist → ui-ux-designer → developer.
- **Cross-dept coordination:** creative-strategist ↔ cro-specialist (pre-launch LP alignment).
- **Manager:** ai-orchestrator gates all writes and owns all cross-dept handoffs.
