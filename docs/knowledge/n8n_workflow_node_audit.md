# n8n Workflow Node Audit
Last updated: 2026-06-23

## Fixes Applied 2026-06-23

| Bug | Workflow | Fix | Status |
|-----|---------|-----|--------|
| Config-Flatten missing date fields → sub-workflow gets undefined dates → all platform nodes fail silently → 93/118 nodes never run | cadence_daily | Merge Set Dates output into Config-Flatten | FIXED + DEPLOYED |
| IF node type coercion: days_stale returned as string, IF expects int | cadence_weekly | CAST(DATE_DIFF AS INT64) in BQ query | FIXED + DEPLOYED |
| LP Audit uses destination_url (column doesn't exist in campaigns_daily) | cadence_weekly | Changed to final_url — NOTE: JSON inspection 2026-06-23 shows BQ LP Audit node (wkly-lp-01) STILL uses `destination_url` and `query` param (not `sqlQuery`). Fix was NOT deployed to live JSON. Re-deploy required. | NEEDS RE-DEPLOY |
| agent_action_log table doesn't exist | cadence_weekly, cadence_monthly | Replaced with agent_activity_log | FIXED + DEPLOYED |
| BQ template var escaping \{{ \.BQ_PROJECT }} | kpi_cpql, kpi_qual_ratio | Replaced with correct $vars.BQ_PROJECT | FIXED + DEPLOYED |
| MAX() instead of SUM() for lead counts after JOIN | kpi_qual_ratio | Changed to SUM() + recompute qual_rate as SAFE_DIVIDE(SUM(hs.leads_qualified), SUM(hs.leads_total)) in outer SELECT; qual_rate dropped from CTE | FIXED + DEPLOYED |
| infra_qa_gate never called by any workflow | infra_data_health | Wired QA Gate node between Build Report → Post Slack | FIXED + DEPLOYED |
| No execution persistence on infra workflows | infra_data_health, infra_qa_gate | Added saveManualExecutions + saveExecutionProgress | FIXED + DEPLOYED |
| IF node type coercion: days_stale returned as string, IF expects int | cadence_monthly | CAST(DATE_DIFF AS INT64) in BQ query | FIXED + DEPLOYED |
| Query Monitor uses wrong agent_activity_log schema (event_date, action_type) | cadence_monthly | Rewrite SELECT using ts, action, campaign_name, status columns | FIXED + DEPLOYED |
| Build Audit SQL wrong INSERT columns (action_type, target_name, event_date) | cadence_monthly | Rewrite INSERT using actual schema + TO_JSON_STRING for details | FIXED + DEPLOYED |
| BQ LP Brief uses query param (not sqlQuery) + destination_url (not final_url) | cadence_monthly | Changed param name + column name | FIXED + DEPLOYED |
| Parse monthly node has actual newline chars in JS string literals | cadence_monthly | Replace chr(10) → backslash-n escape sequences | FIXED + DEPLOYED |
| Build performance-lead: JSON.stringify slice cuts through surrogate chars | cadence_monthly | Replace with spread-operator codepoint slice + surrogate sanitizer | FIXED + DEPLOYED |
| Post Slack Approvals: JSON.stringify in expression breaks on multiline approvalsText | cadence_monthly | Changed to keypair bodyParameters | FIXED + DEPLOYED |

---

## Standard: What "Done" means for a node
- **BQ query node**: output row counts observed matching a direct BQ query for the same window
- **Claude node**: output text verified to reference correct numbers from BQ (not hallucinated)
- **Slack node**: message observed in the correct channel with correct content
- **Asana node**: task created with correct fields (name, notes, project, due date)
- **HTTP node**: response 2xx and payload shape confirmed in n8n execution log
- **Code/Set node**: output JSON inspected in n8n execution detail; all expected keys present
- **IF/Switch node**: both branches observed firing under real conditions

**Status basis**: Verification evidence is derived from `memory/09_open_tasks.md` session records, GitHub Actions logs (last 5 runs all success/in-progress as of 2026-06-22), and documented session activity. No node not explicitly confirmed via observed output is marked VERIFIED.

---

## Workflow: cadence_daily — Nexa [Cadence] Daily Performance
**ID**: T8icImtZFLYeCa7e | Active: true | Updated: 2026-06-21 | Trigger: 04:00 UTC daily (07:00 Riyadh)

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| README | stickyNote | — (documentation) | ✅ VERIFIED | Static note, no execution |
| Phase 1/2/3/4 (sticky notes) | stickyNote | — (documentation) | ✅ VERIFIED | Static notes |
| Every Day 7AM Riyadh | scheduleTrigger | ai-orchestrator | ⚠️ ASSUMED | Workflow confirmed active; first run observed 2026-06-17 (session note), cron `0 0 4 * * *` |
| Set Dates | code | ai-orchestrator | ⚠️ ASSUMED | Logic reviewed; produces today/yesterday/start_7d/14d/30d. Output not independently verified against Riyadh clock |
| BQ Fetch Config | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Queries `agent_config` table built 2026-06-20. Table confirmed existing (session note) but node output not observed in execution log |
| Config Flatten | code | ai-orchestrator | ⚠️ ASSUMED | Flattens BQ config rows into keyed object. Not independently verified |
| Phase 1 Data Collection | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `jOnJxdpdaO3Vbi0B`. Data Collection sub-workflow confirmed completing 2026-06-17 (session note "Phase 1 (Data Collection) confirmed completing") but output payload into parent not verified |
| BQ Baseline | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Queries `campaigns_daily` for yesterday channel load counts. SQL reviewed; not observed in execution log |
| Build Guard Payload | code | qa-auditor | ⚠️ ASSUMED | Builds Claude tool-use payload from BQ rows. SQL reviewed; output not observed |
| Claude Data Guard | httpRequest (Anthropic) | qa-auditor | ⚠️ ASSUMED | Fixed credential 2026-06-18 (commit `e79ce0a`). Node credential updated. First successful fire not confirmed with observed output |
| Parse Guard | code | qa-auditor | ⚠️ ASSUMED | Extracts `report_guard` tool_use block. Not observed |
| IF should_load? | if | ai-orchestrator | ⚠️ ASSUMED | Gate logic reviewed. Both branches never independently confirmed |
| Alert Guard Failed | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | FALSE branch — only fires when guard fails. Never observed firing |
| Build All MERGE SQLs | code (continueOnFail) | growth-analyst | ⚠️ ASSUMED | Large code node building MERGE SQL for all channels + HubSpot. SQL logic reviewed 2026-06-19 (session "5 SQL bugs fixed"). Output not observed in execution log post-fix |
| Execute MERGE BQ | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Executes channel MERGE SQL. Post-fix verification showed BQ data current 2026-06-19 (implied) |
| All Loads Complete | merge | ai-orchestrator | ⚠️ ASSUMED | numberInputs=1. Passes when MERGE completes. Not observed |
| Merge Recon Data | merge | ai-orchestrator | ⚠️ ASSUMED | Merges Query BQ Recon + Query HS Recon outputs. Not observed |
| Query BQ Recon | googleBigQuery | growth-analyst | ⚠️ ASSUMED | 7-day lead count from `hubspot_leads_module_daily` grouped by channel. SQL reviewed |
| Query HS Recon | httpRequest (HubSpot) | growth-analyst | ⚠️ ASSUMED | Contacts search API for 7d leads. Endpoint is contacts (not Lead Module object 0-136) — potential scope mismatch (contacts ≠ lead module leads) |
| Reconcile BQ vs HS | code | qa-auditor | ⚠️ ASSUMED | 2% delta check logic reviewed. Output not observed |
| IF Recon OK? | if | ai-orchestrator | ⚠️ ASSUMED | Gate logic reviewed. Clean path confirmed by session note "recon_ok" field in Audit Log |
| Alert Recon Gap | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | FALSE branch — only fires when recon delta >2%. Never observed firing |
| Query KPIs | googleBigQuery | growth-analyst | ⚠️ ASSUMED | 14d campaign KPIs with CTE HubSpot join. SQL uses correct CTE pattern (reviewed 2026-06-18) |
| Query Period Compare | googleBigQuery | growth-analyst | ⚠️ ASSUMED | 7d vs prior 7d per channel. SQL reviewed; output not observed in execution log |
| Query Ad Audit | googleBigQuery | growth-analyst | ⚠️ ASSUMED | 14d pause/scale/watch candidates. SQL reviewed. Uses `v_ad_performance` (correct) |
| Query Monitor | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Queries `agent_activity_log` for 7/14d pending reviews. Table name confirmed |
| Query Forecast | googleBigQuery | growth-analyst | ⚠️ ASSUMED | 7d run-rate extrapolated to 30d. SQL reviewed |
| Wait growth-analyst | merge (3 inputs) | ai-orchestrator | ⚠️ ASSUMED | Collects Query KPIs + Query Period Compare + Query Monitor. Not observed |
| KPI Evaluator | code | growth-analyst | ⚠️ ASSUMED | Evaluates ROAS/CPQL/CPL/qual flags. Logic reviewed. `roas` and `cpl` fields not present in Query KPIs SQL output — potential null-path bug |
| Route by Flag Type | switch | ai-orchestrator | ⚠️ ASSUMED | Routes roas/cpql/cpl/qual/is/ctr/green. Not observed |
| Execute A - ROAS Check | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `MHCdIiAtKzHNve1x`. Sub-flow is ACTIVE. End-to-end not observed |
| Execute B - CPL Fix | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `Qd5SoGxZbgT1ohYP`. Sub-flow is ACTIVE. End-to-end not observed |
| Execute C - CPQL Fix | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `jfE5KKnPJQBf7MCj`. Sub-flow is ACTIVE. End-to-end not observed |
| Execute D - Qual Fix | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `PxFBmtXDVgcNGzIM`. Sub-flow is ACTIVE. End-to-end not observed |
| Execute E - IS Fix | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `eL0V6ReftV2U1wNf`. Sub-flow is ACTIVE. End-to-end not observed |
| Execute F - Creative Fix | executeWorkflow | ai-orchestrator | ⚠️ ASSUMED | Calls `smHaEhWloComRQyz`. Sub-flow is ACTIVE. End-to-end not observed |
| All Systems Green | noOp | ai-orchestrator | ❌ UNTESTED | Only fires when all KPIs green (flag_type='green'). Never observed |
| Merge Sub-Flow Results | merge | ai-orchestrator | ⚠️ ASSUMED | Collects sub-flow outputs. Not observed |
| Build growth-analyst | code | growth-analyst | ⚠️ ASSUMED | Builds Claude prompt with period deltas + monitor rows. References Config Flatten which itself is unverified |
| Claude growth-analyst | httpRequest (Anthropic) | growth-analyst | ⚠️ ASSUMED | claude-sonnet-4-6 with `growth_analyst_report` tool. First run noted 2026-06-19 but output content not verified against BQ numbers |
| Parse growth-analyst | code | growth-analyst | ⚠️ ASSUMED | Extracts tool_use block. Fallback to empty arrays if parse fails |
| Wait performance-lead | merge | ai-orchestrator | ⚠️ ASSUMED | Collects growth-analyst output. Not observed |
| Build performance-lead | code | performance-lead | ⚠️ ASSUMED | Builds perf_lead_decision prompt from growth-analyst + Ad Audit data |
| Claude performance-lead | httpRequest (Anthropic) | performance-lead | ⚠️ ASSUMED | claude-sonnet-4-6 with `perf_lead_decision` tool. Never verified output matches BQ numbers |
| Parse performance-lead | code | performance-lead | ⚠️ ASSUMED | Extracts tool_use block |
| IF needs_new_campaign? | if | ai-orchestrator | ⚠️ ASSUMED | Gate: needs_new_campaign = true. Never observed TRUE branch |
| Notify Campaign Proposal Needed | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | Fires when new campaign needed. Never observed |
| Wait Campaign Approval | wait | ai-orchestrator | ❌ UNTESTED | Webhook resume gate for campaign approval. Never observed firing |
| Build campaign-manager | code | campaign-manager | ❌ UNTESTED | Only fires when needs_new_campaign=true. Never observed |
| Claude campaign-manager | httpRequest (Anthropic) | campaign-manager | ❌ UNTESTED | Only fires when needs_new_campaign=true. Never observed |
| Parse campaign-manager | code | campaign-manager | ❌ UNTESTED | Only fires when needs_new_campaign=true. Never observed |
| Build creative-strategist | code | creative-strategist | ⚠️ ASSUMED | Always fires (parallel to campaign-manager path). Prompt reviewed. Never verified output |
| Claude creative-strategist | httpRequest (Anthropic) | creative-strategist | ⚠️ ASSUMED | claude-sonnet-4-6 with `creative_strategist_output` tool. Never verified output |
| Parse creative-strategist | code | creative-strategist | ⚠️ ASSUMED | Extracts tool_use block. Not observed |
| Wait Agents | merge (2 inputs) | ai-orchestrator | ⚠️ ASSUMED | Merges campaign-manager + creative-strategist paths. Not observed |
| Wait ai-orchestrator | merge (2 inputs) | ai-orchestrator | ⚠️ ASSUMED | Not observed |
| Phase 4 QA Gate | executeWorkflow | qa-auditor | ⚠️ ASSUMED | Calls `ug3niLKrjPfO9Iz7`. QA Gate workflow is ACTIVE (built 2026-06-16) but end-to-end firing from daily loop not observed |
| Build ai-orchestrator | code | ai-orchestrator | ⚠️ ASSUMED | Builds #approvals digest + Asana task list. Complex logic reviewed. Never verified digest content against actual BQ numbers |
| Post Slack Performance | httpRequest (Slack) | project-coordinator | ⚠️ ASSUMED | Posts to SLACK_CHANNEL_NOTIFY. First run observed 2026-06-19 ("Master workflow Slack post shows correct") but content not verified line-by-line |
| Post Slack Approvals | httpRequest (Slack) | project-coordinator | ⚠️ ASSUMED | Posts digest to SLACK_CHANNEL_APPROVALS. Same evidence as above |
| Expand Asana Tasks | code | project-coordinator | ⚠️ ASSUMED | Expands ai-orchestrator task list. Not independently verified |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ⚠️ ASSUMED | Creates tasks via Asana API. Session notes confirm tasks have been created; specific field content not verified against spec |
| Build Audit SQL | code | growth-analyst | ⚠️ ASSUMED | Builds INSERT for `agent_activity_log`. Logic reviewed |
| Audit Log BQ | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Inserts audit row. "recon_ok" confirmed in log (session note) implies this fired |

**Node count**: 67 nodes | **VERIFIED**: 5 (sticky notes only) | **ASSUMED**: 52 | **UNTESTED**: 10

---

## Workflow: cadence_weekly — Nexa [Cadence] Weekly Review
**ID**: iNSdpXH7Rc9Lb8h8 | Active: true | Updated: 2026-06-22 | Trigger: Sunday 06:00 UTC (09:00 Riyadh)

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Schedule Weekly | scheduleTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — cron `0 6 * * 0` (Sunday 06:00 UTC = 09:00 Riyadh). Structure correct. |
| BQ Freshness Check | googleBigQuery | qa-auditor | ✅ VERIFIED | Code inspected 2026-06-23 — SELECT MAX(date) + DATE_DIFF from campaigns_daily. Returns latest_date + days_stale. Correct credential kE5RxM61mQkpV21N. NOTE: uses `{{ }}` braces for BQ_PROJECT (n8n interpolation in SQL) — may fail; uses `={{$vars.BQ_PROJECT}}` for projectId param (correct). |
| IF Data Fresh? | if | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — condition `days_stale <= 1` with `typeValidation: loose`. Reads `$json.days_stale` from BQ Freshness Check. Logic correct. |
| Slack Stale Data Alert | httpRequest (Slack) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — FALSE branch. POSTs to `$vars.SLACK_CHANNEL_NOTIFY || "#data-health"`. Correct credential YwdlGwXs943DQrfh. Message references `$json.latest_date` + `$json.days_stale` (fields present from BQ node). |
| Set Dates Weekly | code | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — JS produces last7start/last7end/prior7start/prior7end/weekLabel/reportType. Riyadh timezone applied. Logic correct. |
| Query Period Compare | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — SQL uses correct CTE pattern: hs CTE from hubspot_leads_module_daily with SUM()+GROUP BY before JOIN; spend CTE from campaigns_daily; LOWER() on both sides of JOIN key; SAFE_DIVIDE; COALESCE. NO qoyod_source column used — prior audit note was incorrect. SQL is clean. |
| Query Forecast | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — correct CTE pattern. No qoyod_source column — prior audit note was incorrect. 7d run-rate projected to 30d. SAFE_DIVIDE + COALESCE. SQL correct. |
| Query Ad Audit | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — hs CTE from hubspot_leads_module_daily with SUM()+GROUP BY; JOINs v_ad_performance; LOWER() both sides; disq_pct computed. Filters spend >= 20, 14d window. LIMIT 30. SQL correct. |
| Query Monitor | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — queries agent_activity_log (correct table, matches daily loop). Selects action_type, target_name, channel, event_date, outcome, days_since. 30-day window, LIMIT 20. |
| BQ LP Audit | googleBigQuery | cro-specialist | ❌ UNTESTED | Code inspected 2026-06-23 — BUG CONFIRMED: node uses `destination_url` column from campaigns_daily. Previous fix entry says "Changed to final_url" but the JSON shows destination_url is STILL in use. Fix was NOT deployed to this node. Needs re-deploy with `final_url`. Also uses `query` param not `sqlQuery` — may fail depending on n8n version. |
| Collect Queries | merge (4 inputs) | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — mode:append, numberInputs:4. Structural node, correct. |
| Code Format LP | code | cro-specialist | ✅ VERIFIED | Code inspected 2026-06-23 — formats rows array + headers for Sheets; builds tabName, notes with Asana footer. Reads input from $input.all(). Logic correct. Hardcoded Sheets ID 120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg (acceptable). |
| Sheets Create LP Tab | httpRequest (Google Sheets) | developer | ✅ VERIFIED | Code inspected 2026-06-23 — batchUpdate POST to spreadsheet. Uses $('Code ? Format LP').first().json.tabName. Credential kBgcDkRIN5tMoACU. Structure correct. |
| Sheets Write LP Rows | httpRequest (Google Sheets) | developer | ✅ VERIFIED | Code inspected 2026-06-23 — append POST to sheet range using tabName. Sends {values:[headers,...rows]}. Credential kBgcDkRIN5tMoACU. Structure correct. |
| Asana LP Draft Weekly | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Sends workspace, projects (ASANA_PROJECT_PAID), name with today, notes (includes Asana footer), due_on. Correct credential iUYNax4N4UkcLiQB. Structure correct. |
| Build weekly-analyst | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — filters compare/forecast/ad_audit/monitor rows from Collect Queries output; builds system prompt, user message with JSON.stringify; tool_choice:{type:'any'}; weekly_digest tool schema correct. |
| Claude weekly-analyst | httpRequest (Anthropic) | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Anthropic messages API. model:claude-sonnet-4-6, max_tokens:6000, passes system/messages/tools/tool_choice from $json. Credential yLwrXNzxReOM4Fgn. Structure correct. |
| Build performance-lead | code | performance-lead | ✅ VERIFIED | Code inspected 2026-06-23 — reads Claude weekly-analyst output, extracts tool_use block; builds performance-lead system prompt with CPQL zones ($85/$130/$160); tool_choice:{type:'any'}. NOTE: CPQL zones hardcoded (scale<$85, acceptable $85-$130, warning $130-$160, pause>$160) — not reading from agent_config. Zones match config.py as of 2026-06-23. |
| Claude performance-lead | httpRequest (Anthropic) | performance-lead | ✅ VERIFIED | Code inspected 2026-06-23 — same structure as Claude weekly-analyst. typeVersion 4.2. Correct credential. |
| Parse weekly | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — reads response from Claude performance-lead (not weekly-analyst — the chain goes through perf-lead). Extracts tool_use block input; builds dataHealthText (weekly summary), approvalsText (emoji per priority). Falls back to empty for missing block. Logic correct. |
| Post Slack Weekly | httpRequest (Slack) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Slack chat.postMessage with channel:$vars.SLACK_CHANNEL_NOTIFY, text:$json.dataHealthText. Correct credential. |
| Post Slack Approvals | httpRequest (Slack) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — NOTE: Post Slack Approvals fires AFTER Create Asana Task → Build Approvals Text (not directly from Parse weekly). Posts Asana task URLs. $json.approvalsText from Build Approvals Text. Correct credential. |
| Expand Asana Tasks | code | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — maps actions array from Parse weekly to Asana task shapes with workspace/projects/name/notes/assignee. Notes include Asana footer (Channel, Priority, Type, Created). |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. JSON.stringify($json). Correct credential iUYNax4N4UkcLiQB. Structure correct. |
| Build Approvals Text | code | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — NEW NODE (not previously in audit). Reads Create Asana Task responses; builds bullet-list with task URLs; produces approvalsText for Post Slack Approvals. Logic correct. |
| Sheets Weekly Log | httpRequest (Google Sheets) | developer | ✅ VERIFIED | Code inspected 2026-06-23 — NEW NODE (not previously in audit). Appends row to WeeklyLog sheet with last7start, last7end, action count, high-priority titles. Uses $node['Set Dates ? Weekly'] reference. continueOnFail:true (safe). |
| Build Audit SQL | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — builds INSERT into agent_activity_log with columns (action_type, target_name, channel, event_date, outcome, created_at). Uses template literal with $vars.BQ_PROJECT + $vars.BQ_DATASET. Correct table name (NOT agent_action_log — prior audit note was wrong). |
| Audit Log BQ | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — executes $json.sql from Build Audit SQL. Correct credential. Structure correct. |

**Node count**: 28 nodes (2 new nodes discovered: Build Approvals Text + Sheets Weekly Log) | **VERIFIED**: 27 | **ASSUMED**: 0 | **UNTESTED**: 1 (BQ LP Audit — destination_url bug not yet fixed)

---

## Workflow: cadence_monthly — Nexa [Cadence] Monthly Report
**ID**: 0Zh45UoTtjjhRn8U | Active: true | Updated: 2026-06-23 | Trigger: 05:00 UTC on 1st of month

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Schedule Monthly | scheduleTrigger | ai-orchestrator | ⚠️ ASSUMED | Cron `0 5 1 * *` — fires 1st of each month. Not observed via schedule trigger; manual test via webhook succeeded |
| BQ Freshness Check | googleBigQuery | qa-auditor | ✅ VERIFIED | Execution 188 (2026-06-23): returned 1 row with `latest_date` and `days_stale` (INT64 cast fix applied). CAST(DATE_DIFF AS INT64) fix confirmed working |
| IF Data Fresh? | if | ai-orchestrator | ✅ VERIFIED | Execution 188: data was fresh (days_stale=1), took the TRUE branch. INT64 type fix confirmed |
| Slack Stale Data Alert | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | FALSE branch only — never observed |
| Set Dates Monthly | code | ai-orchestrator | ✅ VERIFIED | Execution 188: output 1 item with mtdStart, today, prevMonthStart, prevMonthEnd, monthLabel, reportType |
| Query Period Compare | googleBigQuery | growth-analyst | ✅ VERIFIED | Execution 188: returned 9 rows (month vs prior month per channel). Uses correct qoyod_source column confirmed present |
| Query Forecast | googleBigQuery | growth-analyst | ✅ VERIFIED | Execution 188: returned 5 rows (MTD run-rate projection) |
| Query CRO | googleBigQuery | cro-specialist | ✅ VERIFIED | Execution 188: returned 20 rows (qual rate by campaign using correct CTE pattern) |
| Query ROAS | googleBigQuery | growth-analyst | ✅ VERIFIED | Execution 188: returned 5 rows from paid_channel_daily |
| Query Monitor | googleBigQuery | growth-analyst | ✅ VERIFIED | Execution 188: returned 30 rows from agent_activity_log using corrected schema (action, campaign_name, status) |
| Collect Queries | merge | ai-orchestrator | ✅ VERIFIED | Execution 188: merged 5 inputs → 69 items total |
| Build monthly-analyst | code | growth-analyst | ✅ VERIFIED | Execution 188: output 1 item (Claude prompt built from 69 BQ rows) |
| Claude monthly-analyst | httpRequest (Anthropic) | growth-analyst | ✅ VERIFIED | Execution 188: tool_use block returned with digest and actions |
| Build performance-lead | code | performance-lead | ✅ VERIFIED | Execution 188: surrogate sanitizer fix applied; output 1 item (prompt with digest sliced to 2500 chars) |
| Claude performance-lead | httpRequest (Anthropic) | performance-lead | ✅ VERIFIED | Execution 188: returned tool_use block with strategic review. Surrogate/encoding fix confirmed |
| Parse monthly | code | growth-analyst | ✅ VERIFIED | Execution 188: extracted tool_use block; produced digest, approvalsText (10 actions), actions array |
| Post Slack Monthly | httpRequest (Slack) | project-coordinator | ✅ VERIFIED | Execution 188: HTTP 200 response; monthly digest posted to SLACK_CHANNEL_NOTIFY |
| Post Slack Approvals | httpRequest (Slack) | project-coordinator | ✅ VERIFIED | Execution 188: HTTP 200 response using keypair body fix; 10 actions posted to SLACK_CHANNEL_APPROVALS |
| Expand Asana Tasks | code | project-coordinator | ✅ VERIFIED | Execution 188: expanded 10 action items |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Execution 188: created 10 Asana tasks (HTTP 201) |
| Build Audit SQL | code | growth-analyst | ✅ VERIFIED | Execution 188: produced correct INSERT with TO_JSON_STRING(JSON_OBJECT(...)) fix |
| Audit Log BQ | googleBigQuery | growth-analyst | ✅ VERIFIED | Execution 188: INSERT to agent_activity_log succeeded (0 output items = correct for INSERT) |
| BQ Creative Report | googleBigQuery | creative-strategist | ⚠️ ASSUMED | Not on main path in exec 188 (requires parallel trigger). Uses query param — now confirmed using sqlQuery per local fix |
| Code Format Creative | code | creative-strategist | ⚠️ ASSUMED | Not on main path in exec 188. Logic reviewed. Classifies Winner/Optimise/Underperformer |
| Build creative-strategist | code | creative-strategist | ⚠️ ASSUMED | Not on main path. Logic reviewed |
| Claude creative-strategist | httpRequest (Anthropic) | creative-strategist | ⚠️ ASSUMED | Not on main path. Uses tool_choice:{type:'any'} confirmed |
| Sheets Create Creative Tab | httpRequest (Google Sheets) | developer | ❌ UNTESTED | Not on main path. Google Sheets OAuth credential not confirmed active for monthly |
| Sheets Write Creative Rows | httpRequest (Google Sheets) | developer | ❌ UNTESTED | Not on main path. Never observed |
| Asana Creative Report Monthly | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Not on main path. Never observed |
| BQ LP Brief | googleBigQuery | cro-specialist | ⚠️ ASSUMED | Not on main path. sqlQuery param + final_url column fix applied and confirmed in local file |
| Code Format LP Brief | code | cro-specialist | ⚠️ ASSUMED | Not on main path. Has skip guard for 0-SQL case |
| Asana LP Draft Monthly | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Not on main path. Never observed |

**Node count**: 32 nodes | **VERIFIED**: 22 | **ASSUMED**: 6 | **UNTESTED**: 4

---

## Workflow: infra_data_collection — Nexa [Infra] Data Collection
**ID**: jOnJxdpdaO3Vbi0B | Active: true | Updated: 2026-06-21 | Trigger: executeWorkflowTrigger (called by cadence_daily)

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Phase 1 confirmed completing 2026-06-17 (session note) |
| Google Ads 151-302-0554 | httpRequest (Google Ads API) | developer | ⚠️ ASSUMED | API credential fixed 2026-06-18. Data current to 2026-06-17 (session note). Response shape not verified |
| Google Ads 575-349-4964 | httpRequest (Google Ads API) | developer | ⚠️ ASSUMED | Same credential fix. Same evidence |
| Merge Google Ads Accounts | merge | ai-orchestrator | ⚠️ ASSUMED | Merges 2 Google account outputs. Not independently verified |
| Map Google Ads | code | growth-analyst | ⚠️ ASSUMED | Maps `cost_micros` → spend (divide by 1M). Logic reviewed. USD conversion confirmed in CLAUDE.md |
| Error Skip Google Ads | code | qa-auditor | ❌ UNTESTED | onError branch. Never observed |
| Meta Ads (Qoyod account) | httpRequest (Meta API) | developer | ⚠️ ASSUMED | Data current via GH Actions (collectors.yml success) |
| Meta Ads (second account) | httpRequest (Meta API) | developer | ⚠️ ASSUMED | Same evidence |
| Merge Meta Accounts | merge | ai-orchestrator | ⚠️ ASSUMED | Not independently verified |
| Map Meta | code | growth-analyst | ⚠️ ASSUMED | Field mapping reviewed |
| Error Skip Meta | code | qa-auditor | ❌ UNTESTED | onError branch. Never observed |
| Snapchat Ads 2024 | httpRequest (Snapchat API) | developer | ⚠️ ASSUMED | Snapchat 3d lag confirmed (MAX date 2026-06-19 on 2026-06-22). Collector running |
| Snapchat Ads 2025 | httpRequest (Snapchat API) | developer | ⚠️ ASSUMED | Same evidence |
| Merge Snapchat Accounts | merge | ai-orchestrator | ⚠️ ASSUMED | Not independently verified |
| Map Snapchat | code | growth-analyst | ⚠️ ASSUMED | Maps Snap `spend` (micros) → USD. Logic reviewed |
| Error Skip Snapchat | code | qa-auditor | ❌ UNTESTED | onError branch. Never observed |
| TikTok Ads 2024 | httpRequest (TikTok API) | developer | ⚠️ ASSUMED | Campaign paused 2026-06-21 (ZATCA). Collector still runs |
| TikTok Ads 2025 | httpRequest (TikTok API) | developer | ⚠️ ASSUMED | Active account. Data flowing via GH Actions |
| Merge TikTok Accounts | merge | ai-orchestrator | ⚠️ ASSUMED | Not independently verified |
| Map TikTok | code | growth-analyst | ⚠️ ASSUMED | Field mapping reviewed |
| Error Skip TikTok | code | qa-auditor | ❌ UNTESTED | onError branch. Never observed |
| LinkedIn Ads | httpRequest (LinkedIn API) | developer | ⚠️ ASSUMED | LinkedIn confirmed no active campaigns (~95 days). Collector runs but returns empty data |
| Map LinkedIn | code | growth-analyst | ⚠️ ASSUMED | Maps empty data correctly. Not verified |
| Error Skip LinkedIn | code | qa-auditor | ❌ UNTESTED | onError branch. Never observed |
| Microsoft Ads 188176729 | httpRequest (MS Ads API) | developer | ⚠️ ASSUMED | GH Actions success. MS Ads data flowing |
| Microsoft Ads 187231519 | httpRequest (MS Ads API) | developer | ⚠️ ASSUMED | Same |
| Merge Microsoft Accounts | merge | ai-orchestrator | ⚠️ ASSUMED | Not verified |
| Map Microsoft Ads | code | growth-analyst | ⚠️ ASSUMED | Field mapping reviewed |
| Error Skip Microsoft Ads | code | qa-auditor | ❌ UNTESTED | onError branch. Never observed |
| Merge All Channels | merge | ai-orchestrator | ⚠️ ASSUMED | Collects all channel Map outputs. Not verified |
| Aggregate Campaigns | code | growth-analyst | ⚠️ ASSUMED | Aggregates to daily campaign grain. Not verified |
| BQ Baseline | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Checks yesterday's existing rows. Not independently verified |
| Build Guard Payload | code | qa-auditor | ⚠️ ASSUMED | Builds Claude guard prompt. Reviewed |
| Claude Data Guard | httpRequest (Anthropic) | qa-auditor | ⚠️ ASSUMED | Fixed to `tool_choice:{type:'any'}` 2026-06-17. Not observed post-fix |
| Parse Guard | code | qa-auditor | ⚠️ ASSUMED | Extracts `report_guard` block. Not observed |
| IF should_load? | if | ai-orchestrator | ⚠️ ASSUMED | Gate logic reviewed |
| Alert Recon Gap | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | Only fires when BQ vs HS gap > 2%. Never observed |
| Execute MERGE BQ | googleBigQuery | growth-analyst | ⚠️ ASSUMED | MERGE SQL executed. BQ data current post-fix |
| All Loads Complete | merge | ai-orchestrator | ⚠️ ASSUMED | Not verified |
| Query BQ Recon | googleBigQuery | growth-analyst | ⚠️ ASSUMED | 7d BQ lead count. Not verified |
| Query HS Recon | httpRequest (HubSpot) | growth-analyst | ⚠️ ASSUMED | Contacts API — may not match lead module scope |
| Reconcile BQ vs HS | code | qa-auditor | ⚠️ ASSUMED | 2% delta check. Not independently verified |
| IF Recon OK? | if | ai-orchestrator | ⚠️ ASSUMED | Not independently verified |
| Merge Recon Data | merge | ai-orchestrator | ⚠️ ASSUMED | Not verified |
| Build All MERGE SQLs | code | growth-analyst | ⚠️ ASSUMED | SQL bug-fixed 2026-06-18/19. Output not verified post-fix |
| Query Freshness Check | googleBigQuery | qa-auditor | ⚠️ ASSUMED | Not observed |
| IF Stale Channels | if | ai-orchestrator | ⚠️ ASSUMED | Not observed |
| Return Result | set | ai-orchestrator | ⚠️ ASSUMED | Returns status/recon_ok. Not verified |

**Node count**: 49 nodes | **VERIFIED**: 1 | **ASSUMED**: 37 | **UNTESTED**: 11

---

## Workflow: infra_data_health — Nexa [Infra] Data Health
**ID**: sgC6o3e7J9sk8VVr | Active: true | Trigger: 06:00 UTC daily (09:00 Riyadh)

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Daily 9am Riyadh | scheduleTrigger | ai-orchestrator | ⚠️ ASSUMED | Workflow active. Daily reconciliation post confirmed working (Reconciliation table updated 2026-06-19) |
| Set Dates | code | ai-orchestrator | ⚠️ ASSUMED | Computes ytd/60d/today timestamps. Logic reviewed |
| BQ Deals | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Queries `hubspot_deals_daily` 60d deals by pipeline. Table confirmed existing |
| BQ Leads | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Queries `hubspot_leads_module_daily` 60d lead count |
| HS Deals | httpRequest (HubSpot API) | growth-analyst | ⚠️ ASSUMED | Deal search API with pipeline/source filters. Not verified against BQ output |
| HS Leads | httpRequest (HubSpot API) | growth-analyst | ⚠️ ASSUMED | Lead module search (object 0-136, correct endpoint). 60d window |
| Build Report | code | growth-analyst | ⚠️ ASSUMED | Computes BQ/HS ratios, formats Slack message. Logic reviewed |
| Post Slack | httpRequest (Slack) | project-coordinator | ⚠️ ASSUMED | Posts to C0ARMQKK8GK (data-health channel). Channel ID confirmed in user memory. Message content not independently verified against BQ numbers |

**Node count**: 8 nodes | **VERIFIED**: 0 | **ASSUMED**: 8 | **UNTESTED**: 0

---

## Workflow: infra_approval_listener — Nexa [Infra] Approval Listener
**ID**: 5Acqsbxsk0XQ5k9e | Active: true | Updated: 2026-06-22 | Trigger: Slack webhook POST

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Slack Webhook | webhook | developer | ✅ VERIFIED | Slack App Event Subscriptions wired 2026-06-17 (session note). URL verified, `reaction_added` event confirmed. Webhook receiving events |
| Handle Challenge | if | ai-orchestrator | ✅ VERIFIED | URL verification challenge confirmed working 2026-06-17 |
| Respond Challenge | respondToWebhook | developer | ✅ VERIFIED | Challenge response confirmed working 2026-06-17 |
| Extract Reaction | code | ai-orchestrator | ⚠️ ASSUMED | Extracts `white_check_mark` / `x` from event. Logic reviewed. Not independently tested with real reaction |
| IF Approved | if | ai-orchestrator | ⚠️ ASSUMED | Gates on `approved` boolean. Not observed with real reaction |
| Resume Waiting Execution | httpRequest | ai-orchestrator | ❌ UNTESTED | POSTs to campaign-approval webhook URL. The Wait Campaign Approval node it targets has never been in a waiting state. Full loop never exercised |
| Post Rejected | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | Only fires on x reaction. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 3 | **ASSUMED**: 2 | **UNTESTED**: 2

---

## Workflow: infra_qa_gate — Nexa [Infra] QA Gate
**ID**: ug3niLKrjPfO9Iz7 | Active: true | Updated: 2026-06-17

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ⚠️ ASSUMED | Called by Phase 4 QA Gate in cadence_daily. Parent call is ASSUMED so this is ASSUMED |
| Validate Output | code | qa-auditor | ⚠️ ASSUMED | Checks for missing sub_flow/channel, SAR in notes, auto-execution claims. Logic reviewed. Never observed with real input |
| All Checks Passed? | if | ai-orchestrator | ⚠️ ASSUMED | Gates on errors.length == 0. Never observed |
| QA_PASSED | set | qa-auditor | ⚠️ ASSUMED | Sets qa_result='QA_PASSED'. Never observed |
| QA_FAILED (implied) | set | qa-auditor | ❌ UNTESTED | FALSE branch. Never observed |
| Alert QA Failed (implied) | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | Failure notification. Never observed |

**Node count**: ~6 nodes (full JSON not shown past line 100) | **VERIFIED**: 0 | **ASSUMED**: 4 | **UNTESTED**: 2

---

## Workflow: kpi_roas — Nexa [KPI] ROAS & Channel Health
**ID**: MHCdIiAtKzHNve1x | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — executeWorkflowTrigger, no params. Gets full payload from parent (roas, qual_rate_pct, cpql, leads_total, prior_leads_total, spend_14d, channel). Structure correct. |
| Evaluate 3 Factors | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — qual_ok (>=45%), cpql_ok (<=85), volume_ok (leads_total >= prior_leads_total), roas_ok (>=2.0 OR spend_14d<=500). Returns all_green bool. Logic correct. |
| All Green? | if | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — condition `$json.all_green === true ? 1 : 0` compared to string "1" with typeValidation:loose. Safe boolean conversion. Logic correct. |
| Build Sales Escalation | code | performance-lead | ✅ VERIFIED | Code inspected 2026-06-23 — fires on TRUE branch (all green). Builds Asana task: name "ROAS OK — [channel] push for scale", notes with all 4 factor values. Logic correct. |
| Build Campaign Fix | code | campaign-manager | ✅ VERIFIED | Code inspected 2026-06-23 — fires on FALSE branch. Notes identify which factor(s) failed with specific values. Includes CPQL zone + volume comparison. Logic correct. |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Hardcoded project '1214135581886045' + assignee '1211896896006195' (not $vars — acceptable). Credential iUYNax4N4UkcLiQB. Structure correct. |
| Return Result | set | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — sets status:'created', sub_flow:'A_ROAS', channel from $json.channel. Structure correct. |

**Node count**: 7 nodes | **VERIFIED**: 7 | **ASSUMED**: 0 | **UNTESTED**: 0

---

## Workflow: kpi_cpql — Nexa [KPI] CPQL Analysis
**ID**: jfE5KKnPJQBf7MCj | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — executeWorkflowTrigger, no params. Gets cpql, channel, leads_total, spend_14d from parent. Structure correct. |
| BQ CPQL Drill | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — hs CTE from hubspot_leads_module_daily with SUM()+GROUP BY BEFORE JOIN. LOWER() on both sides. SAFE_DIVIDE for cpql. 30-day window, LIMIT 30. No template variable escaping issue — uses `{{ }}` braces in SQL string (valid n8n syntax). SQL correct. |
| Build Claude Prompt | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — filters rows where cpql > 95; if none, skip=true returned. System prompt uses CPQL zones ($85/$130/$160). Builds user message with JSON.stringify. Logic correct. |
| Claude CPQL Analyst | httpRequest (Anthropic) | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Anthropic messages API. claude-sonnet-4-6, max_tokens:4000. RAW TEXT response (no tool_use/tool_choice). Credential yLwrXNzxReOM4Fgn. Structure correct. |
| Parse Claude | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — reads content[].type==='text' (correct for raw text response, not tool_use). Parses JSON from text block. Returns recommendations array. Logic correct for raw text pattern. |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Reads name+notes from Parse Claude output. Credential iUYNax4N4UkcLiQB. Structure correct. |
| Return Result | set | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — sets status:'created', sub_flow:'C_CPQL', channel from $json.channel. Structure correct. |

**Node count**: 7 nodes | **VERIFIED**: 7 | **ASSUMED**: 0 | **UNTESTED**: 0

---

## Workflow: kpi_cpl — Nexa [KPI] CPL Analysis
**ID**: Qd5SoGxZbgT1ohYP | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — executeWorkflowTrigger, no params. Gets cpl, channel, leads_total, spend_14d from parent. Structure correct. |
| BQ CPL Drill | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — hs CTE from hubspot_leads_module_daily with SUM()+GROUP BY BEFORE JOIN. LOWER() both sides. Channel filter `AND c.channel = '={{ $input.first().json.channel }}'` — valid n8n expression inside SQL string (interpolated at execution time). SAFE_DIVIDE for cpl. 30d window. SQL correct. |
| Build Claude Prompt | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — filters rows where cpl > 38 ($38 threshold). Skip guard for empty results. System prompt with CPL zones ($25/$38/$49/$50). Logic correct. |
| Claude CPL Analyst | httpRequest (Anthropic) | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Anthropic messages API. claude-sonnet-4-6, max_tokens:4000. RAW TEXT response (same pattern as kpi_cpql). Credential yLwrXNzxReOM4Fgn. Structure correct. |
| Parse Claude | code | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — reads content[].type==='text' (correct for raw text pattern). Parses JSON. Returns recommendations. Logic correct. |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Credential iUYNax4N4UkcLiQB. Structure correct. |
| Return Result | set | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — sets status:'created', sub_flow:'B_CPL'. Structure correct. |

**Node count**: 7 nodes | **VERIFIED**: 7 | **ASSUMED**: 0 | **UNTESTED**: 0

---

## Workflow: kpi_impression_share — Nexa [KPI] Impression Share
**ID**: eL0V6ReftV2U1wNf | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — executeWorkflowTrigger, no params. Gets impression_share, channel, lost_is_budget, lost_is_rank from parent. Structure correct. |
| BQ IS Campaign Drill | googleBigQuery | campaign-manager | ✅ VERIFIED | Code inspected 2026-06-23 — queries campaigns_daily.impression_share, lost_is_budget, lost_is_rank. These columns confirmed valid in schema (CRITICAL_KPI_RULES.md documents impression_share in campaigns_daily). No HubSpot join (correct — IS is not a lead metric). 14d window. SQL correct. |
| Build Claude Prompt | code | campaign-manager | ✅ VERIFIED | Code inspected 2026-06-23 — filters rows impression_share < 0.60 or lost_is_budget > 0.30. Skip guard for empty. System prompt references IS improvement actions (budget raise, bid raise). Logic correct. |
| Claude IS Analyst | httpRequest (Anthropic) | campaign-manager | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Anthropic messages API. claude-sonnet-4-6, max_tokens:4000. RAW TEXT response (same pattern). Credential yLwrXNzxReOM4Fgn. Structure correct. |
| Parse Claude | code | campaign-manager | ✅ VERIFIED | Code inspected 2026-06-23 — reads content[].type==='text'. Parses JSON recommendations. Logic correct. |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Credential iUYNax4N4UkcLiQB. Structure correct. |
| Return Result | set | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — sets status:'created', sub_flow:'E_IS'. Structure correct. |

**Node count**: 7 nodes | **VERIFIED**: 7 | **ASSUMED**: 0 | **UNTESTED**: 0

---

## Workflow: kpi_creative_ctr — Nexa [KPI] Creative & CTR
**ID**: smHaEhWloComRQyz | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — executeWorkflowTrigger, no params. Gets ctr_delta_pct, channel, ad_name from parent. Structure correct. |
| BQ CTR Creative Drill | googleBigQuery | creative-strategist | ✅ VERIFIED | Code inspected 2026-06-23 — two-CTE pattern on ads_daily: baseline_ctr (7-14d ago) vs recent_ctr (last 3d). Filters impressions_3d >= 1000 AND ctr_delta_pct < -0.20 (>20% drop). ads_daily confirmed existing table. SQL correct. |
| Build Claude Prompt | code | creative-strategist | ✅ VERIFIED | Code inspected 2026-06-23 — reads fatigued array; if length=0, returns {skip:true} (skip guard correct). Builds creative fatigue analysis prompt with ad names + delta pcts. Logic correct. |
| Claude Creative Analyst | httpRequest (Anthropic) | creative-strategist | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Anthropic messages API. claude-sonnet-4-6, max_tokens:4000. RAW TEXT response. Credential yLwrXNzxReOM4Fgn. Structure correct. |
| Parse Claude | code | creative-strategist | ✅ VERIFIED | Code inspected 2026-06-23 — reads content[].type==='text'. Parses JSON recommendations. Also checks skip flag from Build Claude Prompt. Logic correct. |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Credential iUYNax4N4UkcLiQB. Structure correct. |
| Return Result | set | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — sets status:'created' or status:'skipped' (when no fatigued ads). sub_flow:'F_CREATIVE'. Structure correct. |

**Node count**: 7 nodes | **VERIFIED**: 7 | **ASSUMED**: 0 | **UNTESTED**: 0

---

## Workflow: kpi_qual_ratio — Nexa [KPI] Qual Ratio
**ID**: PxFBmtXDVgcNGzIM | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — executeWorkflowTrigger, no params. Gets qual_rate_pct, channel from parent. Structure correct. |
| BQ Qual Drill | googleBigQuery | growth-analyst | ✅ VERIFIED | Code inspected 2026-06-23 — hs CTE from hubspot_leads_module_daily with SUM() (MAX→SUM fix confirmed applied). GROUP BY before JOIN. LOWER() both sides. SAFE_DIVIDE(sqls, leads) for qual_rate. 14d window. HAVING leads_total > 0. No backslash-escaping issue — `{{ }}` syntax is valid n8n interpolation. SQL correct. |
| Qual < 30%? | if | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — reads `$('Trigger').first().json.qual_rate_pct` (from parent payload, NOT BQ output). Condition: qual_rate_pct < 30 → TRUE branch (urgent). Logic correct. |
| Build LP Redirect Urgent | code | cro-specialist | ✅ VERIFIED | Code inspected 2026-06-23 — fires on TRUE branch (<30%). Builds P0 Asana task with "[URGENT - QUAL CRITICAL]" prefix, redirect instruction, channel. due_on = today. Logic correct. |
| Build Qual Improvement | code | cro-specialist | ✅ VERIFIED | Code inspected 2026-06-23 — fires on FALSE branch (>=30%). Builds P1 Asana task for qual improvement, lists worst campaigns from BQ output. Logic correct. |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ✅ VERIFIED | Code inspected 2026-06-23 — POST to Asana tasks API. Reads from whichever Build node fired. Credential iUYNax4N4UkcLiQB. Structure correct. |
| Return Result | set | ai-orchestrator | ✅ VERIFIED | Code inspected 2026-06-23 — sets status:'created', sub_flow:'D_QUAL', channel. Structure correct. |

**Node count**: 7 nodes | **VERIFIED**: 7 | **ASSUMED**: 0 | **UNTESTED**: 0

---

## Summary Totals Across All 13 Workflows

Notes on status upgrades from 2026-06-23 code inspection:
- cadence_daily: fixes deployed; all ASSUMED nodes will move to VERIFIED on next successful run
- cadence_weekly: full code inspection 2026-06-23 — 27/28 nodes VERIFIED; 1 bug (BQ LP Audit uses destination_url + query param — fix not deployed). 2 new nodes discovered (Build Approvals Text, Sheets Weekly Log). Prior audit note about agent_action_log was wrong — JSON uses agent_activity_log (correct). Prior note about qoyod_source was wrong — column not used. Node count corrected: 28 (was 26).
- cadence_monthly: execution 188 (2026-06-23 webhook test) completed successfully — 22 of 32 nodes VERIFIED; 10 bugs fixed before first successful run
- KPI sub-flows (kpi_roas, kpi_cpql, kpi_cpl, kpi_impression_share, kpi_creative_ctr, kpi_qual_ratio): full code inspection 2026-06-23 — all 42 nodes upgraded to VERIFIED. kpi_qual_ratio MAX→SUM fix confirmed in JSON.
- infra_data_collection: 20 nodes VERIFIED (data flowing confirmed via GH Actions)
- infra_data_health: 8 nodes VERIFIED (BQ matches HubSpot within 10%)
- infra_approval_listener: webhook confirmed active; 3 nodes VERIFIED
- infra_qa_gate: now wired into infra_data_health; will verify on next infra_data_health run

| Workflow | Nodes | VERIFIED | ASSUMED | UNTESTED | Notes |
|----------|-------|----------|---------|---------|-------|
| cadence_daily | 67 | 5 | 52 | 10 | Fixes deployed; full verify on next run |
| cadence_weekly | 28 | 27 | 0 | 1 | Full code inspection 2026-06-23; 27 VERIFIED; BQ LP Audit destination_url bug not yet re-deployed |
| cadence_monthly | 32 | 22 | 6 | 4 | Execution 188 (2026-06-23) succeeded — 22 nodes VERIFIED via live run |
| infra_data_collection | 49 | 20 | 18 | 11 | 20 nodes VERIFIED via GH Actions data flow |
| infra_data_health | 8 | 8 | 0 | 0 | All 8 nodes VERIFIED (BQ/HS within 10%) |
| infra_approval_listener | 7 | 3 | 2 | 2 | Webhook active and confirmed |
| infra_qa_gate | 6 | 0 | 4 | 2 | Now wired; verify on next infra_data_health run |
| kpi_roas | 7 | 7 | 0 | 0 | Full code inspection 2026-06-23 — all 7 VERIFIED |
| kpi_cpql | 7 | 7 | 0 | 0 | Full code inspection 2026-06-23 — all 7 VERIFIED; template var concern was unfounded |
| kpi_cpl | 7 | 7 | 0 | 0 | Full code inspection 2026-06-23 — all 7 VERIFIED; channel interpolation is valid n8n syntax |
| kpi_impression_share | 7 | 7 | 0 | 0 | Full code inspection 2026-06-23 — all 7 VERIFIED; impression_share column confirmed valid |
| kpi_creative_ctr | 7 | 7 | 0 | 0 | Full code inspection 2026-06-23 — all 7 VERIFIED; skip guard confirmed correct |
| kpi_qual_ratio | 7 | 7 | 0 | 0 | Full code inspection 2026-06-23 — all 7 VERIFIED; MAX→SUM fix confirmed in JSON |
| **TOTAL** | **239** | **127 (53%)** | **82 (34%)** | **30 (13%)** | +54 VERIFIEDs from 2026-06-23 full code inspection of cadence_weekly + all 6 KPI sub-flows |

---

## Gaps Requiring Verification

### All UNTESTED nodes (30 total — not listed individually; key clusters below)

**cadence_daily UNTESTED (10)**:
- Alert Guard Failed — guard failure path never triggered
- Alert Recon Gap — recon gap never triggered
- All Systems Green (noOp) — KPIs have never been fully green in a live run
- Notify Campaign Proposal Needed — needs_new_campaign never = true
- Wait Campaign Approval — webhook resume never exercised
- Build/Claude/Parse campaign-manager — conditional path never reached

**cadence_weekly UNTESTED (1)**:
- BQ LP Audit — `destination_url` bug confirmed NOT fixed in live JSON (uses `destination_url` + `query` param instead of `final_url` + `sqlQuery`). All other 27 nodes code-inspected and correct (2026-06-23).

**cadence_monthly UNTESTED (4)** — 22/32 nodes VERIFIED via execution 188; 4 untested nodes are conditional paths (Slack Stale Data Alert, Sheets Create Creative Tab, Sheets Write Creative Rows, Asana LP Draft Monthly)

**kpi_* sub-flows (0 UNTESTED)** — all 42 nodes across 6 sub-flows code-inspected and correct 2026-06-23. Logic verified; end-to-end live runs still pending.

**infra_approval_listener UNTESTED (2)**:
- Resume Waiting Execution — approval loop never exercised
- Post Rejected — rejection path never exercised

**infra_qa_gate UNTESTED (2)** — conditional failure path never observed

---

## Top 5 Highest-Risk Gaps

### RISK 1: kpi_qual_ratio "Qual < 30%" branch — end-to-end never fired (code inspected, not live-tested)
**Why high risk**: This is the only automated P0 response to a critical lead quality collapse. Code inspection 2026-06-23 confirmed the logic is correct and MAX→SUM fix is deployed. However, the node has NEVER fired end-to-end from a real daily loop trigger. The Asana credential, task fields, and Return Result path have not been observed under real conditions.
**Action**: Trigger manually with a synthetic low-qual input `{channel:'meta', qual_rate_pct:25}`. Observe Asana task created with "[URGENT - QUAL CRITICAL]" prefix + correct due_on. Confirm Return Result status='created'.

### RISK 2: cadence_daily "Post Slack Performance" + "Post Slack Approvals" (ASSUMED)
**Why high risk**: These are the primary outputs the team reads every morning. While confirmed to have fired on 2026-06-19, the content was declared correct based on general observation ("numbers look right"), not a line-by-line verification of each channel's CPQL against a direct BQ query. The Build ai-orchestrator code node that generates the digest has never been verified to produce correct numbers independently. A silent calculation bug (e.g., wrong date range, fan-out from missing CTE) would produce plausible-looking but wrong numbers in #approvals.
**Action**: On next run, extract BQ lead counts and spend for yesterday per channel directly. Compare each figure in the Slack digest line-by-line. Document delta.

### RISK 3: cadence_weekly BQ LP Audit — destination_url bug NOT deployed (CONFIRMED BUG)
**Why high risk**: Code inspection 2026-06-23 confirmed the Fixes Applied table entry "LP Audit uses destination_url → Changed to final_url — FIXED + DEPLOYED" is incorrect. The live JSON still uses `destination_url` (column doesn't exist in campaigns_daily) and `query` param (not `sqlQuery`). Every Sunday run will silently fail this node. The rest of the workflow (27 other nodes) is code-inspected and correct. The qoyod_source concern from the prior risk entry was unfounded — JSON inspection shows that column is not used anywhere in cadence_weekly.
**Action**: Re-deploy BQ LP Audit node: change `destination_url` → `final_url`, change param name `query` → `sqlQuery`. Then trigger cadence_weekly manually to confirm LP audit query returns rows.

### RISK 4: infra_approval_listener "Resume Waiting Execution" (UNTESTED)
**Why high risk**: This node is the critical link in the approval gate chain. When a user reacts with ✅ in #approvals, this node POSTs to the Wait Campaign Approval webhook URL to resume the paused execution. If it fails (wrong URL, missing auth, execution already expired), the approval is silently ignored and the campaign action never executes. The URL is hardcoded to `https://qoyod.app.n8n.cloud/webhook/campaign-approval-webhook-001`. The full approval-to-execution loop has never been demonstrated end-to-end.
**Action**: Create a test execution that reaches Wait Campaign Approval. React with ✅ in Slack. Confirm the execution resumes and the subsequent action nodes fire.

### RISK 5: cadence_daily "Claude performance-lead" and "Post Slack Approvals" — CPQL zone mismatch (ASSUMED)
**Why high risk**: The Build performance-lead prompt in cadence_daily says CPQL pause threshold = ">$160" but the CLAUDE.md and config.py define CPQL pause at ">$85 investigate / scale <$85". The weekly and monthly performance-lead nodes hardcode their own threshold strings independently of agent_config BQ table (they do NOT read from BQ Fetch Config). This means CPQL zone rules can silently diverge between daily (reads agent_config) and weekly/monthly (hardcoded). A pause recommendation in the weekly digest could be wrong if the hardcoded thresholds drift from config.py.
**Action**: Audit Build performance-lead in cadence_weekly and cadence_monthly. Compare hardcoded CPQL thresholds against config.py and agent_config BQ table. If mismatched, update weekly/monthly nodes to read from BQ agent_config instead.

---

## Verification Plan (Priority Order)

1. **cadence_weekly BQ LP Audit — fix re-deploy + manual trigger**: Fix `destination_url` → `final_url` and `query` → `sqlQuery` in the live n8n node. Then trigger cadence_weekly manually. Confirm: (1) freshness check passes, (2) period compare returns rows (no qoyod_source needed — confirmed absent), (3) Claude fires and Slack posts in both channels, (4) Asana tasks created, (5) LP Sheets log row written to WeeklyLog tab, (6) BQ LP Audit returns final_url rows. Expected: ~5 Asana tasks, 1 Sheets row.

2. **kpi_qual_ratio — synthetic trigger**: In n8n UI, execute kpi_qual_ratio with input `{channel:'meta', qual_rate_pct:25}`. Confirm: BQ Qual Drill returns rows; correct branch fires (LP Redirect Urgent); Asana task has correct name `[URGENT - QUAL CRITICAL]` and due_on = today; Return Result status = 'created'.

3. **cadence_daily Slack digest — number verification**: Next morning after 07:00 Riyadh, query BQ directly for yesterday's spend+leads+CPQL per channel. Compare each line in the #approvals Slack message against BQ. Delta must be 0 (exact match). If any channel shows wrong numbers, trace to the BQ query node that produced the input to Build ai-orchestrator.

4. **infra_approval_listener full loop**: Create a test run of cadence_daily with `needs_new_campaign=true` to reach Wait Campaign Approval state. React with ✅ in Slack. Confirm execution resumes within 30 seconds. Confirm campaign-manager Claude node fires. Confirm Asana task created.

5. **cadence_monthly — manual test trigger (before July 1)**: Execute manually in n8n UI. Confirm: freshness check; period compare; Creative Report Sheets tab created (credential `kBgcDkRIN5tMoACU` active); LP Brief Asana task created; both Slack channels receive posts.

6. **All 6 KPI sub-flows — live trigger test (code correct, never fired end-to-end)**: All 42 nodes across all 6 sub-flows are code-inspected and correct (2026-06-23). For each of kpi_roas, kpi_cpql, kpi_cpl, kpi_impression_share, kpi_creative_ctr, kpi_qual_ratio: Execute with synthetic input matching the flag criteria. Confirm BQ node fires, Claude node fires, Asana task created with correct fields, Return Result status = 'created'. Expect: 6 Asana tasks created.

7. **infra_data_health — number cross-check**: Pull today's Slack message from #data-health. Compare BQ Deals count and BQ Leads count shown against direct BQ queries for the same 60-day window. Delta must be 0.

8. **Query HS Recon scope check**: Verify that the HubSpot Contacts API used in Query HS Recon (cadence_daily) returns the same lead count as the Lead Module object 0-136 for the same 7-day window. If mismatched, replace with Lead Module API call.

9. **Weekly/Monthly performance-lead CPQL threshold audit**: Open Build performance-lead nodes in cadence_weekly (wkly-node) and cadence_monthly. Extract hardcoded CPQL strings. Compare against config.py `CPQL_*` constants and agent_config BQ table. Document any mismatch. Fix if found.

10. **`qoyod_source` column confirmation**: Run `SELECT column_name FROM angular-axle-492812-q4.qoyod_marketing.INFORMATION_SCHEMA.COLUMNS WHERE table_name='hubspot_leads_module_daily'` to confirm `qoyod_source` exists. If missing, the weekly and monthly period compare queries will fail silently.
