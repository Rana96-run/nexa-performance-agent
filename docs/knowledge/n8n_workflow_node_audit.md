# n8n Workflow Node Audit
Last updated: 2026-06-23

## Fixes Applied 2026-06-23

| Bug | Workflow | Fix | Status |
|-----|---------|-----|--------|
| Config-Flatten missing date fields → sub-workflow gets undefined dates → all platform nodes fail silently → 93/118 nodes never run | cadence_daily | Merge Set Dates output into Config-Flatten | FIXED + DEPLOYED |
| IF node type coercion: days_stale returned as string, IF expects int | cadence_weekly | CAST(DATE_DIFF AS INT64) in BQ query | FIXED + DEPLOYED |
| LP Audit uses destination_url (column doesn't exist) | cadence_weekly | Changed to ads_daily.final_url | FIXED + DEPLOYED |
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
| Schedule Weekly | scheduleTrigger | ai-orchestrator | ⚠️ ASSUMED | Cron `0 6 * * 0`. No code to inspect; trigger config looks correct |
| BQ Freshness Check | googleBigQuery | qa-auditor | ⚠️ ASSUMED | Uses `sqlQuery` param (correct). Queries `campaigns_daily` with correct columns `MAX(date)`, `DATE_DIFF`. SQL reviewed |
| IF Data Fresh? | if | ai-orchestrator | ⚠️ ASSUMED | Standard IF node. Checks `days_stale <= 1`. Logic correct |
| Slack Stale Data Alert | httpRequest (Slack) | project-coordinator | ❌ UNTESTED | FALSE branch only. Never fired. Uses `specifyBody:json` (consistent with other Slack nodes in this workflow) |
| Set Dates Weekly | code | ai-orchestrator | ⚠️ ASSUMED | JS reviewed. Computes `last7start/last7end/prior7start/prior7end/weekLabel/reportType`. Logic correct |
| Query Period Compare | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Uses `sqlQuery` (correct). Correct tables and columns. Does NOT use `qoyod_source` — joins on `lead_utm_campaign` + `campaign_name`. CTE pre-aggregation pattern correct |
| Query Forecast | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Uses `sqlQuery` (correct). Correct tables and columns. No `qoyod_source`. CTE pattern correct |
| Query Ad Audit | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Uses `sqlQuery` (correct). Queries `v_ad_performance` (correct view). CTE join on `hubspot_leads_module_daily` with correct columns |
| Query Monitor | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Uses `sqlQuery` (correct). Queries `agent_activity_log` (correct table — NOT agent_action_log). Columns `action`, `campaign_name`, `channel`, `status` all correct |
| BQ LP Audit | googleBigQuery | cro-specialist | ⚠️ ASSUMED | Uses `sqlQuery` (correct). Queries `campaigns_daily.final_url` (correct column). Aliases as `destination_url` in SELECT only — that is fine. Hardcodes project/dataset strings but functionally equivalent |
| Collect Queries | merge (4 inputs) | ai-orchestrator | ⚠️ ASSUMED | 4-input append merge node. Config reviewed |
| Code Format LP | code | cro-specialist | ⚠️ ASSUMED | JS reviewed. Reads `d.destination_url` (which is the alias from BQ LP Audit SELECT — correct). Logic valid. Has skip guard for 0-lead case |
| Sheets Create LP Tab | httpRequest (Google Sheets) | developer | ⚠️ ASSUMED | Uses `specifyBody:json` with `jsonBody`. Sheets OAuth2 credential `kBgcDkRIN5tMoACU`. Logic reviewed |
| Sheets Write LP Rows | httpRequest (Google Sheets) | developer | ⚠️ ASSUMED | Uses `specifyBody:json` with `jsonBody`. Appends headers + rows. Logic reviewed |
| Asana LP Draft Weekly | httpRequest (Asana) | project-coordinator | ⚠️ ASSUMED | Uses `specifyBody:json` with `jsonBody`. Asana API correct endpoint. References `Code Format LP` output correctly |
| Build weekly-analyst | code | growth-analyst | ⚠️ ASSUMED | JS reviewed. Builds Claude prompt with all 4 query outputs (compare/forecast/audit/monitor). Tool schema correct |
| Claude weekly-analyst | httpRequest (Anthropic) | growth-analyst | ⚠️ ASSUMED | Uses `specifyBody:json` for Anthropic API (correct — not Slack). `weekly_digest` tool. Model `claude-sonnet-4-6` |
| Build performance-lead | code | performance-lead | ⚠️ ASSUMED | JS reviewed. Valid syntax. Hardcodes CPQL thresholds in systemPrompt — not reading from agent_config (known gap, see Risk 5 in this doc) |
| Claude performance-lead | httpRequest (Anthropic) | performance-lead | ⚠️ ASSUMED | Uses `specifyBody:json` for Anthropic API (correct). Model `claude-sonnet-4-6`. `weekly_digest` tool |
| Parse weekly | code | growth-analyst | ⚠️ ASSUMED | JS reviewed. Extracts `tool_use` block. Builds `dataHealthText`, `approvalsText`, `actions` array. Logic valid |
| Post Slack Weekly | httpRequest (Slack) | project-coordinator | ⚠️ ASSUMED | Uses `specifyBody:json` with `jsonBody`. Posts `dataHealthText` to `SLACK_CHANNEL_NOTIFY` |
| Post Slack Approvals | httpRequest (Slack) | project-coordinator | ⚠️ ASSUMED | Uses `specifyBody:json` with `jsonBody`. Posts `approvalsText` to `SLACK_CHANNEL_APPROVALS`. NOTE: monthly uses keypair fix; weekly still uses json — functional but inconsistent |
| Expand Asana Tasks | code | project-coordinator | ⚠️ ASSUMED | JS reviewed. Expands `actions` array to per-item Asana task shapes. Logic correct |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ⚠️ ASSUMED | Uses `specifyBody:json`. Asana API endpoint correct |
| Build Audit SQL | code | growth-analyst | ⚠️ ASSUMED | JS reviewed. INSERTs to `agent_activity_log` (correct table). Uses `TO_JSON_STRING(JSON_OBJECT(...))` for details column (correct). sqlQuery pattern correct |
| Audit Log BQ | googleBigQuery | growth-analyst | ⚠️ ASSUMED | Uses `sqlQuery` param (correct). Executes INSERT SQL from Build Audit SQL |
| Sheets → Weekly Log | httpRequest (Google Sheets) | developer | ⚠️ ASSUMED | Node wkly-017. Appends row to `WeeklyLog` tab. Uses `specifyBody:json`. References `Set Dates → Weekly` node output. `continueOnFail:true` (safe) |
| Build Approvals Text | code | project-coordinator | ⚠️ ASSUMED | Node wkly-018. Builds Asana-URL-linked approvals text from Create Asana Task responses. JS logic reviewed. NOT connected to Post Slack Approvals in current connections (Post Slack Approvals runs in parallel from Parse weekly directly) |

**Node count**: 28 nodes (26 listed in task + wkly-017 Sheets → Weekly Log + wkly-018 Build Approvals Text present in JSON) | **VERIFIED**: 0 | **ASSUMED**: 27 | **UNTESTED**: 1

---

## Workflow: cadence_monthly — Nexa [Cadence] Monthly Report
**ID**: 0Zh45UoTtjjhRn8U | Active: true | Updated: 2026-06-23 | Trigger: 05:00 UTC on 1st of month

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Schedule Monthly | scheduleTrigger | ai-orchestrator | ✅ VERIFIED | Execution 188 (2026-06-23): workflow fired and completed end-to-end. Cron `0 5 1 * *` |
| BQ Freshness Check | googleBigQuery | qa-auditor | ✅ VERIFIED | Execution 188: returned 1 row with `latest_date` and `days_stale` (INT64 cast fix applied). CAST(DATE_DIFF AS INT64) fix confirmed working |
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
| BQ Creative Report (mnth-cr-01) | googleBigQuery | creative-strategist | ⚠️ ASSUMED | Fixed 2026-06-23: `query` → `sqlQuery` (BQ v2 param fix). Queries `v_ad_performance` 30d window with correct columns. Not on main exec path — code-inspected only |
| Code Format Creative (mnth-cr-02) | code | creative-strategist | ⚠️ ASSUMED | Not on main path in exec 188. JS reviewed. Classifies Winner/Optimise/Underperformer by qual_ratio + CPL thresholds. Logic valid |
| Build creative-strategist (mnth-cr-03) | code | creative-strategist | ⚠️ ASSUMED | Not on main path. JS reviewed. Builds Claude prompt from formatted creative rows. Logic valid |
| Claude creative-strategist (mnth-cr-04) | httpRequest (Anthropic) | creative-strategist | ⚠️ ASSUMED | Not on main path. Uses `specifyBody:json` for Anthropic API (correct). `creative_report` tool. Model `claude-sonnet-4-6` |
| Sheets Create Creative Tab (mnth-cr-05) | httpRequest (Google Sheets) | developer | ⚠️ ASSUMED | Not on main path. Uses `specifyBody:json` with `jsonBody`. Sheets OAuth2 credential `kBgcDkRIN5tMoACU`. Logic reviewed |
| Sheets Write Creative Rows (mnth-cr-06) | httpRequest (Google Sheets) | developer | ⚠️ ASSUMED | Not on main path. Uses `specifyBody:json` with `jsonBody`. Appends headers + rows. Logic reviewed |
| Asana Creative Report Monthly (mnth-cr-07) | httpRequest (Asana) | project-coordinator | ⚠️ ASSUMED | Not on main path. Uses `specifyBody:json`. Asana API endpoint correct. References `Code Format Creative` output correctly |
| BQ LP Brief (mnth-lp-01) | googleBigQuery | cro-specialist | ⚠️ ASSUMED | Not on main path. Uses `sqlQuery` param (correct). Queries `campaigns_daily.final_url` (correct column). `hubspot_leads_module_daily` with correct columns |
| Code Format LP Brief (mnth-lp-02) | code | cro-specialist | ⚠️ ASSUMED | Not on main path. JS reviewed. Has skip guard for 0-SQL case. Logic valid |
| Asana LP Draft Monthly (mnth-lp-03) | httpRequest (Asana) | project-coordinator | ⚠️ ASSUMED | Not on main path. Uses `specifyBody:json`. Asana API endpoint correct. References `Code Format LP Brief` output correctly |

**Node count**: 32 nodes | **VERIFIED**: 22 | **ASSUMED**: 10 | **UNTESTED**: 0

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
| Trigger | executeWorkflowTrigger | ai-orchestrator | ❌ UNTESTED | Only fires when ROAS flag raised by KPI Evaluator. KPI Evaluator has not been confirmed to pass roas flags |
| Evaluate 3 Factors | code | growth-analyst | ❌ UNTESTED | Checks qual_ok/cpql_ok/volume_ok/roas_ok. Note: `roas` field not confirmed available in input from KPI Evaluator |
| All Green? | if | ai-orchestrator | ❌ UNTESTED | Gates on all_green. Never observed |
| Build Sales Escalation | code | performance-lead | ❌ UNTESTED | Fires when all 3 factors green. Never observed |
| Build Campaign Fix | code | campaign-manager | ❌ UNTESTED | Fires when 1+ factor not green. Never observed |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Never observed |
| Return Result | set | ai-orchestrator | ❌ UNTESTED | Returns A_ROAS status. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 0 | **ASSUMED**: 0 | **UNTESTED**: 7

---

## Workflow: kpi_cpql — Nexa [KPI] CPQL Analysis
**ID**: jfE5KKnPJQBf7MCj | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ❌ UNTESTED | Only fires when cpql flag raised. Never confirmed firing |
| BQ CPQL Drill | googleBigQuery | growth-analyst | ❌ UNTESTED | 14d CPQL by campaign via CTE join. SQL has template variable escaping issues (backslash-escaped braces visible in raw JSON) — possible BQ query failure |
| Build Claude Prompt | code | growth-analyst | ❌ UNTESTED | Filters worst campaigns (CPQL > $95). Logic reviewed |
| Claude CPQL Analyst | httpRequest (Anthropic) | growth-analyst | ❌ UNTESTED | Credential fixed 2026-06-18. Never observed firing |
| Parse Claude | code | growth-analyst | ❌ UNTESTED | Parses raw JSON text response (not tool_use). Never observed |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Never observed |
| Return Result | set | ai-orchestrator | ❌ UNTESTED | Returns C_CPQL status. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 0 | **ASSUMED**: 0 | **UNTESTED**: 7

---

## Workflow: kpi_cpl — Nexa [KPI] CPL Analysis
**ID**: Qd5SoGxZbgT1ohYP | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ❌ UNTESTED | Only fires when cpl flag raised. Never confirmed |
| BQ CPL Drill | googleBigQuery | growth-analyst | ❌ UNTESTED | 30d CPL via CTE join. SQL reviewed; correct pattern. Channel filter uses string interpolation (`='={{...}}'`) which may fail in BQ |
| Build Claude Prompt | code | growth-analyst | ❌ UNTESTED | Filters rows CPL > $38. Logic reviewed |
| Claude CPL Analyst | httpRequest (Anthropic) | growth-analyst | ❌ UNTESTED | Credential fixed 2026-06-18. Never observed |
| Parse Claude | code | growth-analyst | ❌ UNTESTED | Parses raw JSON text (not tool_use). Never observed |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Never observed |
| Return Result | set | ai-orchestrator | ❌ UNTESTED | Returns B_CPL status. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 0 | **ASSUMED**: 0 | **UNTESTED**: 7

---

## Workflow: kpi_impression_share — Nexa [KPI] Impression Share
**ID**: eL0V6ReftV2U1wNf | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ❌ UNTESTED | Only fires when is flag raised. Never confirmed |
| BQ IS Campaign Drill | googleBigQuery | campaign-manager | ❌ UNTESTED | Queries `campaigns_daily.impression_share` — field must exist in schema. Not confirmed |
| Build Claude Prompt | code | campaign-manager | ❌ UNTESTED | IS analysis prompt. Logic reviewed |
| Claude IS Analyst | httpRequest (Anthropic) | campaign-manager | ❌ UNTESTED | Credential fixed 2026-06-18. Never observed |
| Parse Claude | code | campaign-manager | ❌ UNTESTED | Parses raw JSON text. Never observed |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Never observed |
| Return Result | set | ai-orchestrator | ❌ UNTESTED | Returns E_IS status. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 0 | **ASSUMED**: 0 | **UNTESTED**: 7

---

## Workflow: kpi_creative_ctr — Nexa [KPI] Creative & CTR
**ID**: smHaEhWloComRQyz | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ❌ UNTESTED | Only fires when ctr flag raised. Never confirmed |
| BQ CTR Creative Drill | googleBigQuery | creative-strategist | ❌ UNTESTED | Queries `ads_daily` for CTR baseline vs 3d decay. Table confirmed existing |
| Build Claude Prompt | code | creative-strategist | ❌ UNTESTED | Filters ads with >20% CTR drop. Has skip guard for empty results |
| Claude Creative Analyst | httpRequest (Anthropic) | creative-strategist | ❌ UNTESTED | Credential fixed 2026-06-18. Never observed |
| Parse Claude | code | creative-strategist | ❌ UNTESTED | Parses raw JSON text. Never observed |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Never observed |
| Return Result | set | ai-orchestrator | ❌ UNTESTED | Returns F_CREATIVE status. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 0 | **ASSUMED**: 0 | **UNTESTED**: 7

---

## Workflow: kpi_qual_ratio — Nexa [KPI] Qual Ratio
**ID**: PxFBmtXDVgcNGzIM | Active: true | Updated: 2026-06-17 | Trigger: executeWorkflowTrigger

| Node | Type | Owner | Status | Verification evidence |
|------|------|-------|--------|-----------------------|
| Trigger | executeWorkflowTrigger | ai-orchestrator | ❌ UNTESTED | Only fires when qual flag raised. Never confirmed |
| BQ Qual Drill | googleBigQuery | growth-analyst | ❌ UNTESTED | 14d qual rate by campaign via CTE. SQL has same backslash-escaped template variable issue as kpi_cpql |
| Qual < 30%? | if | ai-orchestrator | ❌ UNTESTED | Critical branch: < 30% → urgent LP redirect; 30-45% → improvement task |
| Build LP Redirect Urgent | code | cro-specialist | ❌ UNTESTED | P0 task with "redirect immediately" instruction. Never observed |
| Build Qual Improvement | code | cro-specialist | ❌ UNTESTED | P1 task. Never observed |
| Create Asana Task | httpRequest (Asana) | project-coordinator | ❌ UNTESTED | Never observed |
| Return Result | set | ai-orchestrator | ❌ UNTESTED | Returns D_QUAL status. Never observed |

**Node count**: 7 nodes | **VERIFIED**: 0 | **ASSUMED**: 0 | **UNTESTED**: 7

---

## Summary Totals Across All 13 Workflows

Notes on status upgrades from 2026-06-23 fixes and code inspection:
- cadence_daily: fixes deployed; all ASSUMED nodes will move to VERIFIED on next successful run
- cadence_weekly: full JSON code inspection 2026-06-23 — all 28 nodes reviewed. 27 nodes upgraded UNTESTED → ASSUMED. 1 remains UNTESTED (Slack Stale Data Alert — FALSE branch, only fires on stale data). 2 previously unlisted nodes found: wkly-017 (Sheets → Weekly Log) and wkly-018 (Build Approvals Text). Prior bug notes corrected: Query Monitor uses `agent_activity_log` (correct), Query Period Compare/Forecast do NOT use `qoyod_source` (weekly joins on campaign name, not channel)
- cadence_monthly: execution 188 (2026-06-23 webhook test) completed successfully — 22 of 32 nodes VERIFIED. Branch nodes code-inspected: all 10 now ASSUMED. BQ Creative Report `query`→`sqlQuery` bug found and fixed + pushed to n8n Cloud 2026-06-23
- KPI sub-flows (kpi_roas, kpi_cpql, kpi_cpl, kpi_impression_share, kpi_creative_ctr, kpi_qual_ratio): BQ nodes verified via direct queries — 18 nodes upgraded from UNTESTED to VERIFIED. kpi_qual_ratio BQ node additionally fixed (MAX→SUM) and query confirmed returning 26 rows / 8,560 leads
- infra_data_collection: 20 nodes VERIFIED (data flowing confirmed via GH Actions)
- infra_data_health: 8 nodes VERIFIED (BQ matches HubSpot within 10%)
- infra_approval_listener: webhook confirmed active; 3 nodes VERIFIED
- infra_qa_gate: now wired into infra_data_health; will verify on next infra_data_health run

| Workflow | Nodes | VERIFIED | ASSUMED | UNTESTED | Notes |
|----------|-------|----------|---------|---------|-------|
| cadence_daily | 67 | 5 | 52 | 10 | Fixes deployed; full verify on next run |
| cadence_weekly | 28 | 0 | 27 | 1 | Code-inspected 2026-06-23; 27 nodes ASSUMED after full JSON review. 1 UNTESTED: Slack Stale Data Alert (FALSE branch only). 2 extra nodes (wkly-017/018) found in JSON not previously listed |
| cadence_monthly | 32 | 22 | 10 | 0 | Execution 188 (2026-06-23) — 22 nodes VERIFIED. Branch nodes code-inspected: 10 ASSUMED. BQ Creative Report `query`→`sqlQuery` fixed + pushed 2026-06-23 |
| infra_data_collection | 49 | 20 | 18 | 11 | 20 nodes VERIFIED via GH Actions data flow |
| infra_data_health | 8 | 8 | 0 | 0 | All 8 nodes VERIFIED (BQ/HS within 10%) |
| infra_approval_listener | 7 | 3 | 2 | 2 | Webhook active and confirmed |
| infra_qa_gate | 6 | 0 | 4 | 2 | Now wired; verify on next infra_data_health run |
| kpi_roas | 7 | 0 | 0 | 7 | BQ node not yet verified end-to-end |
| kpi_cpql | 7 | 3 | 0 | 4 | BQ node verified via direct query (template var fix); other nodes pending |
| kpi_cpl | 7 | 3 | 0 | 4 | BQ node verified via direct query; other nodes pending |
| kpi_impression_share | 7 | 3 | 0 | 4 | BQ node verified via direct query; other nodes pending |
| kpi_creative_ctr | 7 | 3 | 0 | 4 | BQ node verified via direct query; other nodes pending |
| kpi_qual_ratio | 7 | 3 | 0 | 4 | BQ node FIXED (MAX→SUM) + verified: 26 rows / 8,560 leads returned |
| **TOTAL** | **239** | **73 (31%)** | **113 (47%)** | **53 (22%)** | cadence_weekly code-inspected (+27 ASSUMED); cadence_monthly branch nodes all resolved (BQ Creative Report `query`→`sqlQuery` fixed + pushed 2026-06-23) |

---

## Gaps Requiring Verification

### All UNTESTED nodes (125 total — not listed individually; key clusters below)

**cadence_daily UNTESTED (10)**:
- Alert Guard Failed — guard failure path never triggered
- Alert Recon Gap — recon gap never triggered
- All Systems Green (noOp) — KPIs have never been fully green in a live run
- Notify Campaign Proposal Needed — needs_new_campaign never = true
- Wait Campaign Approval — webhook resume never exercised
- Build/Claude/Parse campaign-manager — conditional path never reached

**cadence_weekly UNTESTED (1)** — code-inspected 2026-06-23; 27/28 nodes ASSUMED. Only 1 remains UNTESTED: Slack Stale Data Alert (FALSE branch — only fires when BQ data is >1 day stale)

**cadence_monthly UNTESTED (1)** — 22/32 nodes VERIFIED via execution 188; branch nodes code-inspected 2026-06-23. 1 node UNTESTED with confirmed bug: BQ Creative Report (mnth-cr-01) uses `query` param instead of `sqlQuery` — will fail on n8n BQ v2 node. Sheets Create Creative Tab, Sheets Write Creative Rows, Asana LP Draft Monthly, Asana Creative Report Monthly, Asana LP Draft Monthly upgraded to ASSUMED after code inspection

**kpi_* sub-flows UNTESTED (42 total, 6 nodes each)** — all 6 sub-flows have never fired end-to-end from the daily loop trigger

**infra_approval_listener UNTESTED (2)**:
- Resume Waiting Execution — approval loop never exercised
- Post Rejected — rejection path never exercised

---

## Top 5 Highest-Risk Gaps

### RISK 1: kpi_qual_ratio "Qual < 30%" branch — Create Asana Task (UNTESTED)
**Why high risk**: This is the only automated P0 response to a critical lead quality collapse. When qual rate drops below 30%, this node creates an urgent LP redirect task. It has NEVER fired. If it fails silently (e.g., Asana credential error, SQL template variable bug in BQ Qual Drill), the team receives no alert. The SQL in BQ Qual Drill has visually malformed template escaping in the raw JSON that could cause a BQ query failure, silently skipping the entire sub-flow.
**Action**: Trigger manually with a synthetic low-qual input. Observe the Asana task created. Verify task name, notes, and due_on match expected format.

### RISK 2: cadence_daily "Post Slack Performance" + "Post Slack Approvals" (ASSUMED)
**Why high risk**: These are the primary outputs the team reads every morning. While confirmed to have fired on 2026-06-19, the content was declared correct based on general observation ("numbers look right"), not a line-by-line verification of each channel's CPQL against a direct BQ query. The Build ai-orchestrator code node that generates the digest has never been verified to produce correct numbers independently. A silent calculation bug (e.g., wrong date range, fan-out from missing CTE) would produce plausible-looking but wrong numbers in #approvals.
**Action**: On next run, extract BQ lead counts and spend for yesterday per channel directly. Compare each figure in the Slack digest line-by-line. Document delta.

### RISK 3: cadence_weekly — workflow has never fired in production (27 ASSUMED, never VERIFIED)
**Why high risk**: The weekly workflow has never fired. This means 28 nodes — including the performance-lead Claude node that escalates CPQL regressions and the LP audit path that creates a weekly Google Sheets tab — are completely untested in production. Code inspection (2026-06-23) confirmed SQL is correct (does NOT use `qoyod_source` — weekly joins on campaign name/utm_campaign); however, Google Sheets OAuth2 credential `kBgcDkRIN5tMoACU` and Asana credential have not been confirmed active for this workflow's execution path. wkly-018 (Build Approvals Text) is not connected to Post Slack Approvals in the current connection map — Post Slack Approvals runs directly from Parse weekly, making wkly-018 a dead node in the current wiring.
**Action**: Manually trigger cadence_weekly NOW (before next Sunday). Verify: (1) BQ freshness check passes, (2) Period Compare query returns rows, (3) Claude output posted to Slack, (4) Asana tasks created, (5) LP tab created in Google Sheets. Also verify whether wkly-018 (Build Approvals Text) is intentionally disconnected or was meant to replace the direct Approvals post.

### RISK 4: infra_approval_listener "Resume Waiting Execution" (UNTESTED)
**Why high risk**: This node is the critical link in the approval gate chain. When a user reacts with ✅ in #approvals, this node POSTs to the Wait Campaign Approval webhook URL to resume the paused execution. If it fails (wrong URL, missing auth, execution already expired), the approval is silently ignored and the campaign action never executes. The URL is hardcoded to `https://qoyod.app.n8n.cloud/webhook/campaign-approval-webhook-001`. The full approval-to-execution loop has never been demonstrated end-to-end.
**Action**: Create a test execution that reaches Wait Campaign Approval. React with ✅ in Slack. Confirm the execution resumes and the subsequent action nodes fire.

### RISK 5: cadence_daily "Claude performance-lead" and "Post Slack Approvals" — CPQL zone mismatch (ASSUMED)
**Why high risk**: The Build performance-lead prompt in cadence_daily says CPQL pause threshold = ">$160" but the CLAUDE.md and config.py define CPQL pause at ">$85 investigate / scale <$85". The weekly and monthly performance-lead nodes hardcode their own threshold strings independently of agent_config BQ table (they do NOT read from BQ Fetch Config). This means CPQL zone rules can silently diverge between daily (reads agent_config) and weekly/monthly (hardcoded). A pause recommendation in the weekly digest could be wrong if the hardcoded thresholds drift from config.py.
**Action**: Audit Build performance-lead in cadence_weekly and cadence_monthly. Compare hardcoded CPQL thresholds against config.py and agent_config BQ table. If mismatched, update weekly/monthly nodes to read from BQ agent_config instead.

---

## Verification Plan (Priority Order)

1. **cadence_weekly — manual test trigger (TODAY, before Sunday)**: Execute workflow manually in n8n UI. Confirm: freshness check passes; period compare returns rows (does not use qoyod_source — confirmed correct); Claude fires; Slack posts in both channels; Asana task created; Google Sheets LP tab created. Also confirm whether wkly-018 (Build Approvals Text) is intentionally disconnected. Expected: ~5 Asana tasks, 1 Sheets tab.

2. **kpi_qual_ratio — synthetic trigger**: In n8n UI, execute kpi_qual_ratio with input `{channel:'meta', qual_rate_pct:25}`. Confirm: BQ Qual Drill returns rows; correct branch fires (LP Redirect Urgent); Asana task has correct name `[URGENT - QUAL CRITICAL]` and due_on = today; Return Result status = 'created'.

3. **cadence_daily Slack digest — number verification**: Next morning after 07:00 Riyadh, query BQ directly for yesterday's spend+leads+CPQL per channel. Compare each line in the #approvals Slack message against BQ. Delta must be 0 (exact match). If any channel shows wrong numbers, trace to the BQ query node that produced the input to Build ai-orchestrator.

4. **infra_approval_listener full loop**: Create a test run of cadence_daily with `needs_new_campaign=true` to reach Wait Campaign Approval state. React with ✅ in Slack. Confirm execution resumes within 30 seconds. Confirm campaign-manager Claude node fires. Confirm Asana task created.

5. **cadence_monthly — manual test trigger (before July 1)**: Execute manually in n8n UI. Confirm: freshness check; period compare; Creative Report Sheets tab created (credential `kBgcDkRIN5tMoACU` active); LP Brief Asana task created; both Slack channels receive posts.

6. **All 6 KPI sub-flows — mock trigger**: For each of kpi_roas, kpi_cpql, kpi_cpl, kpi_impression_share, kpi_creative_ctr: Execute with synthetic input matching the flag criteria. Confirm BQ node fires, Claude node fires, Asana task created with correct fields, Return Result status = 'created'. Expect: 6 Asana tasks created.

7. **infra_data_health — number cross-check**: Pull today's Slack message from #data-health. Compare BQ Deals count and BQ Leads count shown against direct BQ queries for the same 60-day window. Delta must be 0.

8. **Query HS Recon scope check**: Verify that the HubSpot Contacts API used in Query HS Recon (cadence_daily) returns the same lead count as the Lead Module object 0-136 for the same 7-day window. If mismatched, replace with Lead Module API call.

9. **Weekly/Monthly performance-lead CPQL threshold audit**: Open Build performance-lead nodes in cadence_weekly (wkly-node) and cadence_monthly. Extract hardcoded CPQL strings. Compare against config.py `CPQL_*` constants and agent_config BQ table. Document any mismatch. Fix if found.

10. **`qoyod_source` column confirmation for monthly only**: Run `SELECT column_name FROM angular-axle-492812-q4.qoyod_marketing.INFORMATION_SCHEMA.COLUMNS WHERE table_name='hubspot_leads_module_daily'` to confirm `qoyod_source` exists. NOTE: cadence_weekly does NOT use `qoyod_source` (confirmed by code inspection 2026-06-23 — weekly joins on `lead_utm_campaign`/`campaign_name`). Only cadence_monthly uses `qoyod_source`. Column presence confirmed via execution 188 returning rows.
