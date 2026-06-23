# Pitfalls & Known Traps

## [2026-06-23] cadence_daily broken — Config-Flatten did not pass date fields to sub-workflow

**Symptom:** cadence_daily (T8icImtZFLYeCa7e) ran daily but only 3–5 of 118 nodes executed. All ad platform collectors in the sub-workflow (jOnJxdpdaO3Vbi0B) returned 0 rows. The guard always blocked the BQ load. Appeared as status=success in the n8n API but produced no data.

**Root cause:** The data flow is: `Set Dates` → `BQ Fetch Config` → `Config-Flatten` → `Phase 1 Data Collection` (executeWorkflow) → sub-workflow. `Config-Flatten` read only from `BQ Fetch Config` (agent_config keys: kpi_rules, roles, etc.) and returned that as a flat object. It did NOT include the date fields from `Set Dates` (yesterday, start_7d, etc.). When the executeWorkflow node called the sub-workflow, its Trigger node received this config-only object. Every ad platform HTTP node called `$('Trigger').first().json.yesterday` which resolved to `undefined`. All 10 platform API calls used `undefined` as the date parameter → zero rows returned → Aggregate Campaigns → Build Guard Payload produced empty report → Claude Data Guard set `should_load=false` → IF blocked everything downstream.

**Fix:** Add `const dates = $('Set Dates').first().json;` and spread into the return: `return [{ json: { ...config, ...dates } }];` in the Config-Flatten node. This ensures the sub-workflow Trigger receives both config keys AND yesterday/start_7d/etc.

**File:** `n8n/workflows/cadence_daily.json` — `Config - Flatten` node. Pushed to n8n Cloud 2026-06-23T08:02:40Z. Commit: 93c4218.

**Rule:** Any n8n `executeWorkflow` node that calls a sub-workflow needing date context MUST pass the date fields explicitly. Sub-workflows only see what the calling node passes as input — they cannot reference nodes from the parent workflow.

## [2026-06-23] cadence_weekly (iNSdpXH7Rc9Lb8h8) — 6 schema/config bugs fixed on first complete run

**Bugs found and fixed during manual trigger run 2026-06-23:**

1. **`Query Ad Audit` (wkly-005):** SQL used `v.campaign_name` but `v_ad_performance` has `utm_campaign`. Fix: replace all 3 occurrences with `v.utm_campaign`.

2. **`Query Monitor` (wkly-006):** SQL used `event_date`, `action_type`, `target_name`, `outcome` but `agent_activity_log` actual schema is `ts` (TIMESTAMP), `action`, `campaign_name`, `status`. Fix: rewrite using correct column names with `DATE(ts,'Asia/Riyadh') AS event_date` alias.

3. **`Build ? performance-lead` (w-build-perf-001):** `tool_choice: {type: 'required'}` — Anthropic API doesn't accept `'required'`; valid values are `'auto'`, `'any'`, `'tool'`, `'none'`. Fix: change to `{type: 'any'}`.

4. **`Parse ? weekly` (wkly-010):** Literal `0x0A` newline inside single-quoted JS string in `approvalsText` join pattern caused `SyntaxError`. Fix: rewrite using `String.fromCharCode(10)` instead of `\n` escape.

5. **`Post Slack ? Approvals` (wkly-012):** Same literal-newline issue inside `jsonBody` expression. Fix: replace literal `\n\n` with `String.fromCharCode(10)+String.fromCharCode(10)`.

6. **`BQ ? LP Audit` (wkly-lp-01):** Node had `query` parameter key but BigQuery v2 node expects `sqlQuery`. Fix: rename `query` → `sqlQuery`, add `resource: "database"`, `operation: "executeQuery"`.

7. **`Build Audit SQL` (wkly-015):** INSERT into `agent_activity_log` used wrong column names (`action_type`, `target_name`, `event_date`, `outcome`, `created_at`). Fix: rewrite INSERT using actual schema (`activity_id`, `ts`, `session_id`, `role`, `action`, `status`, `channel`, `campaign_name`, `details`).

8. **`Sheets ? Create LP Tab` / `Sheets ? Write LP Rows` (wkly-lp-03/04):** Google Sheets OAuth2 credential restricted from HTTP Request nodes; native `googleSheets` node type fails with "Forbidden" (OAuth account lacks Editor access to spreadsheet). Workaround: set `onError: continueErrorOutput` so workflow completes. PERMANENT FIX needed: share spreadsheet `120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg` with the Google account tied to OAuth2 credential `kBgcDkRIN5tMoACU`, OR update `nodesAccess` in n8n UI for the credential to allow HTTP Request nodes.

**n8n expression parser gotcha:** When `specifyBody: "json"` is used on an HTTP Request node with `googleApi` credential type, the expression evaluator fails with `invalid syntax` even for valid `JSON.stringify({...})` expressions. This only affects `googleApi` credential type nodes. With `httpHeaderAuth` (Slack), the same expression works fine.

9. **`v_ad_performance` view must be re-deployed after `bq_writer.py` changes:** Changing column aliases in `V_AD_PERFORMANCE_SQL` in `collectors/bq_writer.py` does NOT automatically update the live BQ view. The view DDL must be re-executed explicitly. The n8n `Query Ad Audit` SQL used `v.utm_campaign` (correct per local code) but the live BQ view still had `campaign_name` from before the fix was committed — causing `Name campaign_name not found inside v` on exec#189/190/191. Fix: `python -c "from collectors.bq_writer import V_AD_PERFORMANCE_SQL, get_client; client=get_client(); client.query(V_AD_PERFORMANCE_SQL).result()"` with `GOOGLE_APPLICATION_CREDENTIALS` set. **Rule:** After any change to `V_AD_PERFORMANCE_SQL` / `V_ADSET_PERFORMANCE_SQL` / `V_KEYWORD_PERFORMANCE_SQL`, re-deploy the view immediately before claiming the fix is done.

**Rule:** After any new n8n cadence workflow is written, always do a manual test run immediately — never assume it works until all nodes complete at least once.

## [2026-06-23] n8n IF node v2 — days_stale returns string from BQ, causes type error even with typeValidation=loose

**Symptom:** Cadence Weekly workflow (iNSdpXH7Rc9Lb8h8) errored on 2026-06-21 at the "IF Data Fresh?" node with: `Wrong type: '2' is a string but was expecting a number [condition 0, item 0]`. Workflow halted immediately — zero downstream nodes ran.

**Root cause:** The BQ Freshness Check node query returns `DATE_DIFF(...)` as an integer in BQ, but n8n's `googleBigQuery` node v2.1 serialises all BQ values as strings in `$json`. The IF node has `operator.type = "number"` and `typeValidation = "loose"` — but n8n v2 IF node does NOT auto-coerce strings to numbers even in loose mode when the comparison type is `number`.

**Fix:** Two options (either works):
1. Wrap the BQ column in `CAST(DATE_DIFF(...) AS INT64)` — BQ still sends a number type; n8n respects it.
2. Change the IF condition `operator.type` to `"string"` and compare `rightValue: "1"` (string comparison). Simpler but fragile for > 9 day staleness.
   Preferred: option 1 (CAST).

**Rule:** Any n8n IF node comparing a BQ-sourced integer field with `operator.type = "number"` must use CAST in the BQ query to guarantee the value arrives as a number, not a string.

**Applied fix (2026-06-23):** Updated `BQ Freshness Check` node `sqlQuery` in workflow `iNSdpXH7Rc9Lb8h8` — `DATE_DIFF(...)` wrapped in `CAST(... AS INT64)`. Confirmed via PUT 200.

## [2026-06-23] n8n LP Audit node — `destination_url` does not exist in campaigns_daily or v_ad_performance; use ads_daily.final_url

**Symptom:** `BQ LP Audit` node in cadence_weekly workflow used `campaigns_daily.destination_url` which doesn't exist. Query would have errored with `Name destination_url not found inside c` on any execution that reached that node.

**Root cause:** The node was written referencing a non-existent column. Neither `campaigns_daily`, `v_ad_performance`, nor `v_adset_performance` have a `destination_url` column. The correct source for LP URL data is `ads_daily.final_url` (ad-level table).

**Fix:** Rewrite LP Audit query to use `ads_daily` grouped by `final_url`, joined to HubSpot via `campaign_name`. Applied to workflow iNSdpXH7Rc9Lb8h8 on 2026-06-23.

**Rule:** Always query `ads_daily.final_url` (not `campaigns_daily.destination_url`) for landing page URL analysis.

## [2026-06-23] n8n — googleSheetsOAuth2Api credential blocked in HTTP Request nodes; use native googleSheets node

**Symptom:** Any HTTP Request node using `predefinedCredentialType: googleSheetsOAuth2Api` fails with: `"This credential is configured to prevent use within an HTTP Request node"`. Execution snapshot shows old `httpRequest` type even after PUT updated the workflow — this is because n8n snapshots the node config at execution start, so a stale execution shows the old type even if cloud was already updated.

**Root cause:** n8n cloud enforces `nodesAccess` restrictions on OAuth2 credential types. `googleSheetsOAuth2Api` is restricted to native `n8n-nodes-base.googleSheets` nodes only.

**Affected nodes in cadence_weekly (iNSdpXH7Rc9Lb8h8):**
- `wkly-017` Sheets → Weekly Log (FIXED 2026-06-23, commit 71dc0ea)
- `wkly-lp-03` Sheets → Create LP Tab (FIXED 2026-06-23, commit 2d873fd)
- `wkly-lp-04` Sheets → Write LP Rows (FIXED 2026-06-23, commit 2d873fd)

**Fix:** Replace `n8n-nodes-base.httpRequest` with `n8n-nodes-base.googleSheets` (typeVersion 4).
- For `append` (wkly-017, wkly-lp-04): `operation: "append"`, `documentId.__rl.mode: "id"`, `sheetName.__rl.mode: "name"`, `columns.mappingMode: "defineBelow"` with explicit column→expression mapping.
- For `createSheet` (wkly-lp-03): `operation: "create"`, same `documentId`, `sheetName` with expression.
- Credential reference `{id: "kBgcDkRIN5tMoACU", name: "Google Sheets OAuth2 API"}` stays identical.

**Limitation:** Native googleSheets append with `defineBelow` writes ONE item per execution. The original lp-04 wrote ALL rows via raw values API in one call. Now only `rows[0]` (top campaign) is written. To restore multi-row write, add a SplitInBatches node before lp-04 or reshape data in Code Format LP to output one item per row.

**Rule:** Never use `googleSheetsOAuth2Api` credential in an HTTP Request node. Always use `n8n-nodes-base.googleSheets` native node.

## [2026-06-23] GH Actions env block — always cross-check collector os.getenv calls

**Symptom:** Snapchat wrote 0 rows every GH Actions run for weeks. Step showed green (exit 0). Dashboard showed 3-day staleness. Snapchat had been silently broken since the workflow was first written.

**Root cause:** `collectors.yml` env block had auth vars (`SNAPCHAT_CLIENT_ID/SECRET/REFRESH_TOKEN`) but was missing the account ID vars (`SNAPCHAT_AD_ACCOUNT_2024`, `SNAPCHAT_AD_ACCOUNT_2025`). `snap_bq.py::_ad_accounts()` returns empty list when those vars are absent — no error, no rows. The secrets existed in GitHub but were never injected into the job.

**Why it wasn't caught:** After writing the workflow, no one triggered a manual run and queried `MAX(date)` per channel in BQ to confirm actual data flow. Step-level `continue-on-error: true` + silent zero-row exits make GH Actions an unreliable health signal.

**Rule:** Any time a new collector step is added to `collectors.yml`, the verification is:
1. `grep -E "os.getenv|os.environ" collectors/<name>_bq.py` — list every env var the script reads
2. Cross-check every one against the `env:` block in `collectors.yml`
3. After the next scheduled run, query `SELECT MAX(date) FROM campaigns_daily WHERE channel = '...'` — confirm it equals today or yesterday

**Zero-row guard:** A post-run step now fires on every full run and posts to #data-health if any channel's MAX(date) < yesterday. This is the detection layer. The above is the prevention layer.

## [2026-06-22] Snapchat + Microsoft Ads campaign_name duplicates in campaigns_daily

**Symptom:** `campaigns_daily` has multiple rows for the same `(date, channel, campaign_name)` — one from an ACTIVE campaign, one from a PAUSED campaign (same name, different `campaign_id`). Snapchat: 3 campaigns, 5 days (510 extra rows). Microsoft Ads: 1 campaign, 4 days (40 extra rows).

**Root cause:** Two separate issues:
1. **Snapchat**: Same Snap account had two campaigns with identical names — an older PAUSED campaign and a newer ACTIVE one. The PAUSED campaign had $0 spend/$0 impressions in the duplicated window. The `upsert_rows` key is `(date, channel, campaign_id)` so both rows legitimately insert with no key collision.
2. **Microsoft Ads**: `Bing_Search_AR_Brand` existed in two different accounts (187231519 PAUSED, 188176729 ACTIVE) with real spend on both. The multi-account collector correctly wrote both rows.

**Fix applied 2026-06-22:**
- `snap_bq.collect_and_write`: skip rows where `spend=0 AND impressions=0 AND status=PAUSED` — prevents zero-activity paused campaigns from polluting the table.
- `microsoft_ads_bq.collect_and_write`: collapse `all_rows` by `(date, campaign_name)` before upserting, summing metrics and keeping ACTIVE campaign_id as canonical identity.
- One-time BQ dedup: 46666 → 45719 total rows; strategy = SUM metrics within `(date, channel, campaign_name)`, keep ACTIVE `campaign_id`.

**Rule going forward:** Any analysis grouping `campaigns_daily` by `campaign_name` must use `SUM(spend)` not `MAX(spend)` — multiple campaign_ids can legitimately share a name. The `spend_campaign` CTE in `utm_paid_attribution_daily` already does this correctly.

## [2026-06-21] Anomaly alerts must pass the "drives action" test

Every alert posted to Slack must answer: **"What do I do now?"** If the reader cannot take a concrete step, the alert is noise and must be removed or suppressed.

Specific patterns that are noise and must be suppressed:
- **Paused campaigns flagged as "dark"** — spend=0 AND impressions=0 for the full window = paused, not dark. Not actionable.
- **Campaigns that never ran** — no historical spend = never launched. Not actionable.
- **LinkedIn token warning when token is valid** — check `platform_tokens` table first; if `refreshed_at` < 24h and not expired, suppress entirely. The GitHub Action already handled it.
- **Broken connector names listed in Slack** — connector issues should auto-fix silently; only post to Slack if self-heal also failed. Never list connector names in the Slack message itself — details go to Asana only.
- **Mass-fire (> 5 anomalies at once)** — almost always a systemic event (platform outage, scheduled budget pause). Post one summary alert, not individual ones.
- **Metrics with fewer than 3 days of baseline data** — not enough history for a meaningful signal.

Rule: before adding any new alert, ask "if this fires, what does the reader do?" If the answer is "nothing" or "check something", suppress it until there's a clear action.

## [2026-06-17] n8n Claude nodes: `tool_choice:{type:'required'}` is invalid → 400 crash

**Symptom:** Master workflow crashes at first Claude node (`Claude · Data Guard`) with:
`400 - tool_choice: Input tag 'required' found using 'type' does not match any of the expected tags`

**Root cause:** Anthropic API `tool_choice.type` valid values are `auto`, `any`, `tool`, `none`.
`required` is NOT valid — it is a different API's convention.

**Fix:** Replace all `tool_choice:{type:'required'}` with `tool_choice:{type:'any'}` in every
Claude HTTP Request node in n8n. Applied to all 5 nodes in Master (`T8icImtZFLYeCa7e`) 2026-06-17:
`Claude · Data Guard`, `Claude · growth-analyst`, `Claude · performance-lead`,
`Claude · campaign-manager`, `Claude · creative-strategist` — 10 occurrences total (2 per node).

**Rule going forward:** When adding a new Claude node in n8n with forced tool use, always use `any`, never `required`.

**Full scope of the fix (2026-06-17):** Found in 3 separate workflows across 8 nodes (10 occurrences in Master, 2 in Data Collection sub-workflow, 2 in Weekly, 2 in Monthly). The sub-workflow and Weekly/Monthly nodes were missed in the first pass because the fix was scoped only to Master. Always scan ALL workflows when fixing this pattern.



## [2026-06-16] wide_ads: THREE sources of NULLs at ad/adset level — FIXED

Three distinct root causes produce NULLs in `wide_ads`. All three were fixed 2026-06-16
in `collectors/views.py` WIDE_ADS_SQL.

**Bug 1 (FIXED) — Snapchat + TikTok ads_daily have `campaign_name = NULL` at ad grain.**
Both collectors hardcode `None` for campaign_name at the ad-level endpoint — the
Snapchat/TikTok API does not return campaign metadata at ad grain, and the collectors
don't look it up from the campaign fetched earlier.
FIX APPLIED: `WIDE_ADS_SQL` now LEFT JOINs `camp_lookup` (aggregated from `campaigns_daily`)
and `adset_lookup` (aggregated from `ads_daily` itself where name is not null), then
COALESCEs `a.campaign_name, camp_lookup.campaign_name`. Verified: 0 NULL campaign_names
for Snapchat and TikTok in wide_ads after rebuild (2026-06-16).
NOTE: TikTok `adset_name` remains NULL — TikTok collector never writes `adset_name`,
so the lookup is also null; fix requires collector-side change (out of scope 2026-06-16).
NOTE: `adsets_daily` table does NOT exist in BQ — adset lookup uses `ads_daily` itself.

**Bug 2 (NOT FIXED — date join retained intentionally) — wide_ads lead join date mismatch.**
`leads_by_id` groups by `(hs_createdate, ad_id)`. Lead createdate ≠ spend date in
~39% of cases (687 of 1,283 leads arrive on different day than spend row). Removing
the date join causes catastrophic 30x fan-out (lifetime ad leads attached to every
daily spend row). DECISION: keep date join, accept ~39% lead undercounting as the
safe trade-off. Undercounting inflates CPQL (conservative); overcounting deflates CPQL
(dangerous for decisions). The 39% mismatch is documented and known.

**Bug 3 (FIXED) — Snapchat ghost rows: 97.1% of ads_daily rows have zero spend.**
Snapchat collector pulls all historical ads for every date, generating 34,080 rows/month
with only ~1,001 having actual spend. Fixed by adding `WHERE a.spend > 0` to the
FROM clause of WIDE_ADS_SQL. Verified: all channels now have 0 zero-spend rows (2026-06-16).

**Summary — Hex impact after fixes:**
- Snapchat/TikTok campaign tabs: campaign names now populated (Bug 1 fixed)
- Snapchat adset/ad tabs: ghost rows eliminated, 97% row count reduction (Bug 3 fixed)
- Lead counts on id-sync channels (Meta/Snap/TikTok): unchanged — date mismatch is
  a known limitation, not fixable without overcounting risk

## [2026-06-16] paid_channel_campaign_daily was DROPPED — any Hex cell querying it will crash

`paid_channel_campaign_daily` was dropped 2026-06-16 (migrated to `wide_ads`). Any Hex
cell or Python script that references it will fail with:
`Not found: Table angular-axle-492812-q4:qoyod_marketing.paid_channel_campaign_daily`
The replacement is always `wide_ads`, GROUP BY `campaign_id` to get campaign grain.

Campaign filter/dropdown cells that used `paid_channel_campaign_daily` for listing
distinct campaign names must use:
```sql
SELECT DISTINCT campaign_name
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND campaign_name IS NOT NULL
  {% if channel_filter %}AND channel = {{ channel_filter }}{% endif %}
ORDER BY campaign_name
```
Reference SQL saved at `.claude/hex_drilldown/campaign_list_data.sql`.

Same applies to `paid_channel_daily`, `v_adset_performance`, `v_ad_performance` —
all dropped 2026-06-16, all consumers migrated to `wide_ads`.

## [2026-06-16] wide_ads migration — dropped tables, null names, ghost rows

**What changed:**
- `paid_channel_campaign_daily`, `v_ad_performance`, `v_adset_performance`,
  `v_channel_key_map`, `channel_roas_daily`, `paid_channel_daily` were all DROPPED.
- Replacement: `wide_ads` (ad-grain denormalized table, single source of truth for all Hex SQL).
- Bug 1: Snapchat/TikTok `campaign_name`/`adset_name` came through as None — fixed with
  COALESCE from `campaigns_daily`/`ads_daily` in the `wide_ads` builder.
- Bug 2: 33k ghost rows (spend=0) caused null `ad_name` rows in Hex — fixed with `WHERE spend > 0`.
- Bug 3: `v_channel_key_map` was dropped and not recreated — rebuilt as a static UNNEST view
  in `collectors/views.py`. Must stay in `ALL_VIEWS` so it auto-recreates every 6h.
- Hex has no cell-editing API (401, requires paid plan). All 28 SQL files must be pasted manually.
  Source of truth: `.claude/hex_drilldown/` — one file per Hex cell.

**wide_ads vs hubspot_leads_module_daily mismatch is EXPECTED and SIGNIFICANT:**
- `wide_ads` joins leads by `(date, ad_id)` — only counts leads where createdate matches spend date.
- `hubspot_leads_module_daily` groups by `(date, lead_utm_campaign)` — a broader, different join key.
- Result: wide_ads typically undercounts by 20–80% per channel vs the module table. This is intentional
  (see Bug 2 note in earlier entry). Do NOT use wide_ads lead totals to validate module table counts.
- Reconciliation target: BQ module table vs HubSpot API (not wide_ads vs module).

**7-day reconciliation result (2026-06-16, window 2026-06-09 to 2026-06-15):**
- BQ (module table) total: 710 leads | HubSpot API total: 650 leads | Delta: +9.2% — FAIL >5%
- By channel: google_ads +11.7%, meta +11.5%, tiktok +10.2%, microsoft_ads -6.5%, snapchat +3.8% (OK)
- linkedin: 1 in BQ, 0 in HubSpot (1 lead, timing lag acceptable)
- Root cause of gap: BQ mirror runs every 6h; HubSpot search API only counts contacts where
  qoyod_source is set. Leads still being classified by n8n workflow will appear in BQ before
  qoyod_source is written back to HubSpot. This is a sync-timing gap, not a duplication or
  attribution error. Re-run reconciliation after 24h for a cleaner read.

## [2026-06-16] n8n cloud internal API: use PATCH not PUT

`PUT /rest/workflows/{id}` returns `404 Cannot PUT`. The correct method for updating a workflow via the browser session is `PATCH /rest/workflows/{id}` with `Content-Type: application/json`. Same applies to partial updates (just `{active:true}` etc.). The public API (`/api/v1/workflows/{id}`) uses `X-N8N-API-KEY` header — different auth path. Activation via PATCH `{active:true}` silently returns `active:false` if the workflow has validation issues; use the n8n UI toggle as fallback.

## [2026-06-18] n8n `wide_ads` fan-out drops ~39% of leads at campaign level

**Symptom:** n8n report shows ~39% fewer leads than BQ `hubspot_leads_module_daily` for the same campaigns/channels.

**Root cause:** `wide_ads` attributes leads per ad via `(date, ad_id)` join — lead createdate ≠ spend date for ~39% of leads (687 of 1,283 in the last sample). This is a known, intentional trade-off in `wide_ads` (conservative undercounting). It is NOT suitable for campaign-level lead totals in reports.

**Fix:** Always use `campaigns_daily` + a pre-aggregated `hubspot_leads_module_daily` CTE for campaign-level lead counts in n8n workflows:
```sql
WITH hs AS (
  SELECT date, lead_utm_campaign,
         SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM `project.dataset.hubspot_leads_module_daily`
  GROUP BY date, lead_utm_campaign
)
SELECT c.campaign_name, SUM(c.spend) AS spend, SUM(hs.leads) AS leads,
       SAFE_DIVIDE(SUM(c.spend), SUM(hs.sqls)) AS cpql
FROM `project.dataset.campaigns_daily` c
LEFT JOIN hs ON c.date = hs.date
           AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
WHERE c.date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND CURRENT_DATE()
GROUP BY c.campaign_name
```
**Rule: never use `wide_ads` for campaign-level aggregations in n8n report workflows.**

## [2026-06-18] n8n `MAX(qual_rate)` cross-campaign pollution after LEFT JOIN

**Symptom:** Campaign CPQL numbers are wildly wrong — one campaign's qual_rate bleeds into others.

**Root cause:** Using `MAX(hs.qual_rate)` in a `GROUP BY` query after a LEFT JOIN picks an arbitrary qual_rate from whichever HubSpot row lands last. If two campaigns have different qual_rates and the JOIN is not perfectly 1:1, the MAX picks the wrong campaign's value.

**Fix:** Never pre-compute `qual_rate` in HubSpot CTE and take MAX of it. Instead, pre-aggregate raw counts (`leads_total`, `leads_qualified`) on both sides, then compute `SAFE_DIVIDE(SUM(sqls), SUM(leads))` AFTER joining:
```sql
-- WRONG
SELECT c.campaign_name, MAX(hs.qual_rate) AS qual_rate  -- poisons across campaigns
...
-- CORRECT
SELECT c.campaign_name,
       SAFE_DIVIDE(SUM(hs.sqls), SUM(hs.leads)) AS qual_rate
FROM campaigns_agg c
LEFT JOIN hs_agg hs ON ...
GROUP BY c.campaign_name
```
**Rule: always join pre-aggregated spend and pre-aggregated HS separately, then compute SAFE_DIVIDE on summed values.**

## [2026-06-18] n8n daily-grain CPQL spike from wrong GROUP BY

**Symptom:** Report shows a campaign with CPQL of $800+ when the true 14-day CPQL is $90. The spike is from a single bad day being surfaced as the "campaign's" number.

**Root cause:** Grouping by `(date, channel, campaign_name)` and ordering by `CPQL DESC` (or using a daily grain without further aggregation) picks the single worst-day spend/leads ratio and presents it as if it represents the campaign's overall performance.

**Fix:** Always aggregate over the FULL evaluation window first, then compute CPQL from the totals:
```sql
-- WRONG: daily grain, worst day surfaces as "the" CPQL
SELECT date, campaign_name, spend/sqls AS cpql
FROM ... GROUP BY date, campaign_name ORDER BY cpql DESC LIMIT 10

-- CORRECT: full-window aggregation
SELECT campaign_name,
       SUM(spend) AS total_spend,
       SUM(sqls) AS total_sqls,
       SAFE_DIVIDE(SUM(spend), SUM(sqls)) AS cpql
FROM ...
WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND CURRENT_DATE()
GROUP BY campaign_name
ORDER BY cpql DESC
```
**Rule: never group by `(date, campaign_name)` and ORDER BY CPQL for a report — always aggregate the full window first.**

## [2026-06-17] n8n public API (/api/v1): use PUT not PATCH for workflow updates

**PATCH returns 405 on `/api/v1/workflows/{id}`** — the public API only supports PUT. The internal browser API (`/rest/`) uses PATCH; they are separate paths with different methods. Always use PUT when updating workflows via the public API with `X-N8N-API-KEY`.

**PUT body: only these fields are accepted** (confirmed 2026-06-19 — all others cause HTTP 400 "additional properties" or "read-only"):
```python
ALLOWED_FIELDS = {"name", "nodes", "connections", "settings", "staticData"}
```
Strip: `createdAt`, `updatedAt`, `id`, `description`, `active`, `isArchived`, `meta`, `nodeGroups`, `pinData`, `versionId`, `activeVersionId`, `versionCounter`, `triggerCount`, `sourceWorkflowId`, `shared`, `tags`, `activeVersion`.

**There is no run/execute endpoint** on the public API for schedule-triggered workflows — trigger via the n8n UI "Execute Workflow" button instead.

## [2026-06-17] n8n googleBigQuery node: exact format required or credential validation fails

The `n8n-nodes-base.googleBigQuery` node REQUIRES:
- `typeVersion: 2.1` (not 2.0)
- `parameters.authentication: "serviceAccount"`
- `parameters.projectId: {"__rl": true, "value": "project-id", "mode": "id"}` (resource locator format, not plain string)
- `credentials: {"googleApi": {"id": "...", "name": "..."}}` (type is `googleApi`, not `googleBigQueryOAuth2Api`)

Without `authentication: "serviceAccount"`, n8n rejects with "Missing required credential: googleBigQueryOAuth2Api". The existing BQ credential in n8n is `kE5RxM61mQkpV21N` (type `googleApi`, name "BigQuery (Qoyod)").

## [2026-06-17] n8n public API: PATCH on active workflows can partially save

When PATCH fails with a credential error (405, 400), the workflow may still get partially updated — nodes appended, connections added — leaving it in a broken state. Always fetch fresh before building the update payload, and include idempotent cleanup: strip all existing `googleBigQuery` and `code` nodes before re-adding, and purge connections referencing removed node names.



## [2026-06-15] CREATE OR REPLACE VIEW fails if object is a BASE TABLE

BQ throws "different type" if you try to `CREATE OR REPLACE VIEW` on a name that already exists
as a BASE TABLE. Fix: drop the physical table first (`not_found_ok=True`), then the VIEW DDL
succeeds. This happened to `paid_channel_daily`, `paid_channel_campaign_daily`,
`v_adset_performance`, `v_ad_performance` during the wide-table migration (2026-06-15).

```python
client.delete_table(table_id, not_found_ok=True)
# then run CREATE OR REPLACE VIEW ...
```

## Cowork scheduled tasks — use .env credentials directly, never MCP connectors (2026-06-13)

- **MCP connectors (Slack, Google, etc.) use separate OAuth tokens** that expire independently of the bot tokens stored in Railway/.env. When a MCP connector returns `invalid_auth`, the task silently fails even though the underlying credentials are fine.
- **Rule: all scheduled tasks must use credentials from `.env` / Railway env vars directly**, not MCP connectors. Load `.env` at the top of every bash Python script:
  ```python
  import os
  with open(r'D:\Nexa Performance Agent\.env') as f:
      for line in f:
          line = line.strip()
          if line and not line.startswith('#') and '=' in line:
              k, v = line.split('=', 1)
              os.environ[k.strip()] = v.strip()
  ```
- **Slack** → use `SLACK_BOT_TOKEN` with `requests` calling `slack.com/api/*` directly. DO NOT use `mcp__slack__*`.
- **BigQuery / any Google API** → use `GOOGLE_APPLICATION_CREDENTIALS_JSON` (Railway, cloud) or `GOOGLE_APPLICATION_CREDENTIALS` (local path to JSON) with `google.oauth2.service_account.Credentials`. DO NOT use the Google MCP connector.
- **Asana** → use `ASANA_ACCESS_TOKEN` with `requests` calling `app.asana.com/api/1.0/*` directly.
- **Network note:** Cowork's bash sandbox blocks outbound to most domains. To call external APIs (Slack, Asana, etc.) from bash, the domain must be added to the allowlist in **Settings → Capabilities → Network**. If you get `403 Forbidden` via proxy, this is the cause — ask the user to add the domain.

## paid_channel_daily.new_biz_* shows PAID-ATTRIBUTED deals only — HubSpot discrepancy is expected (2026-06-11)

- **"Discrepancy" is by design.** Dashboard shows 537 new_biz deals; HubSpot shows 1,165 for the same 3 pipelines + create date. The gap (~628 deals) is non-paid sources.
- **paid_channel_daily INNER JOINs deals to v_channel_key_map** → only paid sources survive: Google Ads, Meta Ads, Snapchat Ads, TikTok Ads, Microsoft Ads, LinkedIn Ads, Organic Search.
- **Sources dropped (non-paid, intentionally):** Direct Traffic (1,843 all-time), Offline (1,441), Direct In-app Purchase (1,123), Other (569), Email Marketing (181), Organic Social (115), Referrals (33). Total non-paid: 5,362 out of 13,194 deals (41%).
- **The dashboard is a paid media performance dashboard** — showing only paid-attributed new_biz is correct for CPL/CPQL/ROAS analysis.
- **When comparing to HubSpot:** HubSpot Pipeline(3) + Create date shows ALL sources. Expect dashboard to be ~46-59% of HubSpot total depending on the period.
- **`v_new_biz_daily` BQ view** (added 2026-06-11) queries all sources without channel filter — useful for all-sources funnel analysis but NOT for the paid dashboard.

## utm_source in v_adset/v_ad_performance — COALESCE fallback required for Databox filters (2026-06-09)

- **utm_source** is a HubSpot field (`lead_utm_source`). Values differ from channel slugs ("fb" ≠ "meta") — that is expected and fine.
- **Rows with leads:** utm_source comes from HubSpot (populated ~95% of the time when campaign_name exists).
- **Rows with no leads:** utm_source would be NULL without a fallback. NULL rows are invisible in Databox filters, so `COALESCE(utm_source, channel)` is intentional — it uses the channel slug as a fallback so every row is filterable.
- **utm_source, channel, and qoyod_source are THREE different things — never substitute one for another:**
  - `utm_source` = UTM parameter captured by HubSpot ("fb", "google", "tiktok") — NULL when no lead
  - `channel` = platform slug used internally ("meta", "google_ads", "tiktok")
  - `qoyod_source` = HubSpot display name ("Meta Ads", "Google Ads", "Tiktok Ads")
- **Do NOT COALESCE(utm_source, channel)** — "meta" ≠ "fb". Use `channel_name` for platform filtering on zero-lead rows.
- Fallback was added and removed twice (2026-06-09) before this was understood.

## utm_paid_attribution_daily — non-paid sources leak in as NULL-channel orphans (2026-06-09)

- **Symptom:** `v_adset_performance` showed 38 leads-only orphan rows (40 leads) with
  `channel IS NULL` but a populated `utm_audience`. They never matched
  `p.channel = h.channel` so always surfaced as leads-only.
- **Root cause:** the `hs_full` CTE in `collectors/bq_writer.py` (feeds
  `utm_paid_attribution_daily`) kept HubSpot leads whose `qoyod_source` was **non-paid**
  (`Offline` 24, `Direct Traffic` 8, `Organic Social` 5, `Other`/`Email Marketing`/
  `Direct In-app Purchase` 1 each) but which still carried a paid `utm_campaign`/
  `utm_audience` on the contact. HubSpot last-touch attribution keeps the stale paid UTM
  even when the converting touch is non-paid. Those sources map to NO slug in
  `channel_name_map`, so `COALESCE(cnm_exact,cnm_slug)` → NULL channel.
- **NOT a missing-channel-in-map bug.** `Tiktok Ads` (lowercase k) and all paid sources
  map fine via the LOWER/slug logic. Only genuinely non-paid sources fail to map — by design.
- **Fix:** filter `hs_full` to `qoyod_source` values that resolve to a known channel
  (paid + `organic_search`) using the SAME exact-then-slug match the channel join uses, so
  filter and channel resolution stay in lock-step. Then `materialize_heavy_views()`.
  Verified: NULL-channel-with-audience 38 → 0, all NULL-channel → 0,
  v_adset_performance NULL-channel → 0, per-channel paid leads unchanged
  (Meta 7d view 55 == hubspot_leads_module 55). Commit `9c758c7`.
- **Rule:** any view scoped to PAID attribution must filter HubSpot leads by `qoyod_source`,
  not just by "has a UTM". A stale paid UTM on a non-paid-source lead is the trap.

## ImpressionShare_ campaign prefix = awareness campaign — NEVER apply CPQL or CPA targets (found 2026-06-09)

- **Symptom:** Flagged `ImpressionShare_Search_AR_Invoice` as a "drain" based on CPQL, recommended keyword pauses AND a tCPA $120 bid strategy change. Both were wrong.
- **Why it's wrong — two layers:**
  1. `config.py::AWARENESS_PATTERNS = ["impressionshare", "impression_share", "websitetraffic", "reach"]` — the campaign matches this pattern. Config explicitly states: **zero leads is fine, primary KPI = IS% ≥ 25%**. Applying CPQL is a category error.
  2. `config.py::CHANNEL_CPQL_ACCEPTABLE = {"google_ads": 130.00}` — Google Ads acceptable CPQL is **$130**, not $100. The "pause zone" cutoff for Google Ads is $130, not the generic $100.
- **Fix — campaign type classification from name (check config.py AWARENESS_PATTERNS):**
  - `ImpressionShare_` → awareness/IS campaign → KPI = IS% (target ≥ 25%) + daily budget control. Zero leads is acceptable. NEVER add tCPA. NEVER apply CPQL zones.
  - `Search_AR_Brand` / `ImpressionShare_Search_AR_Brand` → brand IS → same as above.
  - `Search_*_Test` → test lead-gen campaign → must have hard daily budget cap; prior CPQL determines if regression vs chronic drain.
  - `Search_AR_Generic` / `Google_Search_AREN_*` → lead-gen → KPI = CPQL (Google Ads: pause >$130), CPL, qualification rate.
- **Correct lever for IS campaign:** IS% below 25% target → increase daily budget. IS% fine but spend high → reduce daily budget cap. Do NOT change bid strategy, do NOT add tCPA.
- **Seat responsible for enforcement:** growth-analyst classifies campaign type from name using AWARENESS_PATTERNS BEFORE selecting any KPI metric or recommending bid strategy changes.

## `rows` is a reserved keyword in BigQuery SQL — use `row_count` as alias (2026-06-09)

- `SELECT COUNT(*) AS rows` throws `Syntax error: Unexpected keyword ROWS` in BQ.
- Always use `row_count`, `cnt`, `n`, or any other non-reserved alias.

## utm_source was already collected in hubspot_leads_bq.py but missing from views (2026-06-09)

- `lead_utm_source` was in `PROPERTIES`, BQ schema, bucket key, and both `collect_and_write` and `sync_cursor_and_write` paths since before 2026-06-09.
- The gap was only in `collectors/bq_writer.py`: the `hs_full` CTE in `UTM_PAID_ATTRIBUTION_VIEW_SQL` did not SELECT or GROUP BY `lead_utm_source`, so it never flowed to downstream views.
- Fix: add `lead_utm_source` to `hs_full` GROUP BY (1..7), carry `utm_source` through `attributed`, `attributed_with_spend`, `unattributed`, `combined`, and the final SELECT. Then add `ANY_VALUE(utm_source)` to the `hubspot` CTEs in `V_ADSET_PERFORMANCE_SQL` and `V_AD_PERFORMANCE_SQL`, and expose it in both `joined` CTEs and final SELECTs.
- Verified live: 346 leads with `utm_source='Google'`, 165 `'Snapchat'`, 64 `'Tiktok'` in last 7 days across all three materialized tables.

## Prior-period CPQL determines whether a regressed campaign is a FIX or a PAUSE (found 2026-06-09)

- **Symptom:** Classified `Search_E-invoice_AR_Test` (prior CPQL $73.98, current $308.96) as a "drain" campaign requiring consideration for pause.
- **Why it's wrong:** Prior-period CPQL $73.98 is WITHIN the acceptable zone (<$80). A campaign with good prior-period performance that regressed is a **FIX candidate** (keyword cleanup, budget cap, LP review), not a pause candidate. Only campaigns with BOTH periods bad are true drains.
- **Fix:** Period comparison rule:
  - Prior CPQL good AND current CPQL bad → **REGRESSION → FIX** (root-cause + keyword/LP/cap fix)
  - Prior CPQL bad AND current CPQL bad → **CHRONIC DRAIN → PAUSE** (keep paused until structural fix)
  - Prior CPQL bad AND current CPQL worse → **ACCELERATING DRAIN → PAUSE IMMEDIATELY**
- **Seat responsible:** growth-analyst classifies prior/current delta BEFORE performance-lead decides action.

## Every recommendation must name the seat agent for each action (found 2026-06-09)

- **Symptom:** Delivered a fix-with-full-setup recommendation that listed 7 action items with no seat ownership per item.
- **Why it's wrong:** Per CRITICAL_KPI_RULES.md Rule #5, every action must be seat-owned. An ownerless action has no accountability and no playbook context.
- **Fix:** For every action item in a recommendation, append `→ [seat]`. Standard routing:
  - Keyword pauses / negatives / bid strategy changes → **campaign-manager** (executes after #approvals ✅)
  - LP audit + CRO brief → **cro-specialist** (hands off to ui-ux-designer → developer if fixes needed)
  - BQ verification / period comparison / CPQL calculation → **growth-analyst**
  - Pause/scale decision + CPQL thresholds → **performance-lead**
  - #approvals digest post + Asana tasks → **campaign-manager** or **project-coordinator**
  - Code/script fixes (e.g. audit_active_keywords.py syntax error) → **developer**

Append one-liner entries as they're discovered. Every entry should include
the fix, not just the symptom.

## v_ad_performance leads fan-out — RESOLVED 2026-06-09 (real root cause: upstream spend-join casing fan + microsoft map fan)

**Status: FIXED.** Per-channel recon 2026-06-02..2026-06-08 now passes on every paid
channel (`v_ad_performance` leads vs `hubspot_leads_module_daily.qoyod_source`):
google_ads 0.93, meta 0.96, snapchat **1.00 (148==148)**, tiktok 1.00, microsoft_ads 1.00.
Spend held to the penny vs ads_daily on all channels. Three distinct fixes, all in
`collectors/bq_writer.py`:

1. **Real Bug 1 was UPSTREAM, in `utm_paid_attribution_daily.spend_campaign`, NOT the
   downstream re-join.** `spend_campaign` grouped by RAW `campaign_name`, but the
   `sp_exact`/`sp_slug` leads joins match on `LOWER(TRIM(...))`. Snapchat runs two casing
   variants of the same campaign — `Snapchat_LeadGen_Retargeting_Instantform` vs
   `Snapchat_Leadgen_Retargeting_Instantform` (capital-G vs g). Two raw spend rows →
   one HubSpot lead bucket matched BOTH → its leads DOUBLED at the source (snapchat
   148 truth → 172 in `utm_paid_attribution_daily` itself, before any view). Fix: group
   `spend_campaign` by `LOWER(TRIM(campaign_name))` so casing variants collapse to one
   spend row per normalised join key. After fix the upstream snapchat = 148 exactly.
   **Rule: whenever a CTE is the RIGHT side of a `LOWER(TRIM())` join, that CTE MUST
   pre-group by the same `LOWER(TRIM())` key — grouping by raw casing fans the LEFT side.**
2. **The downstream Strategy C/D ID re-joins were ALSO double-counting** and are now
   REMOVED from `v_ad_performance` and `v_adset_performance`. They re-joined
   `hubspot_leads_module_daily` by `lead_ad_id_sync` / `lead_adgroup_id_sync` /
   `lead_campaign_id_sync` when the content/audience name match returned NULL, then
   sprayed campaign-level leads across every ad/adset in the campaign ON TOP OF the
   content-grain leads (snapchat AB raw 1191 + D raw 1134; meta D 255; tiktok D 361).
   **`utm_paid_attribution_daily` is the single authoritative leads source** at
   `(date, channel, utm_campaign, utm_audience, utm_content)` grain — both views now
   take leads from it ONLY, and the `lead_src_key` dedup key is the upstream bucket's
   own identity so a bucket fanning across many platform ad_id/adset_id rows counts once.
3. **Microsoft channel-label dup (Bug 2)** was rooted in `channel_name_map`: it had BOTH
   a `microsoft` AND a `microsoft_ads` slug row mapping to qoyod_source 'Microsoft Ads'.
   `cnm_exact`/`cnm_slug` joined `qoyod_source='Microsoft Ads'` to BOTH rows → the upstream
   emitted the same Microsoft leads under channel='microsoft' AND 'microsoft_ads' (42 each).
   Fix: removed the legacy `microsoft` slug row → one slug per qoyod_source.

**Verification harness:** map qoyod_source→channel slug, sum `leads_total` per channel
from `hubspot_leads_module_daily`, compare to per-channel `SUM(leads)` from the view for
the SAME window; bar = ratio ≤ 1.05 on EVERY paid channel (google/meta/snapchat/tiktok/
microsoft_ads), not just the org total. `organic_search` shows a stray ~1 lead (fractional
proportional-spend rounding, not paid, HubSpot=0) — immaterial, out of paid scope.

--- ORIGINAL DIAGNOSIS (kept for history; the "re-join" hypothesis was partially right —
    the C/D re-joins did inflate, but the PRIMARY snapchat fan was the upstream casing) ---

## v_ad_performance leads fan-out NOT fully fixed — per-channel recon fails (found 2026-06-09, post-fix)

- **Symptom:** After the name-grain/fan-out fix (commit 13c76e4), the 14d AGGREGATE
  reconciliation passed (1585 ≤ HubSpot 1843) but **per-channel it still over-counts**.
  Live recon 2026-06-02..2026-06-08 (`v_ad_performance` collapsed to canonical channel
  vs `hubspot_leads_module_daily.qoyod_source`):
  - Google Ads 308 vs 332 — **0.93 OK** (only clean channel)
  - Meta 101 vs 54 — **1.87 OVER**
  - Snapchat 316 vs 148 — **2.14 OVER**
  - TikTok 128 vs 63 — **2.03 OVER**
  - Microsoft 84 vs 21 — **4.00 OVER** (and see channel-label dup below)
- **Why the aggregate "passed" and hid this:** Google Ads is the largest channel and is
  clean, so it dominated the total and masked 2x over-counts on the 4 smaller channels.
  **Rule: a reconciliation that only checks the org-wide total is worthless — ALWAYS
  reconcile per-channel.** A clean total can hide compensating per-channel errors.
- **Root cause (located):** The **upstream `utm_paid_attribution_daily` is CORRECT** at
  source grain (snapchat 172, meta 54 EXACT, tiktok 63 EXACT, google_ads 332 EXACT vs
  HubSpot truth). The over-count is introduced **downstream inside `v_ad_performance`'s
  own platform↔HubSpot re-join**: the leads window guard partitions by `lead_src_key`
  (AB-bucket = `AB|date|channel|utm_campaign|utm_audience|utm_content`, raw casing), but
  the view produces MORE distinct AB-combos than HubSpot has buckets (Snapchat: view 101
  AB-combos / 311 leads vs HubSpot 80 buckets / 148 leads), so the guard under-dedups —
  one HubSpot lead bucket is split across multiple platform `(campaign × audience)` rows
  that all share the same `ad_id`+`utm_content`, and each retains a slice of the leads.
  Casing is NOT the cause here (101 raw == 101 lowered AB-combos).
- **Fix needed (hand to developer):** Don't re-join HubSpot leads inside `v_ad_performance`
  at all — `utm_paid_attribution_daily` already has correct per-(date,channel,campaign,
  audience,content) leads. Pull leads/SQLs from the upstream view by its AB grain and let
  the platform side supply only spend/impr/clicks/ids. OR: build `lead_src_key` from the
  HubSpot row's OWN identity (its source primary grain), not from the joined platform
  fields, so it is constant per HubSpot bucket regardless of how many platform rows it lands on.
- **Channel-label duplication (separate bug, same view):** `v_ad_performance` emits BOTH
  `channel='microsoft'` (utm_proxy rows, $0 spend, 42 leads) and `channel='microsoft_ads'`
  (platform rows, $381 spend, 42 leads) for the SAME Microsoft leads (`Bing_AR_Brand_HubSpot`
  = 20 leads under both labels). The utm_proxy CTE labels Microsoft as `microsoft` while the
  platform side uses `microsoft_ads`; the dedup never collapses them → Microsoft double-counted.
  Fix: normalize the proxy channel string to `microsoft_ads` (match `campaigns_daily.channel`)
  before the union, same class as the `microsoft`/`microsoft_ads` map trap already documented.
- **Verified clean reference:** HubSpot leads matching a platform utm_content (lowered, channel
  grain): Snapchat 143, Meta 48, Google 264 — these track HubSpot's qoyod_source totals; the
  view's inflated numbers do not.

## v_ad/v_adset platform CTE grouped by NAME, lost ad_id + fanned leads 3.5x (fixed 2026-06-09)

- **Symptom:** Two ads sharing a `utm_content`/`ad_name` but with different `ad_id`s
  collapsed into ONE row in `v_ad_performance` — `ANY_VALUE(ad_id)` kept one ID and merged
  both ads' spend. Live BQ: 370 spend-bearing merged groups, $7.8k/30d. `v_adset_performance`
  had the same trap on `adset_id` (63 groups, $4.8k/30d).
- **Worse, hidden second bug:** the `platform`↔`hubspot` FULL OUTER JOIN keys on
  `utm_content` (resp. `utm_audience`), so one HubSpot row matched MANY platform name-rows
  and `COALESCE(h.leads,…)` repeated on each → leads over-counted **3.57x** (v_ad_performance
  14d = 5111 leads vs HubSpot truth 1433). The old spend window guard only deduped
  spend/impr/clicks, never leads or deals.
- **Fix:** add `ad_id` (resp. `adset_id`) to the `platform` GROUP BY so each distinct ID
  keeps its own row + spend. Then restructure the final SELECT into a `joined` CTE + outer
  SELECT with THREE window guards: (1) spend/impr/clicks once per ID (existing), (2) **leads
  once per HubSpot source-row** via `lead_src_key` = a string encoding which bucket won
  (`AB|date|channel|campaign|audience|content`, `C|date|channel|id`, `D|date|campaign_id`),
  (3) **deals once per deal-bucket grain** (ID bucket = date×channel×sync_id; name bucket =
  date×channel×utm_campaign×utm_content). Ratios/CPL/CPQL use the RAW (un-zeroed) lead/spend
  so per-row metrics stay correct; only SUM-able columns are zeroed on duplicate rows.
- **Verified:** Check A 370→0 (collapse structurally impossible, ad_id now in grain; the
  370 groups surfaced as 819 distinct ad_id rows). Leads 5111→1585 ≤ HubSpot 1843 (no
  fan-out). Spend held to the penny: v_ad 18270.01 == ads_daily 18270.01.
- **Trap to remember:** any view that GROUP BYs platform data by a NAME column while carrying
  the ID via `ANY_VALUE` will silently merge same-name distinct-ID entities. Always group by
  the ID. And any FULL OUTER JOIN of platform→HubSpot on a name fans HubSpot metrics — guard
  leads AND deals, not just spend. `materialize_heavy_views` lives in `collectors/views.py`
  (NOT `bq_writer`).

## Period windows must end at the last COMPLETE spend day, not "yesterday" (found 2026-06-09)

**Symptom:** Running the 7d-vs-prior period compare on 2026-06-09 with a yesterday-
anchored window (CUR 06-02..06-08) showed Meta CPQL spiking and a wild FORECAST pace
of spend −72% MoM. **Cause:** `campaigns_daily` had NO spend rows for 2026-06-08 yet —
the nightly collector hadn't landed before 08:00 Riyadh (same "data legitimately 2 days
old" reason behind the health_check ≥3-day freshness threshold). The window's last day
was spend=$0 but leads were present, deflating spend/CPQL and exaggerating the MoM gap.
**Fix:** Before fixing window bounds, query `SELECT date, SUM(spend) FROM campaigns_daily
GROUP BY date ORDER BY date` for the tail and set the window END to the last date with
non-trivial spend (here 06-07), not `CURRENT_DATE()-1`. Re-running on 06-01..06-07 vs
05-25..05-31 gave coherent, trustworthy numbers (total CPQL $58.6 cur vs $81.4 prior,
−28%). **Rule:** anchor period windows to the last complete spend day; never trust a
window whose final day shows $0 spend with non-zero leads.

## v_adset_performance — spend fan-out inflates CPQL (found 2026-06-09)

**Symptom:** Meta "CPQL +25% regression" (reported $37→$46 last-7d vs prior-7d)
was a measurement artifact, not a real decline. `v_adset_performance` over-counted
CUR-window Meta spend $1,052 vs raw $742 (`campaigns_daily`/`adsets_daily` deduped
both = $742). Entire gap was ONE day: 2026-06-07 view spend $500 vs raw $190.
**Cause:** adset `Meta_LeadGen_Invoice_Intersts/JobTitles_Instantform` (adset_id
120248894675830198, $103) appeared **4× in the view** on 06-07 — its `utm_audience`
matched multiple HubSpot lead-grain rows and spend was NOT pre-aggregated before the
join, so each match repeated the full $103 → $412. Same fan-out class as
campaign_health.py Bug 1 (2026-05-18), but inside the VIEW definition this time.
**Fix needed (hand to performance-lead/developer):** pre-aggregate spend per
(date, channel, adset_id) in a CTE inside `v_adset_performance` BEFORE the LEFT JOIN
to the HubSpot adset-grain CTE — mirror the `cd` CTE pattern already in campaign_health.py.
**Verification done my own CTE join (deduped spend + pre-agg HS on lead_utm_audience,
source IN fb/ig/meta): true Meta CPQL $42→$37 (IMPROVED).** Always cross-check view
totals against raw `adsets_daily`/`campaigns_daily` (deduped) before trusting a CPQL delta.

**FIXED 2026-06-09 (`collectors/bq_writer.py`).** Two fix attempts — the first was WRONG,
caught by testing:
- ❌ Adding the campaign to the platform↔hubspot JOIN key fixed spend BUT inflated leads
  (snapchat 125→185) — it made `h.leads` NULL more often, over-triggering the Strategy-D
  campaign-ID fallback (sprays campaign leads across adsets). Don't change the join.
- ✅ Correct fix: a **window-dedup** on the platform-side metrics only — wrap spend/
  impressions/clicks in `IF(ROW_NUMBER() OVER (PARTITION BY date,channel,adset_id ORDER BY
  …)=1, metric, 0)` so a fanned row counts them ONCE. Lead attribution + C/D fallbacks
  untouched. Same fix in `v_ad_performance` (partition by ad_id). Verified live-vs-live:
  spend → adsets_daily truth (Meta $742, Snap $3457, TT $1623, MS $318), **leads/SQL byte-identical.**
- ⚠️ **GOTCHA that wasted time:** `v_adset_performance` / `v_ad_performance` are
  **materialized TABLEs** (rebuilt nightly via `materialize_heavy_views`), NOT live views.
  When validating a view-SQL fix, compare a **fresh live recompute vs another live recompute** —
  NOT against the stale materialized TABLE (its row set is yesterday's, so leads look "changed").
  Re-materialize with `CREATE OR REPLACE TABLE` (the DROP-TABLE path is hook-blocked).

## Pause precedence — channel-dependent surgical cleanup runs before campaign-pause

- **Rule (confirmed 2026-05-17):** A campaign hitting the pause threshold
  (CPL > $50 / CPQL > 3× warning for 7+ days) is NEVER auto-paused at the
  campaign level until surgical cleanup has happened first. The surgical
  surface is CHANNEL-DEPENDENT:
  - **Social** (meta, snapchat, tiktok): pause bad ADS first. The ad IS
    the targeting decision; one bad creative can poison the average.
  - **Search** (google_ads, microsoft_ads): pause bad KEYWORDS first AND
    review the landing page. The keyword IS the targeting decision; ad-
    level pause on search channels is the WRONG first step. LP issues
    (broken form, slow load, intent mismatch) masquerade as ad/keyword
    problems and require manual verification.
- **Ad-level pause rules — SOCIAL ONLY** (mirrored in `scripts/bulk_ads.py`
  AND `analysers/campaign_health.py::_campaigns_with_ad_pause_candidates`).
  Helper hard-filters to `channel IN ('meta', 'snapchat', 'tiktok')`:
  - `zero_conv`: spend > $70, 7+ days, 0 platform conversions
  - `high_cpl`:  CPL > $50, 10+ days (`AD_CPL_PAUSE` in config.py)
  - `junk_lead`: 10+ days, hs_leads ≥ 5, disq_rate ≥ 60%
- **Keyword-level pause rules — SEARCH ONLY** (mirrored in
  `executors/keyword_policy.py` AND
  `analysers/campaign_health.py::_campaigns_with_keyword_pause_candidates`).
  Helper hard-filters to `channel IN ('google_ads', 'microsoft_ads')`:
  - `zero_conv`: spend > $35, 14+ days, 0 conversions
  - `high_cpl`:  CPL > $80, 14+ days, 1+ conversions
- **LP review (mandatory on search before campaign-pause):** For any search
  campaign hitting pause-zone, the team manually visits the destination LP
  to verify load speed, form submission, and keyword-intent alignment. The
  QA gate enforces this — campaign-pause on a search channel is blocked
  even with no flagged keywords, mandating LP review.
- **Enforcement (defense in depth):**
  1. `campaign_health.py` pre-fetches BOTH ad-level + keyword-level
     candidates per campaign before the action loop. When action would be
     "pause", it routes by channel:
     - Social → check ad candidates → downgrade to "drilldown" with top 5
       worst ads listed
     - Search → check keyword candidates → downgrade to "drilldown" with
       top 5 worst keywords + LP review instructions (even if no keywords
       flagged, LP review is mandatory)
  2. `qa/checks.py::check_pause_precedence` (wired into `verify_asana`)
     is channel-aware: looks up the campaign's channel from BQ, then
     checks the right candidate type. Blocks any unauthorized campaign-
     pause Asana task. Search-channel tasks are blocked even with no
     flagged keywords because LP review can't be detected automatically.
- **Why both layers:** even if a future analyser/human bypasses the
  analyser's downgrade and submits a campaign-pause task directly, the
  gate blocks it at the Asana surface. Single source of truth lives in
  `_campaigns_with_ad_pause_candidates()` (social) and
  `_campaigns_with_keyword_pause_candidates()` (search).

## Activity dashboard: parallel BQ futures silently overwritten by sequential re-runs

- **Symptom (2026-05-16):** `reports/app.py` had a `ThreadPoolExecutor(14)` block that
  ran all 14 SQL queries in parallel, but cold-load latency was still 12–20s and
  results were sometimes stale.
- **Root cause:** Seven downstream code blocks (`user_sql`, `intel_sql`, `ts_sql`,
  `exec_sql`, `fu_sql`, `new_ads_sql`, `hc_sql`/`fresh_sql`) redefined the same SQL
  strings and re-ran `bq.query().result()` **sequentially after the parallel block**,
  overwriting the fast parallel results with slow serial ones. The parallel block was
  doing real work; it was just wasted.
- **Fix:** Deleted all 7 duplicate sequential blocks (–352 lines). All 14 queries now
  come exclusively from the `ThreadPoolExecutor` futures. Cold load: ~2s. Commit: `34af5fb`.
- **Rule:** After adding a parallel executor, grep for any re-use of the same SQL
  variable names or `bq.query()` calls below the executor block — they will silently
  overwrite the parallel results.

## Railway domain: nexa-web-production-6a6b, NOT nexa-performance-agent

- **Symptom (2026-05-15):** Dashboard link returned Railway 404.
- **Root cause:** Memory had `nexa-performance-agent.up.railway.app` which was the
  trial personal-account project (deleted). The live Pro project auto-assigned domain
  is `nexa-web-production-6a6b.up.railway.app`.
- **Fix:** Run `railway variables` to read `ACTIVITY_DASHBOARD_URL` directly from the
  live project — that is always the canonical URL. Commit: `c280ac9`.
- **Rule:** Never hard-code Railway URLs in memory — always verify with `railway variables`.

## Multi-account collectors: pool rows before upsert (NEVER upsert per-account)

**Symptom (2026-05-15):** Microsoft Ads account 188176729 appeared dormant since
April 24 in BQ even though the API returned real spend for May 10-14. Yesterday's
(May 14) spend of $981.54 was completely missing for that account.

**Root cause:** `collectors/microsoft_ads_bq.py` looped `for acc in accs:` and
called `upsert_rows(...)` once per account. `upsert_rows` derives its DELETE
scope from `key_fields`. Since `key_fields=["date","channel","campaign_id"]`
shares `channel='microsoft_ads'` across both accounts, account-2's
DELETE-then-INSERT wiped account-1's rows for every overlapping (date, channel)
partition before re-inserting only its own data.

**Fix:** Pool rows from ALL accounts into a single `all_rows: list[dict] = []`,
then call `upsert_rows()` ONCE at the end of the function. Applied to all 4
functions: `collect_and_write`, `collect_adsets_and_write`,
`collect_keywords_and_write`, `collect_ads_and_write`.

**General rule:** Any collector that iterates over multiple accounts/sub-channels
that share `key_fields` MUST aggregate rows across the iteration and upsert
once. Per-iteration upserts on overlapping scopes cause silent data loss.

## UTM param → ad hierarchy level (must memorise)

| Ad-platform level | HubSpot UTM property        |
|-------------------|-----------------------------|
| Campaign          | `lead_utm_campaign`         |
| Ad Set / Ad Group | `lead_utm_audience`  ← NOT `lead_utm_medium` |
| Ad                | `lead_utm_content`          |
| Keyword           | `lead_utm_term`             |
| Source/channel    | `lead_utm_source`           |
| Channel-type      | `lead_utm_medium`  (cpc / paid_social — NOT an adset name) |

`lead_utm_medium` never carries the adset name. Adset name lives in
`lead_utm_audience`. `v_adset_performance` Strategy B already joins on
`lead_utm_audience` correctly. Date discovered: 2026-05-13.

## UTM dynamic tokens appearing as literals ({{placement}}, {{site_source_name}}, {keyword})
When these appear verbatim in BQ, the ad's UTM template was misconfigured — the platform
never substituted the dynamic value. Flag these leads as unattributed, do not treat the
literal string as a valid field value.

## ID property naming — different at every layer (DO NOT confuse)

The platform ad-group level has 4+ different names across our stack. Whenever
you write code or SQL touching IDs, match the name to the layer EXACTLY:

| Layer                              | Property / column name        | Notes                                       |
|------------------------------------|-------------------------------|---------------------------------------------|
| HubSpot **Contact** (0-1)          | `ad_group_id`                 | underscore between "ad" and "group"         |
| HubSpot **Contact** (0-1)          | `campaign_id`                 | populated by URL parameter capture (hsa_*)  |
| HubSpot **Contact** (0-1)          | `ad_id`                       | custom property — needs explicit URL capture|
| HubSpot **Lead Module** (0-136)    | `lead_adgroup_id_sync`        | "adgroup" as ONE word, NO underscore        |
| HubSpot **Lead Module** (0-136)    | `lead_campaign_id_sync`       | calculated property — mirrors contact       |
| HubSpot **Lead Module** (0-136)    | `lead_ad_id_sync`             | calculated property — mirrors contact       |
| HubSpot **Deal** (0-3)             | `deal_adgroup_id_sync`        | "adgroup" as ONE word, NO underscore        |
| HubSpot **Deal** (0-3)             | `deal_campaign_id_sync`       | calculated from contact                     |
| HubSpot **Deal** (0-3)             | `deal_ad_id_sync`             | calculated from contact                     |
| BigQuery `adsets_daily` table      | `adset_id`                    | Meta/TikTok/Snap term (Google = ad_group)   |
| BigQuery `ads_daily` table         | `ad_id`                       | universal                                   |
| BigQuery `campaigns_daily` table   | `campaign_id`                 | universal                                   |
| BigQuery `v_adset_performance` view| `adset_id`                    | exposed for dashboards (= adgroup_id sync)  |
| BigQuery `v_ad_performance` view   | `ad_id`, `adset_id`, `campaign_id` | exposed for dashboards               |

Critical mappings when joining:
- HubSpot **Contact** `ad_group_id` ≡ HubSpot **Lead** `lead_adgroup_id_sync` ≡ BQ `adset_id`
  (calculated property syncs contact → lead automatically; same ID value)
- HubSpot **Contact** `campaign_id`  ≡ HubSpot **Lead** `lead_campaign_id_sync` ≡ BQ `campaign_id`
- HubSpot **Contact** `ad_id`        ≡ HubSpot **Lead** `lead_ad_id_sync`       ≡ BQ `ad_id`

The collector and view code already uses these consistently. The trap is when
WRITING new queries against HubSpot's Search API — `ad_group_id` (Contact)
vs `lead_adgroup_id_sync` (Lead Module) IS different and HubSpot's API
returns 400 if you use the wrong one on the wrong object.

Date discovered: 2026-05-14.

## Deals sync — parallel runs duplicate the table

- **Symptom:** `hubspot_deals_daily` ends up with 1.5–2x more rows than HubSpot
  for the same window. Per-bucket counts show 2+ rows with `updated_at`
  timestamps seconds apart.
- **Cause:** Two `collect_and_write()` calls running near-simultaneously
  (e.g., I run a manual backfill while the 6h scheduler also triggers).
  The DELETE-before-INSERT in `upsert_rows()` is not transactional with the
  load job — each run's DELETE fires before either's INSERT, so both runs
  insert their full row set and neither's DELETE catches the other.
- **Fix when it happens:** TRUNCATE the table, run a single fresh YTD
  backfill (`railway run python -m collectors.hubspot_deals_bq`), verify
  dedupe with `COUNT(*)` vs `COUNT(DISTINCT full_key)` — should equal 1.00x.
- **Prevent:** Never run a manual deals sync without first checking
  scheduler logs for an in-progress run. If unsure, wait 6h between runs.
  Date discovered: 2026-05-13.

## BigQuery

- **Streaming buffer blocks DELETE for 90 min.** Rows inserted via streaming
  `insert_rows_json()` sit in a buffer invisible to DELETE/UPDATE. Fix:
  always use `load_table_from_file(BytesIO(ndjson))` — load jobs land in
  the partition instantly and are free. See `collectors/bq_writer.py`.
- **Query-too-large (>1MB).** DELETE with 1000s of key tuples in OR chains
  overflows. Fix: group by `date`, then `WHERE date=@d AND scope IN UNNEST(@sv)`.
- **Partition pruning requires a literal or param.** Don't do
  `WHERE date >= CURRENT_DATE() - INTERVAL 7 DAY` in a view definition; use
  it in queries, or pass params.
- **`upsert_rows` scope-field DELETE causes silent ghost-row accumulation.** When
  `key_fields=[date, scope_field, ...]`, the DELETE only removes rows where
  `scope_field IN (values present in the new build)`. If a lead's source changes
  between builds, the old row (old_source, same date) is NEVER deleted and
  accumulates. Fix: for tables rebuilt entirely per date (like
  `hubspot_leads_module_daily`), use `key_fields=["date"]` only — DELETE wipes
  the whole date partition before re-inserting. Found 2026-05-11: 60,156 rows /
  186,384 leads (5x inflated) vs correct 12,326 rows / ~26k leads. Repair:
  `DELETE WHERE TRUE` + `_rebuild_daily_buckets` for all 131 dates. Fixed by
  changing `_rebuild_daily_buckets` key_fields to `["date"]`.

## HubSpot deal amounts in BQ are correctly USD — verified 2026-05-09

- **`hubspot_deals_daily.amount_total` and `amount_won` ARE USD** (the collector's
  `to_usd()` works correctly). `amount_*_native` columns hold the original SAR.
- Verified by direct API check on 2026-05-09: deal `499825686757`
  ("مؤسسة عجوة نخلة"), HubSpot raw `amount`=12255, `deal_currency_code='SAR'`,
  BQ `amount_won`=$3268, `amount_won_native`=12255 SAR. Math: 12255/3.75=3268 ✓.
- A previous "rule" instructing to divide by 3.75 in dashboards was based on an
  incorrect comparison against Funnel/Looker (which displays SAR). It was
  reverted across all Hex SQL and `analysers/campaign_health.py` on 2026-05-09.
- **Use BQ deal/revenue columns as-is. Do NOT divide by 3.75.** Spend is USD,
  deal/revenue is USD, ROAS is unitless.
- The `_native` columns remain available for users who explicitly want SAR.

## Channel name mismatch: `microsoft` vs `microsoft_ads`

- **`v_channel_key_map` originally used `microsoft`** as the paid_channel
  key, but every collector writes `channel='microsoft_ads'` to the daily
  tables. Result: any Hex tile that joined via `v_channel_key_map`
  silently dropped Microsoft Ads (no error, just blank). Fixed in
  `collectors/views.py` on 2026-05-06 by changing `microsoft` →
  `microsoft_ads` in both the CASE branches and the UNNEST list. Run
  `python -c "from collectors.views import refresh_all_views; refresh_all_views()"`
  to push the view update to BQ.
- **Future-proofing:** the channel name in `v_channel_key_map` MUST equal
  `campaigns_daily.channel` (collector output) exactly. If you add a new
  channel, write it the same way in both places.

## bq_writer schema vs live BQ schema drift

- **`ADS_DAILY_SCHEMA` (and other TABLES schemas) in `collectors/bq_writer.py`
  must match the live BQ table.** When they don't, load jobs fail with
  cryptic `"No such field: <name>"` even though the field exists in the
  destination table.
- **Why:** Even with `ALLOW_FIELD_ADDITION`, BQ validates each input row
  against the **supplied** schema, not the destination's. The flag only
  allows the destination to GROW; rows can't carry fields the supplied
  schema lacks.
- **Fix when adding new collectors:** before writing rows with a new field
  (e.g. `cpl`, `frequency`), verify the field exists in
  `bq_writer.<TABLE>_SCHEMA`. If not, add it. Specifically `cpl` was added
  to `ADS_DAILY_SCHEMA` on 2026-05-06 to fix MS Ads `collect_ads_and_write`.

## TikTok Marketing API OAuth

- **Auth URL host is `business-api.tiktok.com`, NOT `business.tiktok.com`.**
  Using the latter redirects to `/not-found`. The Marketing API portal lives
  on the API subdomain. Fixed in `scripts/tiktok_oauth.py`.
- **Token lifetimes:** access_token = 24 h, refresh_token = 365 d. Daily
  `--refresh` runs needed unless the collector auto-refreshes per call.
- **Redirect URI must be registered** at TikTok Developer Portal → app →
  Settings → Redirect URIs: `http://localhost:8080/tiktok/callback`.

## Microsoft Ads REST Reporting API (May 2026)

- **Correct endpoint:** `https://reporting.api.bingads.microsoft.com/Reporting/v13/GenerateReport/Submit`
  (not `/api/advertiser/reporting/v13/...` — that path doesn't exist).
  Polling: `/Reporting/v13/GenerateReport/Poll`.
- **`ReportRequest` body must include `Type` field** as REST discriminator,
  e.g. `"Type": "CampaignPerformanceReportRequest"`. Without it, API returns
  `400 NullRequest "request message is null"` even though the JSON is valid.
- **`Scope.AccountIds` must be a flat int list,** not the SOAP-style
  `{"long":[id]}` wrapper. Wrong format = same NullRequest error.
- **Column name differences vs SOAP API:**
  - AdGroupPerformanceReport: use `Status` (NOT `AdGroupStatus`)
  - KeywordPerformanceReport: use `BidMatchType` (NOT `MatchType`)
  Both fail at submit time with cryptic "Invalid JSON at position N. Path: $.Columns[X]".
- **`AADSTS650052` resolution:** qoyod.com Azure AD tenant didn't have the
  Microsoft Advertising service principal. Fixed by Global Admin running:
  `New-MgServicePrincipal -AppId "d42ffc93-c136-491d-b4fd-6f18168c68fd"`.
  Once SP exists, work account OAuth on `/common/` works. Tenant ID:
  `8b6fc4da-1c24-432f-b089-2355d22f028d`.

## Microsoft Ads OAuth

- **Work accounts (Azure AD) are blocked.** Signing in with `@qoyod.com`
  (work account) returns `AADSTS650052` (no service principal in tenant)
  or `AADSTS65002` (first-party preauthorization required). Microsoft only
  preauthorizes their own apps + approved partners — there is no admin-
  consent workaround for customer-registered apps.
- **Fix: use a personal Microsoft account.** Rana already has a personal
  MS account using `rana.khalid@qoyod.com` (separate identity from the
  work account — Microsoft allows both with the same email). The OAuth
  picker shows both; pick "Personal account – Created by you".
- **Endpoint must be `/consumers/`** in `scripts/microsoft_oauth.py` —
  `/common/` lets Azure route to the work account and fail. The script
  is hard-coded to consumers.
- **Redirect URI must match Azure exactly.** Registered:
  `http://localhost:8080/ms-ads/callback` (not `/microsoft/callback`).

## HubSpot

- **10,000-result hard cap on Search API.** After `after=10000` returns 400.
  Fix: walk N-day windows (we use 7-day windows), reset `after` per window.
- **Lead module is object `0-136`**, separate from Contacts. Use
  `/crm/v3/objects/0-136/search`, not `/contacts/search`.
- **READ-ONLY.** Never PATCH/DELETE/CREATE HubSpot objects without explicit
  user approval in Slack. User reminded this multiple times.
- **Canonical `lead_qoyod_source` internal names (verified 2026-05-11 from HubSpot property editor):**
  ```
  Google Ads       Microsoft Ads    Meta Ads
  Snapchat Ads     Tiktok Ads       LinkedIn Ads
  ```
  `Tiktok Ads` has a lowercase 'i' — NOT `TikTok Ads`. All BQ channel_maps,
  `QOYOD_SOURCE_TO_CHANNEL` in `channel_inference.py`, and the views in
  `collectors/views.py` must use these exact strings. Any mismatch causes
  leads to silently drop from dashboard joins.
- **`HUBSPOT_ACCESS_TOKEN` is NOT in the local `.env` — it lives on Railway.**
  Any local CLI run (`python -m collectors.hubspot_leads_bq mirror`) MUST use
  `railway run python -m collectors.hubspot_leads_bq mirror`. Without `railway run`
  the token is `None`, every HubSpot API call returns 401, and the failure
  happens inside `_load_pipelines()` at startup before any data is fetched.
  Confirmed 2026-05-11.
- **Unicode arrows crash `print()` on Windows** — `→` (`→`) maps to
  `undefined` under `cp1252` (Windows default console encoding). Replace with
  `->` in any `print()` or `f-string` that is not inside a `sys.stdout.reconfigure`
  block. Symptom: `UnicodeEncodeError: 'charmap' codec can't encode character '→'`
  before any work is done.

## Meta — November 2025 deprecations

Tested and confirmed:
- ❌ `page_impressions` — use `page_impressions_unique` (reach)
- ❌ `page_fans` — use `page_follows`
- ❌ `page_fan_adds` — use `page_daily_follows_unique`
- ❌ `page_impressions_organic` / `page_impressions_paid` — gone
- ✅ `page_post_engagements` — still works
- ✅ `page_views_total` — still works
- ✅ `page_daily_follows` — still works

IG insights:
- ❌ `impressions` — gone; use `reach` as the closest daily metric
- ✅ `reach` — true daily time-series (period=day)
- ⚠️ `profile_views`, `website_clicks`, `accounts_engaged`,
  `total_interactions` — require `metric_type=total_value` and can't be mixed
  in the same call with day-series metrics. Fetch separately; attribute the
  aggregate to the end_date row.

## Snapchat

- ❌ `conversion_lead` field does NOT exist (we assumed it did)
- ❌ `total_conversions` also rejected by most accounts
- ✅ Safe set: `impressions, swipes, spend, conversion_sign_ups`
- Spend is in **micro-currency** (divide by 1,000,000)
- ❌ `currency`, `spend_native`, `currency_native` are NOT in `campaigns_daily`
  schema. Do NOT include them in snap_bq.py rows — BQ returns 400 BadRequest.
  Snap always converts to USD before writing; native fields were removed.

## Google Ads

- **Customer ID must have NO dashes** in API calls. `_customer_ids()` strips.
- `login_customer_id` is the MCC, not the child account.
- PMax campaigns have **no ad groups**; they have **asset groups**. Requires
  a different query (`asset_group` resource).
- **A PMax `asset_group` IS the adset grain — same level as an ad set / ad group.**
  PMax has no ad-group level, so its asset group occupies the adset slot. In BQ they
  are **merged into `adsets_daily` / `v_adset_performance`** (NOT a separate grain),
  carry **`utm_audience`** (the adset-level UTM, like Meta ad set / Google ad group /
  Snap ad squad / LinkedIn campaign / TikTok ad group), and are **excluded from the
  ads grain** (`ads_daily`). So the 4 grains are campaign · **adset (incl. PMax asset
  group)** · ad · keyword. Built by `_build_pmax_asset_group_rows_for_adsets()` in
  `collectors/google_ads_bq.py`; merged 2026-06 (commit `eda263e`).
- Cost in **micros** (`cost_micros / 1_000_000`).
- **Keyword policy is centralised in `executors/keyword_policy.py`.** Don't
  duplicate ALWAYS_NEGATIVE / BRAND_ONLY / NEVER_NEGATIVE patterns into other
  files — import from the policy module. قيود/qoyod variants are BRAND_ONLY
  (only allowed in campaigns whose name contains `Brand`). Always-negative
  terms (login / مجاني / دورة / تحميل / قرض / تمويل / وظيفة + EN equivalents)
  are dropped from `add_kw` even if they converted, and direct-executed as
  EXACT negatives when they appear with 0-conv spend.
- **Arabic "قيود" is ambiguous.** It can mean either the company name "Qoyod"
  OR the accounting noun "journal entries". The policy module disambiguates by
  checking for accounting modifiers (`محاسبية` / `المحاسبة` / `يومية` /
  `اليومية`). Terms like `قيود محاسبية` and `قيود المحاسبة` are FEATURE
  keywords (treat as normal); only standalone `قيود`, `برنامج قيود`, `نظام قيود`,
  `qoyod` etc. are brand-only. If you ever see one of those feature-noun
  combinations flagged as a brand violation, the disambiguation list needs
  another modifier added.
- **Competitor patterns must be distinct, not common Arabic words.** Wafeq
  (`وافق` = also "agreed") and Manager.io / Al-Ostaz (`الاستاذ` = also "the
  teacher/Mr.") are common false-positive risks. Use only the specific
  spellings that don't collide with everyday Arabic: `wafeq`, `وافيق`,
  `الاستاذ المحاسبي` (full phrase), not the bare ambiguous form.
- **Removing a negative keyword is safe — re-adding is the risk.** Removing
  `qoyod` or competitor names as negatives just re-opens those queries to
  match in the right campaign. The audit `scripts/audit_active_negatives.py`
  direct-executes removals (no approval) because it can't make money go
  somewhere it shouldn't. ADDING negatives still requires the patterns to
  pass the policy check first.
- **Search-term audit produces 4 buckets, not 2.** Old pattern was add_kw +
  add_neg. New pattern: add_kw, add_neg (regular wasted), auto_neg
  (always-negative direct-execute), pause_watch (brand/competitor/lang —
  flag for human, never auto-execute either way). Don't conflate auto_neg
  with pause_watch — auto_neg fires immediately, pause_watch surfaces an
  Asana task and waits.
- **Keyword cadence: WEEKLY for adds + pauses, DAILY for negatives.** New
  keyword expansion task and `audit_and_pause_nonconverting_keywords` only
  fire on Sunday Riyadh (`weekday() == 6`). Negatives still direct-execute
  daily. Override for testing: `FORCE_WEEKLY_KEYWORDS=1`. Helpers:
  `_is_weekly_keyword_day()` exists in BOTH `analysers/google_ads_audit.py`
  and `analysers/google_ads_audit_tasks.py` — change them in lockstep if the
  weekday convention ever changes.
- **30-keyword-per-adgroup cap.** Before proposing additions,
  `filter_kw_against_adgroup_cap` queries existing enabled keyword counts
  per ad group and only keeps `(30 - existing)` highest-conv candidates per
  group. Dropped candidates carry a `drop_reason` for the Asana task body.
  This is enforced at audit time, not at execution time — `bulk_keywords.py
  add` doesn't re-check (yet).
- **QS<5 + lost-IS>80% combo.** Existing keywords matching this combo with
  zero historical spend (180-day window) → **DELETE**; with spend → **PAUSE**.
  GAQL note: `metrics.search_rank_lost_impression_share` IS available on
  `keyword_view` (despite docs being unclear). Aggregating in Python because
  GAQL with `segments.date` filter returns daily rows; we sum cost and take
  the latest QS / max lost-IS across the window.
- **CSV writer with variable-shape rows.** When `audit_active_keywords.py`
  emits both pattern violations and QS+IS-lost violations in one CSV, rows
  have different keys. Use the union of all keys + `extrasaction='ignore'`
  on `csv.DictWriter` so it doesn't crash on the first short row.
- **`change_status.resource_change_operation` is NOT a valid GAQL field**
  in v23 (despite some older docs/examples). To estimate keyword age, use
  first-impression date via `keyword_view` + `metrics.impressions > 0`
  with a 365-day window. That's what `keyword_policy.keyword_first_impression_dates`
  does. Newly-added keywords without any impressions return empty → treat
  as age 0 → age guard skips them (safe default).
- **Age guard: 10 days minimum.** `MIN_KEYWORD_AGE_DAYS = 10` in config.
  Performance-based pause (Rule A: spend>$80/0-conv) and the QS+IS-lost rule
  both check `keyword_first_impression_dates()` first. ALWAYS-NEGATIVE
  bypass — login/دورة/تحميل etc. are policy violations, not performance
  decisions, so they get paused immediately at any age.
- **Sunday is `weekday() == 6`.** The Saudi work week starts Sunday, so
  Sunday Riyadh runs the keyword auto-fix and Monday Riyadh posts the
  weekly summary. The summary reads Sunday's BQ activity log entry
  (`role='keyword_approval'`, `action='weekly_autofix'`) within a 36-hour
  window so timezone slop doesn't drop it.
- **Keywords NEVER post to Slack.** Expansion candidates → Asana only.
  Negatives → direct-execute silently. The old Slack-approval workflow
  (`post_keyword_approval` / `pending_keyword_approvals.json` /
  `check_and_execute_pending`) was removed in 2026-05. If a re-introduction
  is ever proposed: don't.

## Windows / Python 3.14 / Console encoding

- Arabic page names crash `print()` on Windows console (cp1252). Fix at
  script top:
  ```python
  try: sys.stdout.reconfigure(encoding="utf-8")
  except Exception: pass
  ```

## Replit

- **Don't overwrite root `.replit`** — it runs the agent (`main.py daily`).
  Put dashboard `.replit` in `dashboard/` if deploying as separate repl.
- **Service account JSON on Replit:** use
  `GOOGLE_APPLICATION_CREDENTIALS_JSON` secret (paste the JSON string),
  NOT `GOOGLE_APPLICATION_CREDENTIALS` (which expects a file path that
  doesn't exist on Replit).

## LinkedIn

- **Access tokens: 60 days. Refresh tokens: 365 days.** Use
  `scripts/linkedin_refresh.py --write-env` weekly. Silent expiry = silent
  collector failure (returns 0 rows, no exception).
- **Header `LinkedIn-Version: 202502`** required on every call (bump ~twice/year).
  Versions 202410 and 202504 are retired → 426 NONEXISTENT_VERSION.
- **DO NOT send `X-Restli-Protocol-Version: 2.0.0` with v202502.** This header
  causes 400 "Projected field not present in schema CampaignGroupV4/CampaignV8/
  AdAnalyticsV6" on every endpoint. Remove it entirely — v202502 works correctly
  without it.
- **DO NOT pass `fields=` projection params** on `adCampaignGroups` or `adCampaigns`.
  They are rejected when the Restli 2.0 header is absent. Return full objects and
  read what you need from the response.
- **MUST pass `fields=` on `adAnalytics`.** Unlike the metadata endpoints, the
  analytics endpoint silently omits any field you don't explicitly request. Without
  `"fields": "costInLocalCurrency,impressions,clicks,externalWebsiteConversions,dateRange,pivotValues"`,
  `costInLocalCurrency` is absent from every row → all spend appears as $0 in BQ.
  Verified 2026-05-10: account had $2,769 YTD real spend but BQ showed $0 until
  the `fields` param was added. Fixed in `_fetch_analytics()` in `collectors/linkedin_bq.py`.
- **Campaigns must use the account-scoped URL:**
  `/rest/adAccounts/{acct_id}/adCampaigns` — NOT `/rest/adCampaigns`.
  The global endpoint needs `search.account.values[0]` param which conflicts
  with removing the Restli 2.0 header. Account-scoped URL needs only `q=search`.
- **`adAnalytics` has pivot-explosion limits.** Requesting `pivot=CREATIVE`
  with wide date range paginates slowly — keep windows ≤ 7 days.
- **Lead Gen Forms bypass UTMs.** Leads from LinkedIn native forms land in
  HubSpot with `qoyod_source='LinkedIn'` but `utm_campaign=NULL`. They'll
  bucket into `__no_utm__`. Real fix: pull `/rest/leadFormResponses` and
  join by `form_id → campaign_id`.
- **Campaign names aren't on `adAnalytics`.** Must bulk-fetch via account-scoped
  `/rest/adAccounts/{acct_id}/adCampaigns` and join.

## Snapchat (extended)

- **DAY granularity rejects end_time in the future.** Always cap `end = date.today() - timedelta(days=1)`. Passing `date.today()` means `end_exclusive = tomorrow` which Snap rejects. Applies to both `collect_and_write` and `collect_adsets_and_write`.
- **Access token expires after 30 min — per-account refresh is NOT enough for large accounts.** 1,000 ads × 5 date-chunks = 5,000 API calls → can take 1–4 hours. Even a per-account refresh at loop start expires mid-account. Fix: track `token_refreshed_at = time.monotonic()` and renew with `token = _refresh_access_token()` whenever `time.monotonic() - token_refreshed_at > 1500` (25 min) inside the per-ad/per-adset inner loop. Applies to `collect_ads_and_write` and `collect_adsets_and_write`.
- **`ZoneInfo("UTC")` crashes on Windows** when the `tzdata` package is absent from the system timezone database. Fix: `if not tz_name or tz_name.upper() == "UTC": tz = timezone.utc` — use `timezone.utc` directly rather than `ZoneInfo("UTC")`.
- **Conversion fields are per-account.** Safe across every account:
  `conversion_sign_ups`. Others (`conversion_purchases`, `conversion_add_cart`,
  `conversion_start_checkout`, `conversion_save`, `conversion_subscribe`,
  `conversion_app_installs`) only work if configured on the Pixel. Collector
  now requests the broad set and falls back to `SNAP_STATS_FIELDS_SAFE` on 400.
- **Native currency is per-account; reporting is USD.** `_get_account()`
  detects each ad account's native currency and `collectors/currency.py`
  converts to USD via the SAR peg (`config.USD_SAR_PEG = 3.75`). Native
  values are preserved as `spend_native` / `currency_native`. If a new
  non-SAR/non-USD currency appears, add it to `PEG_RATES_TO_USD` in
  `currency.py` (and document the source — peg vs FX rate).
- **No adset/ad grain yet.** Dashboard can't drill below campaign.
  See `09_open_tasks.md`.

## Railway deployment

- **`logs/` and `cache/` are gitignored** — Python modules inside them won't
  deploy. Fix: change `.gitignore` to `logs/*.log` and `cache/*.json` so the
  `.py` module files are tracked.
- **`ALLOW_FIELD_ADDITION` in BQ load jobs needs `autodetect=True` or
  explicit schema fields** — without it, extra fields cause 400 BadRequest.
- **HubSpot webhook signature** used `hmac.new()` which doesn't exist in
  Python stdlib. `_verify_signature` now returns `True` (open endpoint).
- **Zapier webhook secret** in `.env` as inline comment was parsed as the
  value. Fixed by removing the check entirely (`_verify(): return True`).
- **Railway healthcheck on `/reports/latest`** causes rollback loops when
  `latest.html` doesn't exist on a fresh container. Removed healthcheck from
  `railway.toml`. Health is now checked via `/health`.

## Google Drive reports

- Reports (`latest.html`) are uploaded after every render. Flask falls back
  to Drive if local file is missing (new container after deploy).
- Requires: Drive API enabled in GCP + service account shared on folder
  with **Editor** access. See `memory/10_google_drive.md`.
- `GDRIVE_REPORTS_FOLDER_ID` env var (optional — defaults to `GDRIVE_FOLDER_ID`).

## Slack noise

- **Heartbeats**: `send_heartbeat()` only posts on `status='failed'`.
  Success/started statuses log to console only.
- **HubSpot webhook**: deal/lead handlers are log-only. Weekly agent run
  posts the aggregate channel summary — no per-event messages.

## OAuth (general)

- **Meta page tokens from long-lived user tokens are permanent** — don't
  bother refreshing. Use `scripts/meta_organic_setup.py` to derive.
- **Google refresh tokens** perpetual unless revoked in account settings.

## Campaign naming convention

- **Naming convention applies to NEW campaigns only.** Existing campaigns have
  varied legacy names that must be parsed as-is. Never reject or rename an
  existing campaign that doesn't match `{Channel}_{Type}_{Language}_{Product}_{Audience}`.
  The convention enforcer (`executors/naming.py`) is for campaign creation only.

## Leads & qualified leads terminology

- **Never use "SQLs" or "MQLs".** Those refer to the contact lifecycle stage
  stored in `hubspot_leads_daily` which is NOT used and never written to.
- The only valid source for lead counts and qualified lead counts is
  `hubspot_leads_module_daily` (`leads_total`, `leads_qualified`).
- A "qualified lead" = `leads_qualified` from the HubSpot Lead Module (object
  `0-136`). CPQL = spend / qualified leads. Never compute CPQL from
  contact-stage data.

## BQ column names (verified 2026-05-15)

- **`paid_channel_daily`**: columns are `leads_total` (not `leads`) and `qualified`
  (not `sqls`). Writing `leads` or `sqls` in SQL returns "Did you mean roas?".
- **`agent_activity_log`**: timestamp column is `ts` (not `created_at`).
- **`ARRAY_AGG ORDER BY … NULLS LAST` unsupported in BQ.** Replace with
  `ORDER BY COALESCE(nullable_col, 99999) ASC`.
- **`health_check.py` freshness threshold must be ≥ 3 days** (not > 1). Before
  08:00 Riyadh the nightly collector hasn't run so data is legitimately 2 days
  old. Threshold < 3 produces a nightly false-positive.

## Railway — single canonical project

- **Live project:** `nexa-performance-agent` in **Marketing Workspace** (Pro),
  ID `57f124d0-e254-4420-89f7-75baab4e6126`, service `85ed1a2a`.
- Personal-account project (`1b3ee05a`) **deleted** as of 2026-05-15.
- Always verify with `railway status` before deploying — must show
  `nexa-performance-agent / production / nexa-web`.

## Landing page mobile CSS (lp.qoyod.com)

- **RTL nav CTA scrolls off-screen:** When `<a class="qnav-cta">` is the last `<li>` inside `.qnav-links` (which has `overflow-x:auto`), it scrolls off the left edge in RTL on mobile. Fix: move it outside `</ul>` as a direct sibling, then use `order:2` + `justify-content:flex-start!important` in the 767px block.
- **`cta-band` false positive:** After deleting a cta-band widget, checking `'cta-band' in html` still returns True because orphaned CSS rules (`.cta-band{...}`) remain in the global style widget. Always check for the HTML section specifically: `re.search(r'<section[^>]*class="[^"]*cta-band', html)`.
- **Hero padding asymmetry in RTL:** Adding padding to `.hero-inner` instead of `.hero` behaves differently in RTL flex — left side appears clipped. Always put mobile padding on `.hero` directly: `padding:40px 16px!important`. The shorthand gives symmetric 16px L+R regardless of RTL.
- **Elementor cache outlives REST API upload:** After `PUT /wp-json/wp/v2/pages/{id}`, ALWAYS run: (1) `DELETE /wp-json/elementor/v1/cache`, (2) fetch the slug with `X-LiteSpeed-Purge: *` header. Without both steps the old rendered HTML is served.
- **Browser cache vs server:** User's phone showing old version ≠ server is wrong. Verify with `curl` + Android user-agent and check `x-cache-nxaccel: BYPASS`. If server is correct, the device needs incognito or cache clear.
- **Local JSON drift:** Local `el-data-{id}.json` can diverge from live if a session uploaded a different version. Always `GET /wp-json/wp/v2/pages/{id}?context=edit` and re-save before editing in a new session.
- **Single mega-widget pages (773):** All sections live in one widget. Nav, hero, cta-band, and all CSS are surgical HTML edits on one `html` field — no separate widget IDs.
- Full patterns: `memory/agents/cro/developer/lp-mobile-css-patterns.md`

## Google Ads multi-account: always use account_id from BQ, not config customer_id (2026-06-09)

**Trap:** `GOOGLE_ADS_CONFIG["customer_id"]` is one child account ID (1513020554), NOT the MCC.
Campaigns in the second child account (5753494964) get `RESOURCE_NOT_FOUND` when you build
`customers/{config_cid}/campaigns/{id}` — the campaign lives under a different CID.

**Fix:** `campaigns_daily` has an `account_id` column storing the child CID that owns each campaign.
Always query `SELECT campaign_name, campaign_id, account_id FROM campaigns_daily` and use
`account_id` (not config) to build the resource name:
```python
child_cid   = str(row.account_id).replace("-", "")
campaign_rn = f"customers/{child_cid}/campaigns/{row.campaign_id}"
result = add_negative_keywords(campaign_rn, kws, customer_id=child_cid)
```
Confirmed: account 5753494964 holds ImpressionShare_Invoice + E-invoice_Test;
account 1513020554 holds ZATCAPhase2 + Brand campaigns.

**Second bug found same run:** `add_negative_keywords` returns a list, not int. Guard:
`n = result if isinstance(result, int) else len(result)`

## Google Search negative keyword policy — informational modifiers that are NOT negatives (2026-06-09)

**Trap:** Proposing `طريقة` ("method / how-to") and `متطلبات` ("requirements") as phrase
negatives in ZATCA / e-invoice Google Search campaigns.

**Why they are NOT negatives:**
- `متطلبات` — "ZATCA requirements", "e-invoice requirements" = businesses being legally
  forced to comply. This is *exactly* our ICP. A search like `متطلبات الفاتورة الإلكترونية`
  is from a buyer in the compliance-mandate funnel, not an informational researcher.
- `طريقة` — "how to issue an e-invoice", "method for e-invoicing" = learning-intent queries
  that pair with our product keywords. The searcher needs a solution. Adding `طريقة` as
  negative would block this traffic everywhere it co-occurs with our target keywords.
- `كيفية` ("how to") — same logic as `طريقة`. Do NOT negate.

**What IS worth negating (fatoora terms):**
- `fatoora`, `fatoora platform`, `fatoora portal`, `ZATCA portal` — these route to the
  Saudi government's free compliance portal, not a paid SaaS. Intent is to use the
  government tool, not buy ours. Direct-execute as phrase negatives.

**Rule:** Only negate informational modifiers that lead to content consumption (دورة / كورس /
تحميل / نموذج مجاني) or to a specific competing free product (fatoora/ZATCA portal). Modifiers
that describe the buyer's **problem** (requirements, method, how-to) stay open — they bring us
the compliance-mandate audience we want. Corrected by Amar 2026-06-09.

## Landing page A/B test

- **Test start date: 2026-05-04.** HubSpot LP (`campaigns.qoyod.com`) has been live ~1 year. WordPress LP (`lp.qoyod.com`) launched for testing starting this date.
- **Never compare LP types using data before 2026-05-04.** Historical data is biased — HubSpot LP has 1 year of optimization, WordPress LP had no volume. All CPL/CPQL comparisons must use `week_start >= '2026-05-04'` as the filter.
- **Minimum test window: 2 weeks** before drawing conclusions. Check back ~2026-05-18 for a meaningful read.
- `v_lp_weekly_summary` and `v_lp_performance_weekly` views are set up and collecting from today. The Hex LP cell should always filter `week_start >= '2026-05-04'`.

## UTM → BQ field mapping (universal across all channels)

Every platform's data is stored with the following UTM-aligned field names.
Never use platform-specific names directly in BQ schemas or views.

| UTM param     | BQ field name  | Platform examples                             |
|---------------|----------------|-----------------------------------------------|
| utm_source    | channel        | "google_ads", "meta", "snapchat", "tiktok"    |
| utm_campaign  | campaign_name  | Campaign / Campaign Group (LinkedIn)           |
| utm_audience  | adset_name     | Ad Set / Ad Group / Ad Squad / Campaign (LI)  |
| utm_content   | ad_name        | Ad / Creative                                 |
| utm_term      | keyword_text   | Keyword (Google, Microsoft Ads)               |
| utm_medium    | placement      | Placement / Form name                         |
| utm_keyword   | keyword_text   | Same as utm_term — platform call it this way  |

LinkedIn-specific: Campaign Group = utm_campaign (stored as `campaign_id`),
Campaign = utm_audience (stored as `adset_id`). The campaign collector writes
at group level for campaigns_daily; adsets collector remaps campaign→adset.

## TikTok

- **Adgroup/ad-grain API error 40002: "dimension campaign_id does not match data_level AUCTION_ADGROUP"** — TikTok API rejects `campaign_id` as a dimension when `data_level=AUCTION_ADGROUP` or `AUCTION_AD`. Fix: remove `campaign_id` from the `dimensions[]` list for adgroup/ad calls and instead look it up via `/adgroup/get/` or `/ad/get/` metadata call. Fixed in `tiktok_bq.py`.
- **30-day query window cap for `stat_time_day`** — TikTok returns `"max time span is 30 days when use stat_time_day"` if `start_date` to `end_date` span >30 days. Fix: wrap `_get_report()` in `_date_chunks(max_days=30)`. Applies at all levels: AUCTION_CAMPAIGN, AUCTION_ADGROUP, AUCTION_AD.
- **`qoyod_source` is stored as `'Tiktok Ads'`** (lowercase 'i' — not
  `'TikTok'` and not `'TikTok Ads'`). `v_channel_key_map` in `collectors/views.py`
  must use `WHEN 'tiktok' THEN 'Tiktok Ads'` or the BQ join in
  `channel_roas_daily` will silently produce 0 TikTok rows.
- **Deep Funnel Optimization in UI:** Instant Form → scroll down → toggle
  "Deep Funnel Optimization" → select CRM pixel → choose "Initiate Checkout"
  as the further optimization event. API equivalent: `optimization_goal="CONVERT"`,
  `pixel_id=TIKTOK_CRM_PIXEL`, `conversion_event="INITIATE_CHECKOUT"`.
- **TikTok access token** expires in 24 hours; refresh token in 365 days.
  Run `python scripts/tiktok_oauth.py --refresh` daily (or via Railway cron).

## BigQuery — campaigns_daily schema

- **`campaign_group_name` does NOT exist in `campaigns_daily`.**  Use
  `campaign_name` for all channels including LinkedIn. The BQ table only has:
  `channel`, `campaign_id`, `campaign_name`, `date`, `spend`, `impressions`,
  `clicks`, `leads`, and channel-specific columns. Any JOIN or GROUP BY on
  `campaign_group_name` will fail silently (column not found).

- **Spend is USD, not SAR.** `campaigns_daily.spend` is always stored in USD regardless of channel. Never label spend figures as SAR in Slack messages, dashboards, or reports. Google Ads cost_micros and Snap spend are divided by 1,000,000 to get USD before BQ write.

- **Never remove a keyword with any spend history.** Only delete keywords with all-time spend = $0. Low QS or poor performance = fix (ad copy / LP) or pause, never remove. Negatives can always be added freely.

- **QS < 5 converting-keyword exception:** Do NOT pause a low-QS + high-lost-IS keyword if conv > 4 AND $10 ≤ CPA ≤ $70. Keyword is delivering real leads despite poor quality score. Guard enforced in `scan_active_keywords()` before flagging. Pause only if conv ≤ 4 OR CPA outside that range.
- **Zero-active-keyword guard:** Never pause the last enabled keyword in an ad group — campaign goes dark silently. `scan_active_keywords()` counts enabled keywords per ad group before flagging and skips sole keywords with a console warning.
- **Ad pause thresholds:** spend > $70 / 7 days / 0 conv → pause. 60%+ disqualified leads (10+ days) → pause. CPL > $50 (10+ days) → pause. Never remove ads, only pause.

## HubSpot deals collector — dual-pass architecture (2026-05-10)

- **2-day incremental window missed long-cycle deals.** A deal created Jan 15 and won Apr 20 would never
  be reprocessed by a 2-day createdate window — BQ showed 721 won deals for Sales Pipeline while HubSpot
  showed 789. Fix: extended to 30-day createdate lookback + a separate closedate pass that covers all won
  deals regardless of when they were created.
- **Closedate pass must run in ALL modes, not just incremental.** Backfills with `--start-date` also need
  the closedate pass; deals closed in the window but created before it are otherwise missed.
- **Do NOT infer `qoyod_source` from UTMs.** Calling `resolve_channel()` on utm fields would inflate counts
  by ~15–20% vs HubSpot's explicit `deal_qoyod_source` filter. Use explicit source only:
  `explicit_src = p.get("deal_qoyod_source") or ""; src_label = explicit_src if (explicit_src and explicit_src != "Other") else "Other"`.
- **Stale rows survive when upsert key changes.** If inference is turned off, old rows with `qoyod_source='Google Ads'`
  (inferred) survive alongside new rows with `qoyod_source='Other'` because the upsert key changed. Fix:
  DELETE the affected pipelines explicitly (`DELETE WHERE pipeline IN (...)`) before re-running backfill.
  SDR Offline Sales and Partnerships Revenue were affected (847 rows deleted 2026-05-10).
- **`seen_ids` deduplication is mandatory.** Deals found in both createdate pass (because they were recently
  created AND won) and closedate pass must be deduplicated with a `seen_ids: set[str]`. Without it, double
  rows inflate counts further.

## Leads gap — Eid Al-Fitr seasonality (2026-05-10)

- **Mid-March 2026 lead dip is NOT a data collection gap.** Week of Mar-16 and Mar-23 show ~950–1,000
  leads vs ~2,000 either side. This is Eid Al-Fitr 2026 (holiday falls Mar 20–22 with extended business
  closure). All sources dropped together — Google went from ~110/day to ~8–22/day, Snapchat from ~50 to
  ~8–22/day. Date coverage is complete (no missing dates in BQ). When reviewing 90-day trends, annotate
  this dip as Eid rather than a reporting issue.

## HubSpot collector

- **Incremental lookback must be 30 days, not 2.** A lead created Apr 22 but qualified May 4 is never
  reprocessed with a 2-day window → BQ stays at 0 qualified while HubSpot UI shows Qualified.
  Fix: `INCREMENTAL_LOOKBACK_DAYS = 30` (still filters by `hs_createdate`, not `hs_lastmodifieddate`).
- **`hubspot_lists.py` must never be deleted.** It creates `LIST_won_deals_lookalike_seed` and
  `LIST_existing_customers_exclude` — used for Meta Custom Audiences and LinkedIn Matched Audiences.
  Was deleted in a dead-code audit; user demanded restore. It is not dead code.

## BQ views — join traps

- **`paid_channel_campaign_daily` join must use `LOWER()` on both sides.** Case-sensitive `=` between
  `campaign_name` (platform, mixed-case) and HubSpot `lead_utm_campaign` (often lower-case) silently
  produces 0 leads in every dashboard cell. Root cause of "correct in direct query, wrong in Slack."
  Always use `LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)`.
- **Snapchat `qoyod_source` is `'Snapchat Ads'` — NOT `'Snapchat'`.** `v_channel_key_map` must use
  `WHEN 'snapchat' THEN 'Snapchat Ads'` or all Snapchat leads are silently dropped in HubSpot joins.
  Confirmed 2026-05-09: BQ had 168 Snapchat leads stored as `'Snapchat Ads'`; the old `'Snapchat'`
  mapping caused Hex to show 795 leads instead of 963 for the 7-day window — all Snapchat leads invisible.
  Fixed in `collectors/views.py` line 27. Previous pitfall entry had this backwards — disregard any note saying `'Snapchat'` is correct.

## Railway deployment (extended)

- **Duplicate Railway project across personal + team workspace = double deployments.**
  Both `rana96-run's Projects` (trial, ID `1b3ee05a`) and `Marketing Workspace` (pro, ID `57f124d0`)
  had `nexa-performance-agent` connected to the same GitHub repo. Every git push triggered two
  Railway deployments, causing double cron runs, doubled API calls (Meta/Snap/TikTok/HubSpot),
  and Snapchat 429 storms. Fix (2026-05-13): deleted the service and project from the trial
  personal workspace via Railway dashboard. The canonical project is `57f124d0` in Marketing Workspace.
  Local `railway` CLI must always link to Marketing Workspace: `railway project link -p "nexa-performance-agent" -w "Marketing Workspace"`.

- **`/tmp` is wiped on every redeploy.** `pending_approvals.json` (and any ephemeral state written to
  `/tmp`) is lost on each deploy. If the team pushes code between the 03:00 nightly approval post and
  morning reaction, the approval metadata is gone. Always write persistent state to BQ or the repo
  volume — never `/tmp`.
- **Teardown must be ON.** With Teardown OFF, old and new deployments overlap during transitions →
  two instances of the scheduler run simultaneously → double Slack posts + double Asana tasks.
  Set `teardown = true` in `railway.toml` AND enable Teardown in the Railway UI deploy tab.
- **gunicorn `--workers 1` is mandatory.** Multiple workers each spawn their own `operational_scheduler`
  thread → N duplicate nightly runs. Always: `gunicorn app_server:app --workers 1 --threads 4`.
- **Activity log CSV is ephemeral.** `logs/activity_log.csv` was wiped on every redeploy. All activity
  logging writes directly to BQ `agent_activity_log` via `log_activity_async()`. No CSV intermediary.
- **Canonical domain is `nexa-web-production-6a6b.up.railway.app`.** Confirmed 2026-05-15 via
  `railway variables` — the `ACTIVITY_DASHBOARD_URL` env var inside the service itself points to
  this domain. `nexa-performance-agent.up.railway.app` is NOT provisioned (returns Railway 404).
  `nexa-web-production-c859.up.railway.app` is the deleted personal-project domain. Use `6a6b`.

## Slack

- **Slack event body must be read ONCE before signature check.** `request.get_data()` called after
  `request.get_json()` returns an empty body — HMAC computed on empty bytes → always 403. Fix: call
  `raw = request.get_data()` first, parse JSON from those bytes, pass same `raw` to HMAC check.
  Also: handle `url_verification` challenge BEFORE signature check (Slack sends it unconfigured).
- **Slack MCP returns `invalid_auth` from scheduled/unattended tasks.** The MCP uses an OAuth session
  that doesn't exist in headless contexts. Fall back to direct Slack API with `SLACK_BOT_TOKEN`
  (`xoxb-` prefix) for all automated/Railway calls.

## Asana task format

- **Always write explicit date ranges in task titles and bodies.** Write `YYYY-MM-DD to YYYY-MM-DD`
  (never "last 14 days"). This lets the team open HubSpot and filter the exact same window to verify
  numbers. `date_from`/`date_to` must always be present in every finding dict.

## Adspirer MCP

- **Adspirer does not support Snapchat or Microsoft Ads.** Standard plan: 1 account per platform.
  Snap and MS must use direct API executors (`executors/snapchat.py`, `executors/microsoft_ads.py`).
  Adspirer is for interactive on-demand execution in Claude Code sessions — the Railway agent cannot
  use it (no browser OAuth).

## Hex API

- **Cannot use `updatePublishedResults: true` AND `inputParams` together.** Hex API v1 returns
  `"Cannot update app results if specifying custom input parameters"` (400) if both are set.
  You must choose one: update published results (with notebook's saved defaults) OR run with
  custom params (results not published). Workaround: set the date input's **default value** to a
  relative "Today" in the Hex UI — then API triggers with `updatePublishedResults: true` will
  always publish today's data without needing inputParams.
- **Date input default must be relative ("Today"), not absolute ("2026-05-02").** If a date
  parameter's default is an absolute date, every API-triggered run publishes that frozen date
  forever. Fix: open the notebook, click the date input cell, change its default from a specific
  date to the relative "Today" option. Then republish. This is a one-time UI fix — cannot be
  done via API.

## Looker Studio

- **No public API — all report building is manual.** BQ views can be created via code, but the
  Looker Studio layer above them (charts, data sources, filters, scorecards) requires manual UI work
  at lookerstudio.google.com. Hex is the canonical automated dashboard.

## TikTok lead attribution — correct HubSpot property for campaign ID

- **`campaign_id` / `ad_group_id` / `ad_id` on the Lead Module (0-136) are NULL for TikTok.**
  These properties exist but are never populated by HubSpot's native TikTok integration.
- **`lead_campaign_id_sync` IS populated** with the TikTok campaign ID (e.g. `1863074553592178`).
  It matches `campaigns_daily.campaign_id` exactly. This is the correct property for ID-based
  campaign matching (Strategy D in v_adset_performance / v_ad_performance).
- **No adset-ID or ad-ID equivalent exists** for TikTok on the Lead Module. `lead_campaign_id_sync`
  is campaign-grain only. If multiple adsets belong to the same campaign, the ID fallback spreads
  campaign-level leads to all adsets (graceful degradation — better than 0).
- **Meta native `campaign_id` etc. are also NULL** in practice as of 2026-05-13. Kept in the
  collector for future use if Meta's integration starts populating them.
- Established 2026-05-13 via `scripts/_check_tiktok_lead.py` deep-probe of HubSpot API.

## BQ views silently become TABLE after materialisation

- **`CREATE OR REPLACE VIEW` fails with "is currently a TABLE"** when a BQ view has previously
  been materialised (e.g. by an ETL process, or `bq_writer.py bootstrap`). The fix is to DELETE
  the table first, then run `CREATE OR REPLACE VIEW`. `create_views()` in `bq_writer.py` now
  auto-detects `table_type == "TABLE"` and drops before recreating.
- Views affected: `utm_paid_attribution_daily`, `v_adset_performance`, `v_ad_performance`
  were found as TABLE in production. Now recreated as VIEWs (2026-05-13).
- To fix manually: `python -m scripts._fix_views` or re-run the `create_views()` function.

## Freshness checks

- **Don't trust `updated_at` for freshness.** A collector that runs successfully but fetches
  zero rows still updates table metadata. Use `MAX(date)` per channel against
  `CURRENT_DATE('Asia/Riyadh')` instead. Helper: `scripts/check_freshness.py`.
- **Microsoft Ads (and LinkedIn) "Success + null ReportDownloadUrl" = no activity, NOT a bug.**
  When a Bing Ads account has zero spend/clicks/impressions in the queried window, the API
  returns `ReportRequestStatus.Status='Success'` with `ReportDownloadUrl=null`. The collector
  reads this as "no rows to write" and exits silently. This causes `MAX(date)` to lag, which
  looks like a stale collector — but the underlying integration is healthy. Verified
  2026-05-09: Microsoft Ads stopped on 2026-04-24 after campaigns were paused.
  Always sanity-check against the platform UI before declaring a collector broken.
  The MS collector now logs this case explicitly.
- **LinkedIn data stopped Feb 2026 due to missing `fields=` param, NOT zero activity.**
  The `adAnalytics` call omitted `fields`, so `costInLocalCurrency` was silently missing.
  All rows were written with spend=$0, causing the upsert to look unchanged and BQ freshness
  to lag. Real spend ($2,769 YTD) was recovered by adding the `fields` param. Fixed
  2026-05-10. See LinkedIn section above for the correct `fields` value.

## campaign_health.py — two lead fan-out bugs (found 2026-05-18)

**Bug 1 — campaigns_daily duplicate rows multiply HubSpot leads.**
Channels affected: Snapchat (2 rows/date), Microsoft Ads (up to 2 rows/date).
Symptom: `hs_leads` in audit tasks 2× what HubSpot shows.
Fix: `campaign_health.py` now pre-aggregates `campaigns_daily` in a `cd` CTE
(`GROUP BY date, channel, campaign_name`) before joining to HS. Applied 2026-05-18
in commit fb4f274.

**Bug 2 — shared campaign names across channels blend leads from the wrong channel.**
Affected: Bing campaigns named identically to Google ones (e.g. `Search_AR_Brand_v2`
exists in both `google_ads` and `microsoft_ads` in campaigns_daily). Filtering
campaigns_daily by channel is correct, but HS leads were not filtered by channel →
Bing CPQL used Google-sourced leads → fake CPQL of $23 when truth was $145+.
Fix: `hs` CTE now includes `qoyod_source` mapped to channel slug. JOIN condition
adds `hs.hs_channel = c.channel`. Orphan Bing campaigns now correctly show 0 leads.
Two wrong PENDING APPROVAL scale tasks flagged [DO NOT APPROVE] in Asana 2026-05-18.

**Prevention:** Any SQL JOINing `campaigns_daily c` to `hubspot_leads_module_daily h`
must:
1. Pre-agg cd: `SELECT date, channel, campaign_name, SUM(spend) … GROUP BY date, channel, campaign_name`
2. Pre-agg hs: include `qoyod_source`, map to channel, join on channel too.
Neither side alone is enough — both must be 1:1 and channel-aligned.

## NEVER use `campaigns_daily.leads` as a leads metric (recurring violation)

- **Symptom:** Channel reports inflated lead counts — e.g., Bing's
  `WebsiteTraffic_Search_AR_Generic` showed 1,157 "leads" for $1,711 spend
  ($1.48 "CPL") in the channel's own reporting. Reality on HubSpot side:
  31 leads and 9 SQLs → real CPQL was $190 (4× the $45 pause threshold).
- **Root cause:** `campaigns_daily.leads` is **channel-reported conversions
  ingested verbatim**. For WebsiteTraffic-objective campaigns specifically,
  the channel counts page views or visits as "conversions" — not real form
  submissions. For most other objectives it's pixel-based and noisy too.
- **Rule (non-negotiable, restated):** Leads and SQLs come from HubSpot
  Lead Module ONLY (`hubspot_leads_module_daily`). Use the pre-aggregate-
  then-join pattern (see CLAUDE.md "KPI measurement rules"). Spend stays
  on the channel side; leads/SQLs cross over from HubSpot.
- **Why it keeps happening (and how to prevent):**
  - The `campaigns_daily.leads` column is RIGHT THERE in the schema and
    tempting for quick queries.
  - QA gate doesn't currently block ad-hoc analysis scripts from using it.
  - Fix: any new analysis script that touches MS/Bing/Generic-channel
    campaigns MUST join to `hubspot_leads_module_daily` for the leads
    metric. NEVER report `cd.leads` as a lead count — only as a debug-
    only "channel-reported conversions" field if at all.
- Caught and re-documented 2026-05-19 (Rana flagged: "you still override the
  qa gate layer and take the conversions from the channels while these are
  page views not leads — we said 100 times leads come only from hubspot").


## Databox — schema type inference always gives STRING/COUNT

- **Symptom:** Numeric fields (spend, cpl, cpql) show "COUNT" as the only aggregation
  option in Databox widget builder even when you push JSON numbers.
- **Root cause:** Databox infers STRING for ALL fields regardless of JSON value type.
  There is no schema-update endpoint (PUT/PATCH both return 405).
- **Fix:** Include a `schema` array in `POST /v1/datasets` at CREATION TIME:
  ```json
  {"name": "...", "dataSourceId": 4983171, "schema": [
    {"name": "spend", "type": "NUMBER"},
    {"name": "cpl",   "type": "NUMBER"}, ...
  ]}
  ```
  Use `dataSourceId: 4983171` (PAK-linked source) for creation — NOT the `dataSourceId`
  returned by GET on an existing dataset (that value is `4983278` and returns 400).
  After creation the stored `dataSourceId` becomes `4983278` — that's read-only metadata.
- **Dataset IDs (history):**
  - v1 `739cde4e` → deleted (wrong field names + all-string)
  - v2 `9ec1816a` → deleted (correct names + all-string)
  - v3 `eff4621e` → ACTIVE (correct names + NUMBER schema)

## Databox — BQ CTE alias scope in `_medium_cte()`

- **Symptom:** `Unrecognized name: hs at [30:42]` — BQ BadRequest during medium CTE build.
- **Root cause:** `hs` alias defined in `medium_raw` CTE was referenced in the PARTITION BY
  clause of `medium_cte` CTE where it's out of scope.
- **Fix:** Split `group_cols` (with `hs.` prefix, used in medium_raw SELECT) from
  `partition_cols` (bare column names, used in PARTITION BY):
  ```python
  group_cols     = ", ".join(f"hs.{c}" for c in hs_cols)   # for medium_raw SELECT
  partition_cols = ", ".join(hs_cols)                        # for PARTITION BY
  ```

## Databox — Custom Metric builder incompatible with Ingestion API datasets (2026-06-08)

- **Symptom:** "Create a custom metric → From a data source or dataset" shows blank
  formula builder for "Qoyod Spend - All Grains". Error in network:
  `GET /d/customqueries/null/builder/4983284 → 422 "Request to datasets-engine failed.
  Unprocessable Entity"`.
- **Root cause:** Databox's analytics-backend `datasets-engine` has `datasetsMetadata: null`
  for the Ingestion API data source (`4983284`). The Custom Metric builder only works for
  native integrations (HubSpot, Google Ads, etc.) — NOT for Ingestion API datasets.
  `POST /analytics-backend-api.databox.com/datasets` → 404 (no registration endpoint).
- **Fix:** Use the Databox **Push API** (`push.databox.com`) instead, BUT it requires a
  **push connector token** — NOT the PAK (`DATABOX_TOKEN`). The PAK returns 401 "Invalid token"
  on `push.databox.com`. The push connector token is a 32-char hex string obtained by:
  1. app.databox.com → Connect Data → Custom → Push Custom Data → create connector
  2. Copy the connector token, store it in Railway as `DATABOX_PUSH_TOKEN`
  Then run: `railway run python scripts/run_databox_push.py 90`
  `push_custom_metrics()` in `collectors/databox_pusher.py` pushes `$spend`, `$leads`,
  `$sqls`, `$cpl`, `$cpql`, `$spend_<channel>` per day. Reads env var `DATABOX_PUSH_TOKEN`.
- **Two separate Databox tokens** (easy to confuse):
  - `DATABOX_TOKEN` = PAK (`pak_617cd2b7…`) — used for Ingestion/Dataset API (`api.databox.com`)
  - `DATABOX_PUSH_TOKEN` = push connector token (hex) — used for Push API (`push.databox.com`)
- **The Ingestion API dataset (`eff4621e`) is write-only** — data cannot be read back
  via the REST API, so you can't use it as an intermediate BQ substitute.
- **Data source IDs**: parent `4983171` = "Qoyod BQ" PAK connection; child `4983284` =
  "Qoyod Spend - All Grains" dataset. The analytics-backend uses the child ID (4983284).

## 2026-06-08 — Agent-system rebuild (critical gates)

- **The team is 9 agents (org chart), NOT the 13 `agent_activity_log` roles.** The
  log table is a *logging* taxonomy (infra: health_monitor/bq_refresh/collector/
  ops_scheduler; human: user; function buckets). Build/verify the roster from
  `docs/_shared/org-chart.md`, never the log table. Cost a full wrong rebuild first.
- **`runtime_personas/` is LIVE runtime — never move/delete the 6 files** `claude/roles.py`
  loads (qoyod-manager-os, qoyod-brand-identity, qoyod-paid-media-agent,
  qoyod-analyst-agent, nexa-strategist, qoyod-daily-report). Moving them breaks Railway.
  **UPDATED 2026-06-17: `runtime_personas/` and `claude/roles.py` were deleted on 2026-06-16. Railway is deprecated. This trap is historical only — the files no longer exist.**
- **`agent_handoff_log` does NOT exist** (no BQ table, no code). The
  growth-marketing-dept / project-coordinator-dept / agent-handoff skills assuming it are
  aspirational specs — don't treat their payloads as live.
- **Don't blind-repoint `claude/roles.py` at the dev playbooks.** Runtime personas
  are rich (~23KB); dev playbooks are tight. Repointing shrinks prompts and degrades
  production. Unify by cross-reference, or grow-then-repoint. (Deferred, by design.)
- **New `.claude/agents/*.md` aren't dispatchable by name until `/agents` reload**
  (or restart) — Claude Code discovers agents at session start.
- **`secrets/` and `node_modules/` were unignored** (nothing committed). Now in
  `.gitignore`. Always confirm `git ls-files secrets/` is empty before committing.
- **Concurrent sessions edit this repo.** Commit with explicit pathspecs
  (`git commit -- <path>`) so you don't sweep another session's staged files.

## Connector Police (connector_tracker.py) — 3 false-positive bugs (fixed 2026-06-08)

The "Connector Police" flagged 4 connectors BROKEN that were all healthy. Root
cause was the tracker itself, not the connectors. If it cries wolf again, check:
- **Channel labels:** it queries `campaigns_daily.channel` — must use `google_ads`/
  `microsoft_ads`, NOT display names `google`/`bing`. Map via `_BQ_CHANNEL`.
- **Channel-less tables:** `hubspot_leads_module_daily` / `hubspot_deals_daily` /
  `gclid_attribution` have **no `channel` column** — freshness/row checks must gate
  the `WHERE channel=` filter on `table == "campaigns_daily"`, else `400 Unrecognized name: channel`.
- **Freshness threshold:** `_STALE_HOURS` must be ≥72h (3d). 1-day-old data is
  ~28–48h old and normal (collector lags up to 2d pre-08:00) → tighter = daily false WARNING.
- **Idle ≠ broken:** a channel with no active campaigns / no spend (or `known_paused`)
  is HEALTHY-IDLE, not stale/BROKEN (LinkedIn). Suppressed in `run_connector_check`.
- **A "corrupt" deal amount was actually a PHONE NUMBER typed into the Amount field
  (human error, not data corruption).** Deal 505631711439 had `amount` = 966504406958 SAR
  — i.e. `+966 50 440 6958` (966 = KSA country code). Owner entered the contact's phone
  into Amount. `check_amount_sanity` (deals): daily `amount_total` > 50× 90d median → BROKEN,
  AND `_looks_like_phone(native_SAR)` recognises the signature (starts 966 + 12 digits, or
  05XXXXXXXX, or 5XXXXXXXX) → diagnoses "phone number in Amount field" explicitly. Test the
  **native (SAR)** value, not USD — the USD conversion (÷3.75) destroys the 966 prefix.
  Source-deal fix is HUMAN-gated (HubSpot read-only). The police watches deal amounts now.

### check_freshness — BQ query error wrongly raised false BROKEN (fixed 2026-06-09)

- **Symptom:** intermittent `hours_old=9999` / BROKEN for `google_ads` and `microsoft_ads`
  (bing) on #nexa-health, even when `campaigns_daily` had fresh rows for those channels.
- **Root cause:** the `except Exception` path in `check_freshness` returned
  `{"status": "BROKEN", "hours_old": None}`. A **BQ query error** (transient rate limit /
  timeout / internal error — the check failed to RUN) was indistinguishable from a genuine
  data outage, so a flaky query produced a hard RED alert for a connector with healthy data.
  The old `int(rows[0].hours_old or 9999)` also masked the empty case behind the `9999`
  sentinel, conflating "no rows" with "query failed".
- **Fix:** split the two failure modes in `check_freshness`:
  - **(a) exception → WARNING** with `error="freshness check failed to run: {e}"` (the check
    couldn't execute; not a connector fault → no false RED).
  - **(b) `MAX(date)` is NULL (zero rows for the channel) → real BROKEN** with
    `reason="no rows in BQ for this channel/table"` — handled explicitly, no `9999` magic.
  - Fresh data still flows through the `_BROKEN_HOURS`/`_STALE_HOURS` ladder unchanged.
- **`_BQ_CHANNEL` confirmed correct:** `campaigns_daily.channel` distinct values are
  `google_ads`/`microsoft_ads` (verified live), and `_BQ_CHANNEL = {"google":"google_ads",
  "bing":"microsoft_ads"}` is applied consistently in both `check_freshness` and
  `check_row_integrity`. The slug map was never the bug — the exception path was.
- **Confirmation run (`run_connector_check` per channel):** google → freshness HEALTHY
  hours_old=32; bing → freshness HEALTHY hours_old=32. No false BROKEN on either.

## Claude Code subagents — invalid YAML frontmatter silently drops the agent (2026-06-09)

- **Symptom:** `Agent type 'growth-analyst' not found` mid-session, though the file looked
  fine and it had dispatched earlier. 3 of 9 agents affected (growth-analyst, developer,
  ui-ux-designer); the other 6 loaded.
- **Root cause:** their `description:` had an **unquoted `: ` (colon-space)** —
  growth-analyst's "everything: the 8-step loop", developer's "Last link: receives". YAML
  reads the embedded colon as a new mapping key → `ScannerError: mapping values are not
  allowed here` → Claude Code drops the agent from the dispatch registry.
- **Fix:** remove the embedded `: ` (use `—`) or double-quote the description. Validate
  with `yaml.safe_load` on the frontmatter (one-liner in `.claude/agents/README.md`);
  then run `/agents` (or restart). **Rule:** agent `description` must be valid YAML — never
  an unquoted colon-space. A subagent that can't load on its own = a frontmatter bug.

## Non-paid-source leak audit across all HubSpot-joined surfaces (2026-06-09)

After the `utm_paid_attribution_daily` fix (commit 9c758c7) dropped 38 NULL-channel orphan
rows, audited every other surface for the same leak (non-paid `qoyod_source` carrying a
stale paid UTM → NULL/mis-attributed channel). Live BQ, last-7d, per surface:
NULL-channel-with-leads count + distinct channel values present.

- **paid_channel_campaign_daily — CLEAN.** Resolves channel via INNER JOIN on inline
  paid-only `channel_map` keyed on `qoyod_source`; non-paid sources (Direct Traffic /
  Offline / Organic Social / etc.) have no map row and are dropped. 0 NULL-channel rows,
  only paid channels present. No fix.
- **paid_channel_daily — CLEAN.** Same INNER-join-on-`channel_map` structure. 0 NULL-channel
  rows, only paid channels. No fix.
- **channel_roas_daily — CLEAN.** INNER JOIN on `v_channel_key_map` (includes
  `organic_search` by design). 0 NULL-channel rows; only paid + `organic_search` present —
  the latter is intentional, not a leak. No fix.
- **utm_paid_attribution_daily — CLEAN (confirm).** 0 NULL-channel rows post-fix; channels =
  paid + `organic_search` (in the fix allow-list). Fix verified holding.
- **v_adset_performance — CLEAN (confirm).** Leads sourced only from
  `utm_paid_attribution_daily` (no direct `hubspot_leads_module_daily` join since 2026-06-09);
  inherits the fix. 0 NULL-channel rows.
- **v_ad_performance — CLEAN (confirm).** Same — leads only from `utm_paid_attribution_daily`.
  0 NULL-channel rows (2 organic_search leads, intentional).
- **Why the qoyod_source surfaces are structurally immune:** they map channel via an INNER
  JOIN on `qoyod_source` against a paid-only (or paid+organic) map, so a non-paid source is
  dropped at the join — it can never become NULL or a non-paid label. Different mechanism
  from `utm_paid_attribution_daily`, which matched on UTM and COALESCE-resolved channel
  (allowed NULLs). **The 9c758c7 source-filter pattern only needs to live in the one UTM-grain
  view; the channel-grain views already filter implicitly via the INNER join.** No fixes
  applied, no materialize needed.

## n8n API PUT requires UTF-8 without BOM (2026-06-17)

**Symptom:** PUT to `https://qoyod.app.n8n.cloud/api/v1/workflows/{id}` silently fails or returns HTTP 500 even with valid JSON payload.

**Root cause:** PowerShell's `Set-Content` and `ConvertTo-Json | Out-File` write UTF-8 with BOM (bytes EF-BB-BF at start). The n8n Cloud API rejects BOM-prefixed payloads.

**Fix:** Strip the BOM before sending:
```powershell
$json = $wf | ConvertTo-Json -Depth 20 -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
Invoke-RestMethod -Uri "..." -Headers $headers -Method PUT -Body $bytes -ContentType "application/json"
```
Or use `[System.Text.UTF8Encoding]::new($false).GetString(...)` to read back without BOM.

**Risk:** An accidental PUT with a small/empty payload can wipe a workflow. Always save a backup JSON before any PUT.

## 2026-06-19 — Full system audit findings

### Collector: duplicate "status" key in row dict (meta_bq.py, snap_bq.py)
When a BQ row dict has two entries with the same key, Python silently keeps only the last value.
Found in meta_bq.py and snap_bq.py — a `"status": None` placeholder plus the real assignment.
Fix: remove the None placeholder. Always check for duplicate keys before committing new collector row dicts.

### Collector: PMax spend not converted to USD (google_ads_bq.py)
`collect_pmax_asset_groups_and_write()` computed spend from `cost_micros / 1_000_000` but never applied `to_usd()`. Currency code was fetched but unused. Native SAR amounts were labeled as USD in BQ.
Fix: always pipe `cost_micros / 1_000_000 → normalize_currency() → to_usd()` before writing any spend field.

### Collector: naive datetime for API window boundaries (hubspot_leads_bq.py)
`datetime(year, month, day)` without `tzinfo=timezone.utc` is system-TZ-dependent. On Railway (UTC) it was fine; locally or if TZ changes, the HubSpot fetch window drifts and leads near midnight are missed or duplicated.
Fix: always use `datetime(..., tzinfo=timezone.utc)` for timestamp boundaries sent to any API.

### Collector: property in row dict but not in PROPERTIES fetch list (hubspot_leads_bq.py)
`leads_disqualification_reason__sub_reasons_qflavour` was mapped in the row dict but missing from the `PROPERTIES` list. HubSpot returns None for unrequested properties — Qflavour sub-reasons were always NULL in BQ.
Fix: whenever adding a field to the row dict, immediately add its property name to the PROPERTIES/fields fetch list.

### QA gate: HubSpot paging cursor `after = 0` breaks pagination
HubSpot Search API rejects `"after": 0` in some versions, silently returning only page 1.
Fix: use `after = None` as initial cursor; omit the key from the request body when falsy.

### QA gate: check_pause_precedence silently passed because analysers/ was deleted
`check_pause_precedence()` lazy-imports `from analysers.campaign_health import ...` inside a try/except. When the `analysers/` package was deleted 2026-06-16, every call raised ImportError, was caught silently, and the check returned `passed=True`. The safety gate was non-functional for weeks with no visible failure.
Fix: restored `analysers/__init__.py` and `analysers/campaign_health.py` stub. Rule: any QA check with a lazy-import MUST log a warning when the import fails, not silently pass.

### n8n: infra_data_collection.json was writing contacts data into hubspot_leads_module_daily
The HubSpot node in the data collection workflow called `/crm/v3/objects/contacts/search` (Contacts API) and merged results into `hubspot_leads_module_daily`. The correct source is the Lead Module API (`/crm/v3/objects/0-136/search`). The Python Railway collector owns that table; the n8n MERGE was incorrect.
Fix: removed the HubSpot MERGE block from n8n entirely. Python collector is the sole writer.

### BQ views: HAVING clause invalid in VIEW definitions
BQ does not allow aggregate functions in HAVING inside a VIEW SQL. `paid_channel_campaign_daily` had `HAVING SUM(spend) > 0` which caused the view to return 404. The filter is redundant anyway since `wide_ads` already filters `WHERE spend > 0`.
Fix: never use HAVING with aggregates in BQ VIEW definitions.

### Ghost BQ objects: memory says "dropped" but never actually deleted from BQ
`platform_campaign_snapshot`, `pmax_asset_groups_daily`, and `v_channel_key_map` were declared dropped in memory/01_architecture.md on 2026-06-16 but were never deleted from BQ. Downstream code could accidentally join them.
Fix: when memory says "dropped", verify the object is actually gone from BQ before closing the task. Use `c.delete_table(..., not_found_ok=True)` explicitly.

### n8n: hardcoded BQ project/dataset in SQL strings (5 workflow files)
Found in kpi_cpl.json, kpi_impression_share.json, kpi_cpql.json, kpi_creative_ctr.json, kpi_qual_ratio.json. SQL strings used backtick-quoted `angular-axle-492812-q4.qoyod_marketing.table` instead of `{{ $vars.BQ_PROJECT }}.{{ $vars.BQ_DATASET }}.table`.
Fix: all replaced. Rule: always use `{{ $vars.BQ_PROJECT }}` and `{{ $vars.BQ_DATASET }}` in all n8n SQL. The projectId field on BQ nodes must be an expression `="{{ $vars.BQ_PROJECT }}"` not a string literal.

### Silent exception swallowing — the root cause of all of the above
The common thread: `except Exception: pass` or `except Exception: return []` with no log.
When a check, import, or query fails silently, the system appears healthy while producing wrong data.
Rule: every except block must either re-raise or log at WARNING level minimum. Never silently return empty/None on a data path.

## HubSpot Lead Module ≠ Contacts (2026-06-20)
We work with the HubSpot Lead Module (object `0-136`), NOT contacts.
- Collector: `collectors/hubspot_leads_bq.py` uses `LEAD_OBJ = "0-136"` and queries `/crm/v3/objects/0-136/search`
- BQ table: `hubspot_leads_individual` stores Lead Module records, keyed by `hs_object_id`
- Any HubSpot API call that needs to count or fetch leads MUST use object `0-136`, not `/contacts/search`
- Contacts and Leads are different HubSpot objects — count comparisons between them are meaningless
- Fix applied in `scripts/reconcile_hubspot_bq.py` commit after 2026-06-20 session: changed endpoint from contacts to 0-136

## gh CLI path and auth (2026-06-20)

- **gh CLI not on default PATH**: Binary lives at `C:\Program Files\GitHub CLI\gh.exe`. System PATH already includes it, but new PowerShell sessions launched from Claude Code tools sometimes don't inherit it. Use full path `& "C:\Program Files\GitHub CLI\gh.exe"` as fallback, or prefix `$env:PATH += ";C:\Program Files\GitHub CLI"`. Authenticated as `Rana96-run`, repo slug `Rana96-run/nexa-performance-agent`. Token scopes: repo + workflow (sufficient for Actions log reads).

## n8n Cloud PUT /api/v1/workflows/{id} — strip extra fields before PUT (2026-06-21)

n8n Cloud PUT /api/v1/workflows/{id} only accepts `{name, nodes, connections, settings}`. Any extra fields (`updatedAt`, `createdAt`, `versionId`, `shared`) cause 400. Strip them before PUT.

**Also**: the `settings` object itself must not contain newer fields like `availableInMCP` or `binaryMode` — these cause `400: request/body/settings must NOT have additional properties`. Safe settings fields: `executionOrder`, `saveManualExecutions`, `callerPolicy`, `errorWorkflow`, `timezone`. Strip everything else.

## n8n Weekly Review IF node crash — BQ returns numeric as string (2026-06-21)

**Symptom:** Weekly Review workflow (`iNSdpXH7Rc9Lb8h8`) fails at node `IF ⚡ Data Fresh?` with `NodeOperationError: Wrong type: '2' is a string but was expecting a number`.

**Root cause:** BQ `googleBigQuery` node returns `DATE_DIFF()` result as a string. The IF node with `typeValidation: "strict"` refuses to compare a string against a number `rightValue`.

**Fix:** Change IF node `parameters.conditions.options.typeValidation` from `"strict"` to `"loose"`. This allows n8n to coerce the string to number automatically. Applied 2026-06-21 via API PUT.

## n8n Approval Listener — wrong Resume URL (2026-06-22)

**Symptom:** Approval Listener workflow (`5Acqsbxsk0XQ5k9e`) errored on every ✅ reaction with: `404 - "The requested webhook POST {messageTs}-approval/resume is not registered."` Error execution ID 67, first occurred 2026-06-18.

**Root cause:** The `Resume Waiting Execution` node constructed a dynamic URL from the Slack `messageTs`:
```
https://qoyod.app.n8n.cloud/webhook/{{ $('Extract Reaction').first().json.messageTs }}-approval/resume
```
This webhook path is never registered. n8n Wait nodes (with `resume: "webhook"`) register a **static** URL at:
```
https://qoyod.app.n8n.cloud/webhook/{webhookId}
```
The `webhookId` comes from the node definition field, not the message timestamp.

**Fix:** Changed URL to the static `webhookId` of the `Wait Campaign Approval` node in `cadence_daily` (`T8icImtZFLYeCa7e`):
```
https://qoyod.app.n8n.cloud/webhook/campaign-approval-webhook-001
```
Also enriched the POST body to include `messageTs` and `channel` for downstream Slack threading. Applied 2026-06-22 via API PUT. Workflow confirmed `active: true`, versionId `26b33ed6`.
