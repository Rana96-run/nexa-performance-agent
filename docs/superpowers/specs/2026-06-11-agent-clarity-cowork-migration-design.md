# Design Spec — Agent Clarity, Workflow Redesign & Cowork Migration
**Date:** 2026-06-11
**Status:** Pending implementation approval

---

## What this spec covers

1. A standard definition format for all 9 agents (scope, skills, trust, memory, handoffs)
2. Per-agent memory architecture alongside shared memory
3. Hybrid handoff model — direct peer handoffs + orchestrator reporting
4. Activity dashboard redesign focused on performance marketing
5. Cowork migration with n8n as the data/action layer

---

## Section 1 — Agent Definition Standard

Every agent file (`.claude/agents/<name>.md`) is rewritten to include 7 mandatory fields. The existing content (boot sequence, hard rules, efficiency rules, done means) is preserved and enriched — nothing is removed.

### The 7-field standard

```
scope       — what this agent owns + explicit "does NOT own" list
skills      — specific capabilities, each tagged with a trust tier
memory      — READ list (shared files) + WRITE path (private folder)
trust       — three-tier table per skill
receives    — who hands tasks to this agent
hands-to    — who this agent hands to directly (no orchestrator needed)
reports-to  — always ai-orchestrator (outcome + queued write actions)
```

### Trust tiers

| Tier | Meaning | Requires |
|---|---|---|
| **Auto** | Executes without approval | Nothing — agent does it immediately |
| **Lead-gated** | Needs department lead sign-off | performance-lead or cro-specialist approval |
| **Human-gated** | Needs ✅ in #approvals | Human reaction in Slack before execution |

### File template

```markdown
---
name: <agent-name>
description: <one line — when to dispatch this agent>
tools: <comma-separated>
model: opus | sonnet
---

## Scope
**Owns:** <1-3 lines — what this agent is responsible for>
**Does NOT own:** <explicit list — prevents role bleed>

## Boot sequence
1. <first file — always CRITICAL_KPI_RULES.md for performance agents>
2. <second file>
3. <private memory folder>
(max 3 files — agents that read 6 files before acting are slow)

## Skills & trust
| Skill | What it does | Trust tier |
|---|---|---|
| <name> | <description> | Auto / Lead-gated / Human-gated |

## Memory
- **Reads:** <list of shared memory files this agent is allowed to read>
- **Writes:** `memory/agents/<dept>/<role>/` (private — no other agent writes here)

## Receives tasks from
- `ai-orchestrator` — <what triggers it from the orchestrator>
- `<peer agent>` — <what triggers a direct peer handoff>

## Hands to (directly — no orchestrator needed)
- `<agent>` — when <condition>
- `<agent>` — when <condition>

## Reports to
`ai-orchestrator` — <what the outcome report contains + any write actions queued>

## Done means
<one observable, verifiable statement — never "attempted", always "confirmed">
```

---

## Section 2 — Memory Architecture

### Three-layer structure

**Layer 1 — Critical (every agent reads, nobody edits alone)**
```
memory/CRITICAL_KPI_RULES.md
```
The single file every agent checks before any paid-media analysis. Edited only when a rule changes — requires explicit approval.

**Layer 2 — Shared (owned by growth-analyst, readable by all)**
```
memory/01_architecture.md       ← schema, table names, view names
memory/08_pitfalls.md           ← API traps, known failure modes
memory/14_learning_patterns.md  ← action outcomes + what worked/didn't
memory/09_open_tasks.md         ← cross-session work in progress
memory/00_index.md              ← navigation index
```
`growth-analyst` is the sole writer. All other agents read, never write.

**Layer 3 — Private (each agent writes its own folder, nobody else touches it)**
```
memory/agents/
  manager/
    ai-orchestrator/    ← routing decisions, escalation patterns
  performance/
    performance-lead/   ← threshold change history, budget decisions
    campaign-manager/   ← naming edge cases, pixel config notes
    creative-strategist/ ← persona insights, A/B outcomes per channel
  cro/
    cro-specialist/     ← test results, hypothesis outcomes
    ui-ux-designer/     ← design patterns, ZATCA badge variations
    developer/          ← pixel firing notes, UTM passthrough issues
  support/
    marketing-ops/      ← connector failure patterns, UTM mapping notes
    growth-analyst/     ← BQ query patterns, reconciliation findings
```

### Read/write rules
- Every agent reads Layer 1 + Layer 2 (relevant files only, not all of them)
- Every agent writes only to its own Layer 3 folder
- `growth-analyst` additionally writes Layer 2 shared files
- No agent reads another agent's Layer 3 folder

---

## Section 3 — Hybrid Handoff Model

### The model
- **Orchestrator → any agent:** task assignment with a HANDOFF packet
- **Any agent → peer directly:** hand off without going back to orchestrator first
- **Any agent → orchestrator:** report outcome when done + queue any write actions
- **Orchestrator gates ALL writes:** every scale/pause/create/launch waits for ✅

### Standard handoff packet (unchanged)
```
HANDOFF
from:    <your-agent-name>
to:      <target-agent-name>
why:     <one line: what triggered this>
window:  <YYYY-MM-DD to YYYY-MM-DD>
payload: <facts the receiver needs — numbers, IDs, paths>
ask:     <the single decision or action you want back>
```

### Who hands to whom directly

```
ai-orchestrator
  ├──► growth-analyst          (observe + compare → flags)
  ├──► performance-lead        (flag triage → routes to directs)
  │       ├──► campaign-manager ∥ creative-strategist  (parallel)
  │       │       campaign-manager ──► creative-strategist (needs copy)
  │       │       campaign-manager ──► marketing-ops (pixel verify)
  │       │       creative-strategist ──► cro-specialist (pre-launch align)
  │       └── both report back to performance-lead → up to orchestrator
  ├──► cro-specialist          (LP test start/decide)
  │       ├──► ui-ux-designer  (sequential)
  │       │       └──► developer (sequential)
  │       │               └──► cro-specialist (result)
  │       └── cro-specialist reports to orchestrator
  ├──► marketing-ops           (tracking/pixel/UTM/connectors)
  └──► growth-analyst          (memory, forecasts, BQ)
       both report directly to orchestrator
```

### What changes from current
- Currently: agents can only hand to their department lead, who routes up
- New: any agent can hand directly to any peer when the work calls for it
- Unchanged: the orchestrator still gates all writes and receives all outcome reports

---

## Section 4 — Activity Dashboard Redesign

### Problem
The current dashboard mixes 13 log-roles. Infrastructure noise (`health_monitor` = 10,790 rows, `bq_refresh` = 2,104 rows) drowns out performance marketing signal. The dashboard should answer: *what did the system decide today?*

### New structure — 4 panels

**Panel 1 — Marketing Decisions** (primary, always expanded)
Filtered to performance marketing roles only:

| Log role | Display label |
|---|---|
| `performance_audit` | Campaign Performance |
| `keyword_management` | Keyword Management |
| `daily_digest` | Daily Report & Approvals |
| `spike_detector` | Anomaly Alerts |

Columns: `time_riyadh` \| `action` \| `status` \| `channel` \| `campaign_name` \| `rows_affected`

**Panel 2 — Approval Outcomes** (secondary, always visible)
```sql
WHERE status IN ('approved', 'rejected', 'pending_approval')
```
Shows the full approval trail — what was queued, who acted, what executed.
Columns: `time_riyadh` \| `role` \| `action` \| `status` \| `channel` \| `campaign_name`

**Panel 3 — System Health** (collapsed by default, expand on RED)
One status row per infra role — last run timestamp + success/fail count for the day.
Roles: `health_monitor`, `bq_refresh`, `ops_scheduler`, `collector`
No detailed tables — just a health indicator. Expands only when investigating a system failure.

**Panel 4 — Cowork Agent Activity** (added after Cowork migration)
Which of the 9 agents ran, what they handed off, what was queued for approval.
Populated once Cowork logs to `agent_activity_log` with agent-seat role values.

### Heatmap
Keep the GitHub-style calendar heatmap — but filter Y-axis to Panel 1 roles only (4 rows instead of 13). Infrastructure roles removed from the heatmap entirely.

---

## Section 5 — Cowork Migration + n8n Integration

### What stays on Railway
The Python data collectors — API pulls from Meta, Google, HubSpot, Snapchat, LinkedIn into BigQuery. These are data infrastructure, not intelligence. They stay as-is.

### What moves to Cowork
The intelligence layer: analysis, decisions, approvals, handoffs.

### Architecture after migration

```
n8n (data/action layer)
  ├── Collects: Meta, Google, HubSpot, Snapchat, LinkedIn → BigQuery
  ├── Triggers: Cowork skills via webhook (e.g. "data is ready → run daily loop")
  ├── Routes: ✅/❌ reactions from Slack back to Cowork
  └── Executes: approved writes to ad platforms (after ✅ from Cowork)

Cowork (intelligence layer)
  ├── Scheduled: /daily-loop at 08:00 Asia/Riyadh
  ├── On-demand: /campaign-manager, /growth-analyst, etc.
  └── Outputs: #approvals digest to Slack, tasks to Asana

BigQuery (single source of truth — unchanged)
Railway (Python collectors — unchanged, runs in parallel)
```

### Cowork skill definitions

| Skill | Schedule / Trigger | Agent | Output |
|---|---|---|---|
| `/daily-loop` | 08:00 Riyadh daily | `ai-orchestrator` | #approvals digest + Asana tasks |
| `/campaign-manager` | On-demand | `campaign-manager` | Build spec or audit result |
| `/creative-strategist` | On-demand | `creative-strategist` | Creative brief + variant plan |
| `/growth-analyst` | On-demand | `growth-analyst` | Analysis + memory writes |
| `/cro-specialist` | On-demand | `cro-specialist` | LP test brief or result |
| `/marketing-ops` | On-demand | `marketing-ops` | Connector/pixel/UTM status |
| `/performance-lead` | On-demand | `performance-lead` | KPI decision + routed actions |
| `/weekly-review` | Monday 08:00 Riyadh | `ai-orchestrator` | Weekly ops summary |
| `/keyword-autofix` | Sunday 08:00 Riyadh | `campaign-manager` | Keyword policy enforcement |

### Cowork connectors required

| Connector | Used by | Purpose |
|---|---|---|
| BigQuery | `growth-analyst`, `marketing-ops` | Live data reads |
| Slack | `ai-orchestrator` | #approvals digest, #nexa-health |
| Asana | `ai-orchestrator`, all agents | Task creation + tracking |
| Meta Ads | `campaign-manager`, `marketing-ops` | Read audits; writes after ✅ |
| Google Ads | `campaign-manager` | Read audits; writes after ✅ |
| HubSpot | `growth-analyst` | Read-only lead/deal data |
| n8n (webhook) | `ai-orchestrator` | Trigger data collection + route approvals |

### n8n agent integration
Any agent can trigger an n8n workflow by calling its webhook URL. Example flows:
- `campaign-manager` proposes a pause → n8n holds the action → Slack ✅ received → n8n executes the Meta API call
- `marketing-ops` detects a broken connector → n8n fires the re-collection job → signals `growth-analyst` when data is ready
- `growth-analyst` completes analysis → n8n creates the Asana task with full context

This keeps agents focused on decisions only — they never call ad platform APIs directly. n8n is the hands; Cowork is the brain.

### Migration order (5 phases)

**Phase 1 — Agent file cleanup** (Claude Code)
Update all 9 `.claude/agents/*.md` files with the 7-field standard. Create `memory/agents/` folder structure.

**Phase 2 — Cowork skill files**
Create one Cowork skill file per agent from the updated `.md` definitions. Same content, Cowork format.

**Phase 3 — Connectors**
Wire BigQuery, Slack, Asana, Meta, Google Ads, HubSpot in Cowork. Test each connector independently.

**Phase 4 — Daily loop on Cowork**
Set up `/daily-loop` as a scheduled Cowork skill at 08:00 Riyadh. Run in parallel with Railway's `main.py daily` for 2 weeks. Compare outputs. Retire Railway's LLM layer once outputs match.

**Phase 5 — n8n wiring**
Replace Railway Python collectors one-by-one with n8n workflows. Verify BQ ↔ HubSpot reconciliation stays < 2% delta after each replacement. `marketing-ops` owns this phase.

**Phase 5 is optional and independent** — the system works without n8n. n8n is an improvement to the data/action layer, not a prerequisite for Cowork.

### Fallback during migration
Railway's `main.py daily` stays running through Phase 4. If Cowork has an outage, Railway covers. Only retired once Cowork is verified stable for 14 consecutive days.

---

## Section 6 — Slack Message Design

### Problem
Current messages are machine-written, too long, and unreadable past line 3. The digest should be a decision surface, not a report.

### Design principles
- One line per channel — no paragraphs
- Numbers in fixed order: spend · leads · CPQL — same position every day
- Actions separated from review items — clear what needs a reaction vs what's handled
- One ✅/❌ for all actions — single decision, not per-item
- Detail lives in Asana, not Slack — links only
- Dashboard URL once at the top

### Format

```
Nexa · {date}  |  {dashboard_url}

PERFORMANCE
{channel}    ${spend}  ·  {leads} leads  ·  ${cpql} CPQL   {status_icon}
{channel}    ${spend}  ·  {leads} leads  ·  ${cpql} CPQL   {status_icon}

ACTIONS  —  ✅ executes all  ·  ❌ skips all
↗  {campaign_name}   +{pct}% budget  (${old} → ${new})
⏸  {campaign_name}   pause           (${cpql} CPQL · {days}d)

REVIEW ONLY  (Asana tasks created)
⚡  {flag_description}  —  {asana_url}
```

### Status icons
| Icon | Meaning | CPQL zone |
|---|---|---|
| ✅ | Scale | Under $85 |
| ⚠️ | Watch | $85–$130 |
| 🔴 | Pause candidate | Over $130 |

### Rules
- ACTIONS block only appears if there are gated write actions pending
- REVIEW ONLY block only appears if there are non-gated items
- If nothing to act on: ACTIONS block is omitted entirely — no "nothing to action today"
- Channel order: sorted by spend descending
- CPQL always shown in USD, spend always in USD
- Campaign names shown exactly as they appear in the platform — no truncation
- Asana task URL included on every review item — never inline detail

### What this replaces
The current `daily_digest` output from `main.py daily`. The `ai-orchestrator` Cowork skill produces this format. The old Railway digest is retired in Phase 4.

### Activity dashboard integration
`daily_digest` rows in `agent_activity_log` store the full message content in the `details` JSON column so Panel 1 of the dashboard can surface what was posted, not just that it was posted.

---

## What does NOT change

- **The approval gate** — ✅/❌ in #approvals, always, for every write action. Cowork doesn't change this.
- **HubSpot read-only** — no PATCH/DELETE/POST without explicit Slack approval.
- **Spend reporting in USD** — unchanged across all layers.
- **CPQL before CPL, 14-day minimum** — enforced in every agent's trust tier table.
- **Railway Python collectors** — stay running; Cowork doesn't touch data collection.
- **The `memory/` folder** — `growth-analyst` still owns shared memory writes. Cowork agents write to the same repo.

---

## Files this spec creates or modifies

### New files
```
docs/superpowers/specs/2026-06-11-agent-clarity-cowork-migration-design.md  ← this file
memory/agents/manager/ai-orchestrator/          ← empty, ready for agent writes
memory/agents/performance/performance-lead/
memory/agents/performance/campaign-manager/
memory/agents/performance/creative-strategist/
memory/agents/cro/cro-specialist/
memory/agents/cro/ui-ux-designer/
memory/agents/cro/developer/
memory/agents/support/marketing-ops/
memory/agents/support/growth-analyst/
```

### Modified files (agent cleanup — Phase 1)
```
.claude/agents/ai-orchestrator.md
.claude/agents/performance-lead.md
.claude/agents/campaign-manager.md
.claude/agents/creative-strategist.md
.claude/agents/cro-specialist.md
.claude/agents/ui-ux-designer.md
.claude/agents/developer.md
.claude/agents/marketing-ops.md
.claude/agents/growth-analyst.md
```

### Modified files (dashboard — after Phase 1)
```
memory/16_activity_dashboard.md    ← updated spec with 4-panel design
```

### New Cowork files (Phase 2 — separate project)
```
.claude/skills/cowork/daily-loop.md
.claude/skills/cowork/campaign-manager.md
.claude/skills/cowork/creative-strategist.md
.claude/skills/cowork/growth-analyst.md
.claude/skills/cowork/cro-specialist.md
.claude/skills/cowork/marketing-ops.md
.claude/skills/cowork/performance-lead.md
.claude/skills/cowork/weekly-review.md
.claude/skills/cowork/keyword-autofix.md
```
