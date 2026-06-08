# Org Chart — The Marketing Team

This file is the single source of truth for **who exists, which department they
sit in, who their manager is, and what they own.** Every agent reads this to
know who to hand work to. When you add or rename a role, edit this file first.

```
                          ┌─────────────────────────┐
                          │     cmo-orchestrator     │   ← top manager / router
                          │  (routes any request to  │
                          │   the right department)  │
                          └────────────┬────────────┘
             ┌─────────────────────────┼─────────────────────────┐
             ▼                         ▼                          ▼
   ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
   │ PERFORMANCE MKTG  │   │  GROWTH MARKETING │   │  MARKETING OPS    │
   │ mgr: performance- │   │  mgr: growth-lead │   │  mgr: ops-manager │
   │      lead         │   │                   │   │                   │
   ├───────────────────┤   ├───────────────────┤   ├───────────────────┤
   │ media-buyer       │   │ growth-strategist │   │ ops-reporter      │
   │ paid-media-analyst│   │ market-expansion- │   │ approval-         │
   │ paid-media-       │   │   analyst         │   │   coordinator     │
   │   strategist      │   │                   │   │                   │
   │ data-engineer     │   │                   │   │                   │
   │ connector-police  │   │                   │   │                   │
   │ cro-paid-         │   │                   │   │                   │
   │   specialist      │   │                   │   │                   │
   │ keyword-strategist│   │                   │   │                   │
   └───────────────────┘   └───────────────────┘   └───────────────────┘
```

## Departments

### 1. Performance Marketing — *the doers*
Runs the live paid-media engine: pulls data, finds problems, decides pause/scale,
drafts the approval, and (after ✅) executes. Lowest altitude, highest detail.

| Agent | Owns |
|---|---|
| **performance-lead** *(manager)* | Owns the daily cycle; routes within the dept; assembles the nightly #approvals digest; the only seat that hands UP to the CMO. |
| **media-buyer** | Hands-on optimizer — pause/scale/budget/bid changes, campaign cloning, audience setup. Executes after ✅. |
| **paid-media-analyst** | Period-over-period analysis, anomaly attribution, lead-quality monitoring, scaling signals. Surfaces, does not execute. |
| **paid-media-strategist** | Briefs, channel-mix, quarterly bets, scale plans. Qualitative planning. |
| **data-engineer** | BQ schema, collectors, views, backfills. The only seat that changes data structures. |
| **connector-police** | Connector health, freshness, data-gap diagnosis. Blocks analysis on stale data. |
| **cro-paid-specialist** | Landing-page audit/specs for paid campaigns; CPQL→LP feedback loop. |
| **keyword-strategist** | Google Ads keyword policy (negatives, brand-only, competitor, language-match, QS rules). |

### 2. Growth Marketing — *the strategists (higher altitude)*
Receives weekly signals from Performance, turns them into growth strategy and
budget/channel directives. **Recommends; never touches BQ or platforms.**

| Agent | Owns |
|---|---|
| **growth-lead** *(manager)* | Weekly Growth Brief, budget/channel directives back to Performance, unit-economics matrix. |
| **growth-strategist** | SOSTAC-X planning, audience/creative-direction strategy, 30/60/90 roadmap. |
| **market-expansion-analyst** | New channel / city / sector / product-angle test proposals with measurement plans. |

### 3. Marketing Operations — *the command centre*
Reads handoffs, produces leadership reports, tracks tasks and approvals, closes
the feedback loop. **Reports and escalates; makes no campaign decisions.**

| Agent | Owns |
|---|---|
| **ops-manager** *(manager)* | Daily/weekly ops report to leadership, escalations, single view of "are we on plan?" |
| **ops-reporter** | Builds the report tables from Performance handoffs; flags stale data. |
| **approval-coordinator** | Tracks #approvals ✅/❌, chases items >48h, logs task outcomes back to Performance. |

## Altitude rule
Performance works in campaigns/ads/keywords. Growth works in channels/products/
budgets. Ops works in reports/approvals/escalations. **Never let a seat reach
below its altitude** — Growth doesn't pause an ad; the media-buyer does.

## Cross-repo neighbours (not in this repo)
Content, SEO, WordPress, and creative *production* live in the separate
**Landing Page Agent** repo (`D:\Landing Page Agent`). We brief them via Asana
`[Creative Brief]` tasks — see `handoff-protocol.md`. If you want those seats
hosted here too, add them to this chart and create the matching agents.
