# Org Chart — Nexa Operations HQ · The Team

Single source of truth for the team: **8 agents, 1 manager, 3 departments.**
This mirrors the live "NEXA OPERATIONS HQ — The Team" dashboard. When a role
changes, edit this file first. (The `agent_activity_log` *function labels* —
bq_refresh, health_monitor, performance_audit, etc. — are how work is **logged**,
not who the team **is**. Don't confuse the two.)

```
                        ┌──────────────────────────┐
                        │      AI ORCHESTRATOR      │  Manager · all 3 depts
                        │  8-step loop daily 08:00  │  receives QA_PASSED only,
                        │  Riyadh · gates writes ✅ │  queues #approvals,
                        └─────────────┬────────────┘  manages all handoffs
          ┌───────────────────────────┼───────────────────────────┐
          ▼                            ▼                            ▼
 ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
 │ DEPT 1: PERF.     │        │ DEPT 2: CRO / LP │        │ DEPT 3: SUPPORT  │
 │ STRATEGIC:        │        │ (sequential)     │        │ serve both depts │
 │  performance-lead │        │                  │        │ NO internal      │
 ├──────────────────┤        │ cro-specialist   │        │ handoff          │
 │ campaign-manager │        │  (brief+design)  ├────────┤                  │
 │      ∥           │        │       │ →         │        │ project-coordinator    │
 │ creative-        │        │ developer        │        │      ∥           │
 │   strategist     │        │                  │        │ growth-analyst   │
 └──────────────────┘        └──────────────────┘        └──────────────────┘
   (parallel directs)         (direct handoff chain)        (parallel, independent)
```

## Manager
**`ai-orchestrator`** — runs the 8-step loop daily 08:00 Riyadh. Receives QA_PASSED
reports from all departments via qa-auditor, queues every write decision into ONE
#approvals digest, **gates every write action on the ✅ reaction**, and manages all
cross-department handoffs. Does not execute work. Does not re-validate — that is QA Auditor's job.

## Dept 1 — Performance
| Agent | Owns |
|---|---|
| **performance-lead** *(strategic lead only)* | Budget reallocation across channels, new channel launch or sunset decisions, KPI threshold changes in `config.py`, weekly channel mix review. NOT in the daily KPI flag path. |
| **campaign-manager** | KPI flag response (receives directly from project-coordinator); 12-field naming spec on every build; both Meta pixels; keyword policy buckets; audience configuration. Never executes without ✅. |
| **creative-strategist** | OCEAN persona mapping for all copy/creative; scopes A/B variants per audience segment per channel; aligns LP assets with cro-specialist before any test goes live. |

`campaign-manager` and `creative-strategist` work **in parallel — no handoff between them.**
KPI flags: `project-coordinator` → `campaign-manager` DIRECTLY (performance-lead is not in this path).

## Dept 2 — CRO / Landing Page · sequential chain (2 steps)
| Agent | Owns |
|---|---|
| **cro-specialist** *(chain lead — brief + design)* | 8-section LP brief + test hypothesis; OCEAN-aligned design spec (annotated, ZATCA badge above fold, interaction notes for developer); success criteria from 14-day CPQL + destination_url; owns test-result decisions; weekly pixel health audit across ALL active LPs. Hands one combined brief+design package to developer. |
| **developer** | Builds variant from cro-specialist's package; UTM passthrough on every form field; wires both pixel fires; deploys to production; verifies pixel fires in Events Manager before sign-off. |

Direct handoff: **cro-specialist (brief+design) → developer**, result back to cro-specialist.

## Dept 3 — Support · serve both depts above, NO internal handoff
| Agent | Owns |
|---|---|
| **project-coordinator** *(OPS)* | Task routing (KPI flags → campaign-manager directly); UTM structure policy; pixel health; HubSpot lead_utm_campaign field mapping; Railway env vars + credential rotation; GTM containers. Sunday infra hygiene scan (env var audit + collector manifest). Fires #nexa-health on RED only. |
| **growth-analyst** *(DATA)* | Owns `memory/` (writes 08_pitfalls.md on every API trap, updates 14_learning_patterns.md after every outcome). 8-step loop on live BQ, period comparisons, CRO A/B results, monthly forecasts. Sunday proactive hygiene scan (BQ dedup, BQ↔HubSpot reconciliation, memory freshness, 7d/14d outcome monitoring). Never reports without live BQ. |

`project-coordinator` and `growth-analyst` run **in parallel — no internal handoff.**

## Parallel vs sequential, at a glance
- **Parallel:** campaign-manager ∥ creative-strategist · project-coordinator ∥ growth-analyst.
- **Sequential (direct handoff):** cro-specialist (brief + design) → developer (one package — no intermediate UI/UX step).
- **Cross-dept coordination:** creative-strategist ↔ cro-specialist (pre-launch LP alignment).
- **Manager:** ai-orchestrator gates all writes, owns all cross-dept handoffs, does NOT re-validate (QA Auditor owns that).
