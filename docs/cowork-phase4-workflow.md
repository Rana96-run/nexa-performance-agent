# Phase 4 — Cowork Multi-Agent Daily Loop

**Owner:** ai-orchestrator  
**Blocks:** Phase 5 (retire Railway LLM layer)  
**Status:** ⬜ Not started — waiting on Phase 3 connectors  
**Start condition:** All 6 Phase 3 connectors wired + `drive_reader.py` uploaded to Railway

---

## Critical constraint (re-read every session)

> **Cowork's sandbox cannot run Python analysers, call the BigQuery client
> library, or hit Google/Slack APIs via code.**
>
> The correct split: **Railway runs analysis → writes to Asana + BQ.**
> **Cowork reads those outputs** via connectors and does the human-facing
> summarisation + routing. This is documented in `memory/14_learning_patterns.md`
> (entry: 2026-06-12). Any Cowork skill that tries to run `analysers/` or
> `bq_client.query(...)` directly **will fail silently**.

---

## The handoff chain

```
Railway (08:00 Riyadh)
  collectors/* → BQ
  analysers/campaign_health.py → flags → Asana tasks
  analysers/period_compare.py  → period data → BQ
  analysers/forecaster.py      → projection → BQ
        │
        ▼
Cowork /daily-loop (08:05 Riyadh — 5 min after Railway)
  ai-orchestrator
        │
        ├─► growth-analyst         (reads BQ + Asana context)
        │         │
        │         └─► HANDOFF to performance-lead
        │
        ├─► performance-lead       (receives flags from growth-analyst)
        │         │
        │         ├─► HANDOFF to campaign-manager    (parallel)
        │         └─► HANDOFF to creative-strategist (parallel)
        │
        ├─► campaign-manager   ──┐ (both return to performance-lead)
        ├─► creative-strategist ─┘
        │
        └─► ai-orchestrator gates ALL write actions → #approvals digest
```

---

## Step-by-step loop (Cowork side)

### Step 1 — ai-orchestrator: get context

Read from connectors:
1. **Asana** — open tasks in `ASANA_PROJECT_DAILY_ACTIVITY` created since yesterday 08:00 Riyadh. These are Railway's flag outputs (CPQL_REGRESSED, ROAS_REGRESSED, QUAL_DROPPED, LAUNCH_WAVE, ZERO_CONV, JUNK_LEADS).
2. **BigQuery** — summary row from `paid_channel_daily` for yesterday + 7-day window (pre-aggregated view, one row per channel). Fetch: `SELECT channel, spend, leads_total, leads_qualified, cpql, roas FROM nexa_performance.paid_channel_daily WHERE date = DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 1 DAY)`.
3. **BigQuery** — pending monitor tasks (actions executed 7d and 14d ago): `SELECT * FROM nexa_performance.agent_activity_log WHERE action IN ('pause','scale','create') AND DATE_DIFF(CURRENT_DATE(), event_date, DAY) IN (7,14) AND outcome IS NULL`.

Issue HANDOFF to `growth-analyst`:
```
HANDOFF
from:    ai-orchestrator
to:      growth-analyst
why:     Daily 8-step loop — step 2 (COMPARE) and step 3 (INVESTIGATE)
window:  {yesterday-6d} to {yesterday}  vs  {yesterday-13d} to {yesterday-7d}
payload: BQ rows attached above; Asana flag task IDs: {list}
ask:     Period-over-period table (spend/leads/CPQL per channel, Δ%). Flag each
         channel: ✅ <$85 CPQL | ⚠️ $85–$130 | 🔴 >$130. For any 🔴 or new flag,
         provide root-cause in 2 sentences. Return a HANDOFF packet to
         performance-lead with findings + recommended actions.
```

### Step 2 — growth-analyst: compare + investigate

Reads from:
- **BigQuery**: `paid_channel_daily`, `hubspot_leads_module_daily` (pre-agg CTE pattern — never direct join)
- **Asana**: flag tasks for context

Produces: period comparison table + root-cause notes per flagged channel.

Issues HANDOFF to `performance-lead`:
```
HANDOFF
from:    growth-analyst
to:      performance-lead
why:     Step 3 complete — flags with root-cause ready for triage
window:  {start} to {end}
payload:
  {channel}: spend=${X}, leads={N}, CPQL=${Y} ({Δ}%)
  ROOT CAUSE: {2-sentence explanation}
  FLAGS: {CPQL_REGRESSED | QUAL_DROPPED | ZERO_CONV | LAUNCH_WAVE | clean}
  MONITOR: {action_id} from {date} — 7d check due
ask:     Decide scale/pause/monitor for each flag. For scale: full setup
         (campaign ID, budget change, rationale). For pause: campaign/ad ID +
         14-day data summary. Return HANDOFF to ai-orchestrator with decisions.
```

### Step 3 — performance-lead: triage + decide

Reads from:
- **BigQuery**: drill into `v_adset_performance`, `v_ad_performance` for flagged channels
- **Asana**: any open optimization tasks for the same campaigns

Rules (from CRITICAL_KPI_RULES.md):
- CPQL before CPL
- 14-day minimum window for pause/scale
- Leads ONLY from `hubspot_leads_module_daily`

If campaign builds are needed, issue parallel HANDOFFs:
```
HANDOFF
from:    performance-lead
to:      campaign-manager          ← and simultaneously →      creative-strategist
why:     Flag {X} requires new campaign / creative test
window:  {start} to {end}
payload: {campaign context, audience data, platform}
ask:     campaign-manager: build full naming + setup spec
         creative-strategist: write 2 copy variants (AR, MSA)
         Both return to performance-lead.
```

Returns HANDOFF to `ai-orchestrator` with final recommendation list (scale/pause/build/monitor).

### Step 4 — ai-orchestrator: gate + digest

1. Receives decisions from performance-lead (+ campaign-manager / creative-strategist if parallel work ran).
2. Checks MONITOR items — if 7d/14d action due, pulls outcome from BQ `agent_activity_log`, sends update to `growth-analyst` to record in `memory/14_learning_patterns.md`.
3. Builds ONE #approvals digest (format below).
4. Posts to `#approvals` Slack channel.
5. Creates Asana tasks for all REVIEW ONLY items.
6. **Does NOT execute anything.** Waits for ✅/❌ reaction.

---

## #approvals digest format

```
Nexa · {YYYY-MM-DD}  |  {DASHBOARD_URL}

PERFORMANCE  ({start} → {end})
{channel}   ${spend}  ·  {leads} leads  ·  ${cpql} CPQL  {✅/⚠️/🔴}  ({Δ}% vs prior)

ACTIONS  —  ✅ executes all  ·  ❌ skips all
↗  `{campaign_name}`   +{X}% budget  (${old} → ${new}/day)   [{14d data}]
⏸  `{ad_name}`         pause         (${cpql} CPQL · {N}d)

REVIEW ONLY  (Asana tasks already created — no execution needed)
⚡  {flag_type}  {campaign}  —  {asana_url}

MONITOR
🔍  `{action}` on `{campaign}` (executed {date}) — {outcome or "no data yet"}
```

CPQL zones: ✅ < $85 | ⚠️ $85–$130 | 🔴 > $130

---

## Phase 4 parallel-run protocol (14 days)

During the parallel run, BOTH Railway `main.py daily` AND Cowork `/daily-loop`
run simultaneously. Compare outputs daily:

| Check | Pass criteria |
|---|---|
| Channel-level CPQL flags match | Same channels flagged ✅/⚠️/🔴 |
| Recommended actions match | Same campaigns to scale/pause |
| Lead counts match | <2% delta (sync timing) |
| Asana tasks created correctly | Same task titles, correct assignees |
| #approvals digest formatted correctly | All required fields present |

Track in `memory/09_open_tasks.md` Phase 4 row. When **14 consecutive days pass**
all 5 checks → retire Railway LLM layer (`main.py daily` cron disabled).

---

## Implementation notes

### Cowork skill to update

`/.claude/skills/cowork/daily-loop.md` already has the 8-step loop at a high
level. After Phase 3 is wired, add a `## Cowork-Railway contract` section
documenting that BQ analysis stays on Railway and Cowork reads outputs.

### Scheduling

The Cowork scheduled task should fire at **08:05 Riyadh (05:05 UTC)**, 5 minutes
after Railway's 05:00 UTC cron, to ensure Railway's overnight analysis is written
to BQ and Asana before Cowork reads it.

### Handoff packet storage

During the parallel run, each HANDOFF packet is written to `memory/09_open_tasks.md`
as a session note so the next session can resume if interrupted. Once Phase 5
is complete, this becomes runtime-only (no file persistence needed).

---

## Dependencies

- Phase 3 complete (6 connectors wired)
- `collectors/drive_reader.py` deployed to Railway (for monthly report uploads)
- `analysers/period_compare.py` on Railway (runs before Cowork reads BQ)
- `analysers/forecaster.py` on Railway (same)
- Cowork daily-loop skill updated with Cowork-Railway contract section
