# n8n Workflow Reference

Complete node-by-node reference for all 13 n8n workflows. Use this when debugging a
workflow, tracing a data path, or understanding what calls what.

**BQ project:** `angular-axle-492812-q4` · **dataset:** `qoyod_marketing`  
**Asana project GID:** `1214135581886045`  
**Slack notify channel:** env `SLACK_CHANNEL_NOTIFY`; data-health channel: `C0ARMQKK8GK`  
**Google Sheets ID:** `120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg`

---

## 1. Cadence Workflows

### cadence_daily — `T8icImtZFLYeCa7e`

**Trigger:** Schedule — `0 0 4 * * *` (07:00 Riyadh daily)  
**Active:** yes  
**Purpose:** Master daily intelligence loop. Collects data from all ad platforms, runs Claude data guard, merges into BQ, reconciles with HubSpot, evaluates KPIs, dispatches all 6 KPI sub-flows, runs 3 AI analyst agents, posts Slack summary + approvals digest, creates Asana tasks, and writes audit log.

#### Phase 1 — Collection

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Every Day 7AM Riyadh | scheduleTrigger | Fires at 07:00 Riyadh (04:00 UTC) |
| 2 | Set Dates | code | Computes `date_from` (14 days ago), `date_to` (yesterday), ISO strings for all downstream queries |
| 3 | BQ Fetch Config | googleBigQuery | Reads `agent_config` table — thresholds, channel targets, active flags |
| 4 | Config Flatten | code | Expands config rows into flat key→value map passed to all subsequent nodes |
| 5 | Phase 1 Data Collection | executeWorkflow | Calls `infra_data_collection` (`jOnJxdpdaO3Vbi0B`) — returns mapped rows per channel |

#### Phase 2 — Guard + Load

| # | Node | Type | What it does |
|---|------|------|-------------|
| 6 | BQ Baseline | googleBigQuery | Queries last 2 days of `campaigns_daily` to establish expected row counts per channel |
| 7 | Build Guard Payload | code | Packages collected rows + baseline into Claude prompt: checks row counts, spend plausibility, missing channels |
| 8 | Claude · Data Guard | httpRequest (Anthropic) | Calls `claude-sonnet-4-6`; returns JSON `{should_load: bool, reason: string, warnings: []}` |
| 9 | Parse Guard | code | Extracts `should_load` flag; attaches warnings to output |
| 10 | IF should_load? | if | `true` → Build All MERGE SQLs; `false` → Alert · Guard Failed |
| 11 | Alert · Guard Failed | httpRequest (Slack) | Posts failure reason to notify channel; workflow stops |
| 12 | Build All MERGE SQLs | code | Generates MERGE INTO SQL for each channel's staging → `campaigns_daily` (upsert by date + campaign_id) |
| 13 | Execute MERGE → BQ | googleBigQuery | Runs all MERGE statements in sequence |
| 14 | All Loads Complete | merge | Waits for MERGE to finish before continuing |

#### Phase 2b — Reconciliation

| # | Node | Type | What it does |
|---|------|------|-------------|
| 15 | Query BQ Recon | googleBigQuery | (parallel) Counts leads from `hubspot_leads_module_daily` for last 7 days |
| 16 | Query HS Recon | httpRequest (HubSpot) | (parallel) Counts leads from HubSpot Lead Module API for same 7-day window |
| 17 | Reconcile BQ vs HS | code | Compares counts; passes if within 2% tolerance |
| 18 | IF Recon OK? | if | `true` → query phase; `false` → Alert · Recon Gap |
| 19 | Alert · Recon Gap | httpRequest (Slack) | Posts reconciliation gap detail; workflow stops |

#### Phase 3 — Intelligence

| # | Node | Type | What it does |
|---|------|------|-------------|
| 20 | Query KPIs | googleBigQuery | (parallel) Channel-level CPL, CPQL, leads, spend from `paid_channel_daily` joined to `hubspot_leads_module_daily` CTE |
| 21 | Query Period Compare | googleBigQuery | (parallel) Current 7d vs prior 7d across all channels |
| 22 | Query Ad Audit | googleBigQuery | (parallel) Ad-level CPL + disqualification rates from `ads_daily` joined to `hubspot_leads_module_daily` |
| 23 | Query Monitor | googleBigQuery | (parallel) ROAS from `channel_roas_daily`; qual rates; IS metrics from `keyword_performance_daily` |
| 24 | Query Forecast | googleBigQuery | (parallel) MTD actuals + run-rate projection from `paid_channel_daily` |
| 25 | KPI Evaluator | code | For each channel, assigns flags: `ROAS_REGRESSED`, `CPQL_REGRESSED`, `CPL_REGRESSED`, `QUAL_DROPPED`, `IS_LOW`, `CTR_DROP`, or `GREEN` |
| 26 | Route by Flag Type | switch | Routes each flag to its sub-flow executor (branches: roas / cpql / cpl / qual / is / ctr / green) |
| 27 | Execute A – ROAS Check | executeWorkflow | Calls `kpi_roas` (`MHCdIiAtKzHNve1x`) |
| 28 | Execute B – CPL Fix | executeWorkflow | Calls `kpi_cpl` (`Qd5SoGxZbgT1ohYP`) |
| 29 | Execute C – CPQL Fix | executeWorkflow | Calls `kpi_cpql` (`jfE5KKnPJQBf7MCj`) |
| 30 | Execute D – Qual Fix | executeWorkflow | Calls `kpi_qual_ratio` (`PxFBmtXDVgcNGzIM`) |
| 31 | Execute E – IS Fix | executeWorkflow | Calls `kpi_impression_share` (`eL0V6ReftV2U1wNf`) |
| 32 | Execute F – Creative Fix | executeWorkflow | Calls `kpi_creative_ctr` (`smHaEhWloComRQyz`) |
| 33 | Merge Sub-Flow Results | merge | Collects all sub-flow results before AI analyst pass |

#### Phase 3b — AI Analysts

| # | Node | Type | What it does |
|---|------|------|-------------|
| 34 | Wait growth-analyst | (implicit) | Waits for merge |
| 35 | Build growth-analyst | code | Packages KPI data + period comparison + sub-flow findings into growth-analyst prompt |
| 36 | Claude growth-analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns analysis + recommendations |
| 37 | Parse growth-analyst | code | Extracts structured output |
| 38 | Wait performance-lead | (implicit) | Waits for growth-analyst output |
| 39 | Build performance-lead | code | Packages growth-analyst findings + budget context into performance-lead prompt |
| 40 | Claude performance-lead | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns strategic decisions |
| 41 | Parse performance-lead | code | Extracts `needs_new_campaign`, actions list |
| 42 | IF needs_new_campaign? | if | `true` → Notify Campaign Proposal + await approval; `false` → skip |
| 43 | Notify Campaign Proposal | httpRequest (Slack) | Posts proposal summary to `#approvals` |
| 44 | Wait Campaign Approval | wait/webhook | Pauses execution; resumes via webhook `campaign-approval-webhook-001` from `infra_approval_listener` |
| 45 | Build campaign-manager | code | (parallel) Packages brief for campaign-manager agent |
| 46 | Build creative-strategist | code | (parallel) Packages brief for creative-strategist agent |
| 47 | Wait Agents | merge | Waits for both agent builds |
| 48 | Wait ai-orchestrator | (implicit) | Waits for all agent outputs |
| 49 | Build ai-orchestrator | code | Assembles final orchestrator prompt with all agent outputs |

#### Phase 4 — Output

| # | Node | Type | What it does |
|---|------|------|-------------|
| 50 | Phase 4 QA Gate | executeWorkflow | Calls `infra_qa_gate` (`ug3niLKrjPfO9Iz7`); must return `QA_PASSED` |
| 51 | Post Slack Performance | httpRequest (Slack) | (parallel) Posts daily performance summary to notify channel |
| 52 | Post Slack Approvals | httpRequest (Slack) | (parallel) Posts nightly approvals digest to `#approvals` |
| 53 | Expand Asana Tasks | code | (parallel) Formats all recommended actions into Asana task bodies |
| 54 | Build Audit SQL | code | (parallel) Builds INSERT SQL for audit log |
| 55 | Create Asana Task | httpRequest (Asana) | Creates tasks in channel-specific Asana projects |
| 56 | Audit Log BQ | googleBigQuery | Inserts execution record into `agent_audit_log` |

**Inputs:** none (schedule-triggered)  
**Outputs:** Slack messages (performance + approvals), Asana tasks, BQ audit log entry  
**Calls:** `jOnJxdpdaO3Vbi0B`, `MHCdIiAtKzHNve1x`, `jfE5KKnPJQBf7MCj`, `Qd5SoGxZbgT1ohYP`, `PxFBmtXDVgcNGzIM`, `eL0V6ReftV2U1wNf`, `smHaEhWloComRQyz`, `ug3niLKrjPfO9Iz7`  
**Called by:** nobody (master workflow)

---

### cadence_weekly — `iNSdpXH7Rc9Lb8h8`

**Trigger:** Schedule — `0 6 * * 0` (Sunday 06:00 UTC = 09:00 Riyadh)  
**Active:** yes  
**Purpose:** Weekly performance digest. Freshness-gates on BQ data, runs period comparison + forecast, calls Claude weekly-analyst + performance-lead, posts Slack weekly summary + approvals, creates Asana tasks, and logs LP audit to Google Sheets.

#### Freshness gate

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Schedule Weekly | scheduleTrigger | Fires Sunday 09:00 Riyadh |
| 2 | BQ Freshness Check | googleBigQuery | Queries `MAX(date)` from `campaigns_daily`; flags stale if older than yesterday |
| 3 | IF Data Fresh? | if | Fresh → main track; stale → Slack Stale Data Alert (stop) |
| 4 | Slack Stale Data Alert | httpRequest (Slack) | Posts stale warning; workflow stops |

#### Main track (parallel start)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 5 | Set Dates Weekly | code | Computes current 7d window + prior 7d window date strings |
| 6 | BQ LP Audit | googleBigQuery | (parallel with Set Dates) Queries `paid_channel_campaign_daily` for LP-level CPL, CPQL, leads, spend last 7d |

#### Set Dates triggers (parallel queries)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 7 | Query Period Compare | googleBigQuery | Current 7d vs prior 7d by channel from `paid_channel_daily` |
| 8 | Query Forecast | googleBigQuery | MTD + run-rate projection |
| 9 | Query Ad Audit | googleBigQuery | Ad-level CPL + disqualification from `ads_daily` |
| 10 | Query Monitor | googleBigQuery | ROAS, qual rates, IS from monitoring views |
| 11 | Collect Queries | merge/append | Waits for all 4 queries |

#### AI analyst pass

| # | Node | Type | What it does |
|---|------|------|-------------|
| 12 | Build weekly-analyst | code | Packages all query results into weekly analyst prompt |
| 13 | Claude weekly-analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns weekly analysis narrative |
| 14 | Build performance-lead | code | Packages weekly analysis + budget context |
| 15 | Claude performance-lead | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns strategic decisions |
| 16 | Parse weekly | code | Extracts actions, Slack text, Asana task bodies |

#### Output (parallel)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 17 | Post Slack Weekly | httpRequest (Slack) | Posts weekly summary to notify channel |
| 18 | Post Slack Approvals | httpRequest (Slack) | Posts approvals digest |
| 19 | Expand Asana Tasks | code | Formats action items |
| 20 | Build Audit SQL | code | Builds INSERT for audit log |
| 21 | Create Asana Task | httpRequest (Asana) | Creates tasks in channel-specific projects |
| 22 | Sheets Weekly Log | googleSheets | Appends row to "WeeklyLog" tab in shared spreadsheet |
| 23 | Build Approvals Text | code | Formats approvals message text |
| 24 | Post Slack Approvals | httpRequest (Slack) | Final approvals post |

#### LP track (from BQ LP Audit)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 25 | Code Format LP | code | Formats LP rows into sheet-ready arrays |
| 26 | Sheets Create LP Tab | googleSheets | Creates tab named `LP-YYYY-MM-DD` in shared spreadsheet |
| 27 | Sheets Write LP Rows | googleSheets | Writes LP performance rows to the new tab |
| 28 | Asana LP Draft Weekly | httpRequest (Asana) | Creates LP review task in Asana |

**Inputs:** none (schedule-triggered)  
**Outputs:** Slack weekly + approvals, Asana tasks, Google Sheets LP tab (`LP-YYYY-MM-DD`), Google Sheets weekly log (`WeeklyLog`)  
**Calls:** none  
**Called by:** nobody

---

### cadence_monthly — `0Zh45UoTtjjhRn8U`

**Trigger:** Schedule — `0 5 1 * *` (1st of month, 05:00 UTC = 08:00 Riyadh)  
**Active:** yes  
**Purpose:** Monthly review. Freshness-gates, runs month-over-month comparison + forecast + CRO + ROAS + monitor queries, calls Claude monthly-analyst + performance-lead, posts Slack monthly + approvals, creates Asana tasks, writes creative report to Sheets, writes LP brief to Asana.

#### Freshness gate

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Schedule Monthly | scheduleTrigger | Fires 1st of month 08:00 Riyadh |
| 2 | BQ Freshness Check | googleBigQuery | Queries `MAX(date)` from `campaigns_daily` |
| 3 | IF Data Fresh? | if | Fresh → 3-way parallel; stale → Slack alert (stop) |
| 4 | Slack Stale Alert | httpRequest (Slack) | Posts stale warning; stops |

#### 3-way parallel start

| # | Node | Type | What it does |
|---|------|------|-------------|
| 5 | Set Dates Monthly | code | Computes MTD + prior month same-days date strings |
| 6 | BQ Creative Report | googleBigQuery | Queries `ads_daily` for creative-level CTR, CPL, CPQL, spend last 30d |
| 7 | BQ LP Brief | googleBigQuery | Queries best-performing LP from prior month (lowest CPQL, min 10 leads) |

#### Main track — 5 parallel queries (from Set Dates Monthly)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 8 | Query Period Compare | googleBigQuery | Current MTD vs prior month same days from `paid_channel_daily` |
| 9 | Query Forecast | googleBigQuery | EOM spend/leads/CPQL projection |
| 10 | Query CRO | googleBigQuery | Qual rates + disqualification reasons from `hubspot_leads_module_daily` |
| 11 | Query ROAS | googleBigQuery | Revenue vs spend from `paid_channel_daily` |
| 12 | Query Monitor | googleBigQuery | IS, QS, ROAS multi-metric from monitoring views |
| 13 | Collect Queries | merge | Waits for all 5 |

#### Main AI pass

| # | Node | Type | What it does |
|---|------|------|-------------|
| 14 | Build monthly-analyst | code | Packages all query data into monthly analyst prompt |
| 15 | Claude monthly-analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns month-over-month narrative + forecast |
| 16 | Build performance-lead | code | Packages analysis + budget context |
| 17 | Claude performance-lead | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns strategic recommendations |
| 18 | Parse monthly | code | Extracts actions, Slack text, Asana bodies |

#### Main output (parallel)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 19 | Post Slack Monthly | httpRequest (Slack) | Posts monthly summary |
| 20 | Post Slack Approvals | httpRequest (Slack) | Posts approvals digest |
| 21 | Expand Asana Tasks | code | Formats action items |
| 22 | Build Audit SQL | code | Audit INSERT SQL |
| 23 | Create Asana Task | httpRequest (Asana) | Creates tasks in channel-specific projects |
| 24 | Audit Log BQ | googleBigQuery | Inserts audit record |

#### Creative track (from BQ Creative Report)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 25 | Code Format Creative | code | Formats creative rows for Sheets + Claude prompt |
| 26 | Build creative-strategist | code | Packages creative data into strategist prompt |
| 27 | Claude creative-strategist | httpRequest (Anthropic) | `claude-sonnet-4-6`; returns creative recommendations |
| 28 | Sheets Create Creative Tab | googleSheets | Creates tab named `Creative-YYYY-MM` |
| 29 | Sheets Write Creative Rows | googleSheets | Writes creative performance rows |
| 30 | Asana Creative Report Monthly | httpRequest (Asana) | Creates monthly creative review task |

#### LP track (from BQ LP Brief)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 31 | Code Format LP Brief | code | Formats best LP data into brief template |
| 32 | Asana LP Draft Monthly | httpRequest (Asana) | Creates monthly LP brief task |

**Inputs:** none (schedule-triggered)  
**Outputs:** Slack monthly + approvals, Asana tasks, Google Sheets creative tab (`Creative-YYYY-MM`), Asana LP brief task, BQ audit log  
**Calls:** none  
**Called by:** nobody

---

## 2. KPI Sub-flows

All sub-flows share the same return shape:
```json
{ "sub_flow": "<ID>", "status": "created", "channel": "<channel>" }
```
They are called by `cadence_daily` via `executeWorkflow` and return synchronously before cadence_daily continues.

---

### kpi_roas — `MHCdIiAtKzHNve1x`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Evaluates ROAS against 3 supporting factors (qual rate, CPQL, volume). No Claude call — pure logic. Either escalates to sales or proposes campaign fix.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Ad channel name |
| `roas` | number | 14-day ROAS |
| `qual_rate_pct` | number | Qualified lead rate (0–100) |
| `cpql` | number | Cost per qualified lead (USD) |
| `leads_total` | number | Leads in current window |
| `prior_leads_total` | number | Leads in prior window |
| `spend_14d` | number | Total spend last 14 days (USD) |

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives input params |
| 2 | Evaluate 3 Factors | code | Computes: `qual_ok` = qual≥45%, `cpql_ok` = cpql≤$85, `volume_ok` = leads≥prior_leads, `roas_ok` = roas≥2.0 OR spend≤$500 |
| 3 | All Green? | if | All 4 flags true → sales escalation; any false → campaign fix |
| 4 | Build Sales Escalation | code | Task title/body: ROAS is fine, problem is SQL conversion — route to sales team |
| 5 | Build Campaign Fix | code | Task title/body: identifies which factor failed, proposes budget or targeting fix |
| 6 | Create Asana Task | httpRequest (Asana) | Creates task in channel-specific project |
| 7 | Return Result | set | Returns `{sub_flow: "A_ROAS", status: "created", channel, action: "sales_escalation" or "campaign_fix"}` |

**Called by:** cadence_daily "Execute A – ROAS Check"

---

### kpi_cpql — `jfE5KKnPJQBf7MCj`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Drills into CPQL regression. Queries 30-day campaign breakdown, passes to Claude for root cause + fix recommendation, creates Asana task.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Ad channel name |
| `cpql` | number | Current CPQL (USD) |

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives channel + cpql |
| 2 | BQ CPQL Drill | googleBigQuery | 30-day CTE join: pre-aggregates `hubspot_leads_module_daily` then joins to `campaigns_daily`; excludes paused campaigns (spend=0 for 2+ days); returns campaign-level CPQL sorted desc |
| 3 | Build Claude Prompt | code | Filters rows where cpql>$95; builds prompt with worst campaigns highlighted |
| 4 | Claude CPQL Analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`, max 2000 tokens; returns JSON: `{root_cause, campaigns_to_fix, asana_title, action_items[]}` |
| 5 | Parse Claude | code | Extracts structured fields |
| 6 | Create Asana Task | httpRequest (Asana) | Creates task with full campaign breakdown + action items |
| 7 | Return Result | set | Returns `{sub_flow: "C_CPQL", status: "created", channel}` |

**Called by:** cadence_daily "Execute C – CPQL Fix"

---

### kpi_cpl — `Qd5SoGxZbgT1ohYP`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Drills into CPL regression (entry gate: CPL > $38). Queries 30-day breakdown, Claude analysis, Asana task.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Ad channel name |
| `cpl` | number | Current CPL (USD) |

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives channel + cpl |
| 2 | BQ CPL Drill | googleBigQuery | 30-day CTE join filtered by channel; campaign-level CPL sorted desc |
| 3 | Build Claude Prompt | code | Filters campaigns where cpl>$38; builds analysis prompt |
| 4 | Claude CPL Analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`, max 2000 tokens; returns JSON: `{root_cause, campaigns_to_fix, asana_title, action_items[]}` |
| 5 | Parse Claude | code | Extracts structured fields |
| 6 | Create Asana Task | httpRequest (Asana) | Creates task with breakdown |
| 7 | Return Result | set | Returns `{sub_flow: "B_CPL", status: "created", channel}` |

**Called by:** cadence_daily "Execute B – CPL Fix"

---

### kpi_qual_ratio — `PxFBmtXDVgcNGzIM`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Responds to qualification rate drop. Routes to either urgent LP redirect (qual<30%) or standard improvement task (30–45%). No Claude call — rule-based.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Ad channel name |
| `qual_rate_pct` | number | Qual rate percentage (0–100) |

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives channel + qual_rate_pct |
| 2 | BQ Qual Drill | googleBigQuery | 14-day query: campaigns with `leads_total>0`, returns disqualification breakdown per campaign |
| 3 | Qual < 30%? | if | <30% → LP Redirect Urgent; ≥30% → Qual Improvement |
| 4 | Build LP Redirect Urgent | code | P0 task, due today: redirect LP immediately |
| 5 | Build Qual Improvement | code | P1 task, due +2 days: investigate targeting + creative |
| 6 | Create Asana Task | httpRequest (Asana) | Creates task |
| 7 | Return Result | set | Returns `{sub_flow: "D_QUAL", status: "created", channel, action: "lp_redirect" or "qual_fix"}` |

**Called by:** cadence_daily "Execute D – Qual Fix"

---

### kpi_impression_share — `eL0V6ReftV2U1wNf`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Diagnoses impression share loss. Queries IS breakdown (budget vs rank loss), passes to Claude to identify whether the cause is budget or Quality Score, creates Asana task.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Ad channel name |

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives channel |
| 2 | BQ IS Campaign Drill | googleBigQuery | 14-day avg: IS, `lost_is_budget`, `lost_is_rank` from `keyword_performance_daily`; excludes paused campaigns |
| 3 | Build Claude Prompt | code | Packages IS breakdown per campaign |
| 4 | Claude IS Analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`, max 2000 tokens; returns JSON: `{is_lost_to, root_cause, campaigns_to_fix, asana_title}` |
| 5 | Parse Claude | code | Extracts structured fields |
| 6 | Create Asana Task | httpRequest (Asana) | Creates task |
| 7 | Return Result | set | Returns `{sub_flow: "E_IS", status: "created", channel}` |

**Called by:** cadence_daily "Execute E – IS Fix"

---

### kpi_creative_ctr — `smHaEhWloComRQyz`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Detects creative fatigue via CTR drop. Entry: CTR drop >20%, min 1000 impressions in 3-day window, ad active min 3 days. Queries baseline vs recent CTR, Claude identifies fatigued ads, creates Asana task.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `channel` | string | Ad channel name |

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives channel |
| 2 | BQ CTR Creative Drill | googleBigQuery | From `ads_daily`: baseline window d-10 to d-4, recent window last 3d; `WHERE impressions_3d>=1000 AND ctr_delta_pct < -0.20` |
| 3 | Build Claude Prompt | code | Skips (returns early) if no fatigued ads found; otherwise packages ad list |
| 4 | Claude Creative Analyst | httpRequest (Anthropic) | `claude-sonnet-4-6`, max 2000 tokens; returns JSON: `{fatigued_ads, root_cause, asana_title, action_items[]}` |
| 5 | Parse Claude | code | Extracts structured fields |
| 6 | Create Asana Task | httpRequest (Asana) | Creates task |
| 7 | Return Result | set | Returns `{sub_flow: "F_CREATIVE", status: "created", channel}` |

**Called by:** cadence_daily "Execute F – Creative Fix"

---

## 3. Infrastructure Workflows

### infra_data_collection — `jOnJxdpdaO3Vbi0B`

**Trigger:** executeWorkflowTrigger (called by cadence_daily only)  
**Active:** yes  
**Purpose:** Fetches raw campaign data from all 6 ad platforms (7 API accounts across 2 date-split account pairs), normalizes into a unified schema, runs data guard + BQ MERGE, reconciles against HubSpot, returns status.

**Accounts and credential handling:**

| Platform | Accounts | Notes |
|----------|----------|-------|
| Google Ads | 151-302-0554 + 575-349-4964 | Merged before mapping |
| Meta Ads | قيود account + Qoyod account | Merged before mapping |
| Snapchat Ads | 2024 account + 2025 account | Merged before mapping |
| TikTok Ads | 2024 account + 2025 account | Merged before mapping |
| LinkedIn Ads | Single account | Direct map |
| Microsoft Ads | 188176729 + 187231519 | Token refreshed per run; new token stored back to n8n via API |

**Full node list:**

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Entry point called by cadence_daily |
| 2 | Query · Freshness Check | googleBigQuery | Checks `MAX(date)` per channel in `campaigns_daily`; flags channels stale >1 day |
| 3 | IF · Stale Channels | if | Any stale → Alert · Stale Data (Slack) then continue; all fresh → skip alert |
| 4 | Alert · Stale Data | httpRequest (Slack) | Warns which channels are stale; does not stop execution |
| 5 | Refresh MS Token | httpRequest | OAuth2 token refresh for Microsoft Ads using `refresh_token` + `client_id` + `client_secret` + `scope` |
| 6 | Store New MS Refresh Token | httpRequest | Stores new refresh token back to n8n credential store via n8n API (`X-N8N-API-KEY` header) |
| 7 | Google Ads · 151-302-0554 | httpRequest | Fetches campaign stats via Google Ads API |
| 8 | Google Ads · 575-349-4964 | httpRequest | Fetches campaign stats for second account |
| 9 | Merge Google Ads Accounts | merge | Combines both Google accounts |
| 10 | Map · Google Ads | code | Normalizes to unified schema: `{date, campaign_id, campaign_name, channel, spend, impressions, clicks, leads}` |
| 11 | Error Skip · Google Ads | code | On API error: returns empty rows so downstream continues |
| 12 | Meta Ads · قيود | httpRequest | Fetches via Meta Marketing API |
| 13 | Meta Ads · Qoyod | httpRequest | Fetches for second account |
| 14 | Merge Meta Accounts | merge | Combines both Meta accounts |
| 15 | Map · Meta | code | Normalizes to unified schema |
| 16 | Error Skip · Meta | code | Empty rows on error |
| 17 | Snapchat Ads · 2024 | httpRequest | Fetches via Snapchat Marketing API |
| 18 | Snapchat Ads · 2025 | httpRequest | Fetches for second account |
| 19 | Merge Snapchat Accounts | merge | Combines both Snapchat accounts |
| 20 | Map · Snapchat | code | Normalizes; divides `spend` micros by 1,000,000 to USD |
| 21 | Error Skip · Snapchat | code | Empty rows on error |
| 22 | TikTok Ads · 2024 | httpRequest | Fetches via TikTok Business API |
| 23 | TikTok Ads · 2025 | httpRequest | Fetches for second account |
| 24 | Merge TikTok Accounts | merge | Combines both TikTok accounts |
| 25 | Map · TikTok | code | Normalizes to unified schema |
| 26 | Error Skip · TikTok | code | Empty rows on error |
| 27 | LinkedIn Ads | httpRequest | Fetches via LinkedIn Marketing Solutions API |
| 28 | Map · LinkedIn | code | Normalizes to unified schema |
| 29 | Error Skip · LinkedIn | code | Empty rows on error |
| 30 | Microsoft Ads · 188176729 | httpRequest | Fetches via Bing Ads API using refreshed token; headers: `Authorization`, `CustomerAccountId`, `CustomerId` |
| 31 | Microsoft Ads · 187231519 | httpRequest | Fetches for second account |
| 32 | Merge Microsoft Accounts | merge | Combines both Microsoft accounts |
| 33 | Map · Microsoft Ads | code | Normalizes to unified schema |
| 34 | Error Skip · Microsoft Ads | code | Empty rows on error |
| 35 | Merge All Channels | merge | Combines all 6 channel outputs (with error-skip fallbacks) |
| 36 | Aggregate Campaigns | code | Deduplicates and aggregates by `(date, campaign_id, channel)` |
| 37 | BQ Baseline | googleBigQuery | Queries last 2 days from `campaigns_daily` for row count baseline |
| 38 | Build Guard Payload | code | Packages collected rows + baseline for Claude |
| 39 | Claude · Data Guard | httpRequest (Anthropic) | `claude-sonnet-4-6`; validates data integrity; returns `{should_load, reason, warnings[]}` |
| 40 | Parse Guard | code | Extracts `should_load` flag |
| 41 | IF should_load? | if | `true` → Build All MERGE SQLs; `false` → Alert · Recon Gap (stop) |
| 42 | Build All MERGE SQLs | code | Generates MERGE INTO `campaigns_daily` SQL for each channel |
| 43 | Execute MERGE → BQ | googleBigQuery | Runs all MERGEs |
| 44 | All Loads Complete | merge | Waits for MERGE |
| 45 | Query BQ Recon | googleBigQuery | (parallel) BQ lead count for reconciliation window |
| 46 | Query HS Recon | httpRequest (HubSpot) | (parallel) HubSpot lead count for same window |
| 47 | Reconcile BQ vs HS | code | Compares; passes within 2% tolerance |
| 48 | IF Recon OK? | if | `true` → Return Result; `false` → Alert · Recon Gap |
| 49 | Alert · Recon Gap | httpRequest (Slack) | Posts gap detail to notify channel |
| 50 | Merge Recon Data | merge | Collects recon result |
| 51 | Return Result | set | Returns `{status: "ok" or "recon_failed", recon_ok: bool}` |

**Inputs:** none (receives dates from cadence_daily context)  
**Outputs:** Populates `campaigns_daily` via MERGE; returns status to cadence_daily  
**Calls:** nothing  
**Called by:** cadence_daily "Phase 1 Data Collection"

---

### infra_approval_listener — `5Acqsbxsk0XQ5k9e`

**Trigger:** Webhook POST at path `slack-approval`  
**Active:** yes (always-on listener)  
**Purpose:** Listens for Slack reaction events (✅ / ❌) on approval messages. Resumes paused cadence_daily executions waiting for campaign-approval webhook, or posts rejection to the Slack thread.

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Slack Webhook | webhook | Receives POST from Slack Events API at `/webhook/slack-approval` |
| 2 | Handle Challenge | if | `body.type == "url_verification"` → Respond Challenge; else → Extract Reaction |
| 3 | Respond Challenge | respondToWebhook | Returns `{challenge}` for Slack URL verification handshake |
| 4 | Extract Reaction | code | Reads `event.reaction`; maps `white_check_mark` → approved, `x` → rejected; extracts `event.item.ts` (message timestamp) and `event.item.channel` |
| 5 | IF Approved | if | `approved` → Resume Waiting Execution; `rejected` → Post Rejected |
| 6 | Resume Waiting Execution | httpRequest | POST to n8n execution resume endpoint with webhook ID `campaign-approval-webhook-001`; passes `{approved: true}` |
| 7 | Post Rejected | httpRequest (Slack) | Posts thread reply "❌ Action rejected" to original message thread |

**Inputs:** Slack Events API POST (reaction_added events)  
**Outputs:** Resumes cadence_daily waiting execution OR posts rejection Slack thread reply  
**Calls:** nothing  
**Called by:** nobody (standalone listener; linked to cadence_daily via webhook ID `campaign-approval-webhook-001`)

---

### infra_qa_gate — `ug3niLKrjPfO9Iz7`

**Trigger:** executeWorkflowTrigger  
**Purpose:** Output validation gate. Validates that any sub-flow result or workflow output meets minimum quality standards before downstream posting. Blocks unsafe outputs.

**Inputs:**

| Field | Type | Description |
|-------|------|-------------|
| `sub_flow` | string | Sub-flow identifier (e.g. "A_ROAS", "C_CPQL", "infra_data_health") |
| `status` | string | Claimed status from upstream node |
| `channel` | string | Channel or context label |

**Validation checks (all must pass):**

1. `sub_flow` field is present and non-empty
2. `channel` field is present and non-empty
3. `status` is one of: `created`, `ok`, `QA_PASSED`
4. No SAR-only spend values (spend must be USD — catches `spend_sar` references)
5. No auto-execution claims (output must not claim to have auto-paused/enabled anything)

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Trigger | executeWorkflowTrigger | Receives input fields |
| 2 | Validate Output | code | Runs all 5 checks; collects errors into `errors[]` array |
| 3 | All Checks Passed? | if | `errors.length == 0` → QA_PASSED; else → QA_FAILED |
| 4 | QA_PASSED | set | Returns `{qa_result: "QA_PASSED", sub_flow, channel, validated_at: ISO timestamp}` |
| 5 | QA_FAILED | set | Returns `{qa_result: "QA_FAILED", sub_flow, channel, errors[], validated_at}` |

**Outputs:** `{qa_result, sub_flow, channel, validated_at, errors?}`  
**Calls:** nothing  
**Called by:** cadence_daily "Phase 4 QA Gate", infra_data_health "QA Gate"

---

### infra_data_health — `sgC6o3e7J9sk8VVr`

**Trigger:** Schedule — `0 6 * * *` (daily 06:00 UTC = 09:00 Riyadh)  
**Active:** yes  
**Purpose:** Daily BQ↔HubSpot reconciliation health check. Compares deals and leads counts across BQ and HubSpot API for the last 60 days. Posts result to `#data-health` Slack channel. Threshold: ≥85% = healthy.

| # | Node | Type | What it does |
|---|------|------|-------------|
| 1 | Daily 9am Riyadh | scheduleTrigger | `0 6 * * *` — fires 09:00 Riyadh daily |
| 2 | Set Dates | code | Computes `ytd_start_ms`, `days60_ms`, `today_end_ms` as Unix ms strings; also ISO date versions |
| 3 | BQ Deals | googleBigQuery | Sums `deals_total` from `hubspot_deals_daily` WHERE last 60 days AND `qoyod_source` IN paid channels AND `pipeline` IN ('Sales Pipeline','Bookkeeping','Qflavours'); groups by pipeline |
| 4 | BQ Leads | googleBigQuery | Sums `leads_total` from `hubspot_leads_module_daily` WHERE last 60 days |
| 5 | HS Deals | httpRequest (HubSpot) | POST to `/crm/v3/objects/deals/search`; filters by `pipeline` IN (default + Bookkeeping + Qflavours), `deal_qoyod_source` IN paid channels, `createdate BETWEEN days60_ms AND today_end_ms`; `limit: 1` (uses `total` field only) |
| 6 | HS Leads | httpRequest (HubSpot) | POST to `/crm/v3/objects/0-136/search`; filters by `hs_createdate GTE days60_ms`; `limit: 1` (uses `total` field only) |
| 7 | Build Report | code | Computes `dealsRate = round(bq/hs*100)` and `leadsRate`; formats Slack message with ✅ (≥85%) or ❌ (<85%) icons; appends gap note if any rate <85% |
| 8 | QA Gate | executeWorkflow | Calls `infra_qa_gate` (`ug3niLKrjPfO9Iz7`) with `sub_flow="infra_data_health"`, `channel="data-health"` |
| 9 | Post Slack | httpRequest (Slack) | Posts report text to channel `C0ARMQKK8GK` (#data-health) |

**Inputs:** none (schedule-triggered)  
**Outputs:** Slack message to `#data-health` (`C0ARMQKK8GK`)  
**Calls:** `ug3niLKrjPfO9Iz7` (infra_qa_gate)  
**Called by:** nobody (standalone)

---

## Cross-workflow reference

### Sub-flow call map

```
cadence_daily (T8icImtZFLYeCa7e)
├── infra_data_collection (jOnJxdpdaO3Vbi0B)   Phase 1
├── kpi_roas (MHCdIiAtKzHNve1x)                Execute A
├── kpi_cpl (Qd5SoGxZbgT1ohYP)                 Execute B
├── kpi_cpql (jfE5KKnPJQBf7MCj)                Execute C
├── kpi_qual_ratio (PxFBmtXDVgcNGzIM)          Execute D
├── kpi_impression_share (eL0V6ReftV2U1wNf)    Execute E
├── kpi_creative_ctr (smHaEhWloComRQyz)         Execute F
└── infra_qa_gate (ug3niLKrjPfO9Iz7)           Phase 4

cadence_weekly (iNSdpXH7Rc9Lb8h8)   — no sub-workflow calls
cadence_monthly (0Zh45UoTtjjhRn8U)  — no sub-workflow calls

infra_data_health (sgC6o3e7J9sk8VVr)
└── infra_qa_gate (ug3niLKrjPfO9Iz7)

infra_approval_listener (5Acqsbxsk0XQ5k9e)  — standalone; unblocks cadence_daily via webhook
```

### KPI thresholds (enforced in code nodes)

| KPI | Scale | Acceptable | Warning | Pause |
|-----|-------|------------|---------|-------|
| CPL (campaign) | <$25 | $25–38 | $40–49 | >$50 |
| CPQL (campaign) | <$85 | $85–95 | $95–130 | >$160 |
| ROAS | ≥2.0x | — | — | <2.0x AND spend>$500 |
| Qual rate | ≥45% | 30–45% | — | <30% (P0 LP redirect) |
| CTR delta | — | — | — | drop >20% with ≥1000 imps |
| IS lost (budget) | — | — | — | triggers E_IS sub-flow |

### Data sources per query type

| Query | Table / View |
|-------|-------------|
| Channel-level KPIs | `paid_channel_daily` |
| Campaign-level KPIs | `paid_channel_campaign_daily` |
| Ad-level KPIs | `ads_daily` |
| Leads (source of truth) | `hubspot_leads_module_daily` |
| Deals / Revenue | `hubspot_deals_daily` |
| ROAS | `channel_roas_daily` |
| Impression share / QS | `keyword_performance_daily` |
| Agent config / thresholds | `agent_config` |
| Audit log | `agent_audit_log` |

### Credentials map

| Credential name | Used by |
|----------------|---------|
| BigQuery (Qoyod) | All BQ nodes |
| Anthropic account | All Claude httpRequest nodes |
| HubSpot (Qoyod) | HS Recon, HS Deals, HS Leads |
| Slack (Qoyod) | All Slack httpRequest nodes |
| Meta (Qoyod) | Meta Ads nodes |
| Google Ads (Qoyod) | Google Ads nodes |
| Snapchat (Qoyod) | Snapchat Ads nodes |
| TikTok (Qoyod) | TikTok Ads nodes |
| LinkedIn (Qoyod) | LinkedIn Ads node |
| (MS token via OAuth refresh) | Microsoft Ads nodes (self-rotating) |
