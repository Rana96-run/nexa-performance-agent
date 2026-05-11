# Open Tasks — Prioritized Work Queue

Ordered by dependency + user priority. Check off as done; append new items at
the bottom of the relevant section.

## P0 — Unblocks everything else

- [x] **HubSpot deal SAR/USD investigation — RESOLVED 2026-05-09.** Direct
  HubSpot API verification proved the collector's `to_usd()` IS working
  correctly. BQ `amount_won` is USD; `amount_won_native` is SAR. The earlier
  "divide by 3.75" rule was based on a misread (comparing Hex against Funnel
  which displays SAR). Reverted across all Hex SQL + `analysers/campaign_health.py`
  on 2026-05-09. Locked in `memory/08_pitfalls.md`.



- [ ] **Re-mint LinkedIn tokens** — `LI_ACCESS_TOKEN/ORG_URN/AD_ACCOUNT_URN`
  currently empty. Run `python scripts/linkedin_oauth.py` then `... orgs`,
  paste outputs to `.env`. Follow-ups via `scripts/linkedin_refresh.py`.
- [ ] **Run YouTube OAuth** — `python scripts/youtube_oauth.py`. Writes
  `YT_REFRESH_TOKEN` + `YT_CHANNEL_ID` to `.env` (slots empty today).
- [x] **Microsoft Ads** — UNBLOCKED + FULLY CONNECTED 2026-05-06. Admin granted
  Global Admin → ran `New-MgServicePrincipal -AppId d42ffc93-c136-491d-b4fd-6f18168c68fd`
  → service principal exists in qoyod.com tenant → `/common/` OAuth works with
  `@qoyod.com` work account. YTD coverage Dec 27 → Apr 24 (119 days):
  - campaigns: 534 rows
  - adgroups:  993 rows
  - ads:       1,182 rows (NEW collector function `collect_ads_and_write`)
  - keywords:  7,819 rows
  Collector function added + wired into `reporting_scheduler.py`. REST API
  pitfalls fixed in `microsoft_ads_bq.py`: endpoint URL `/Reporting/v13/GenerateReport/Submit`,
  `Type` discriminator field, column names per-report (CampaignStatus / Status / KeywordStatus / AdStatus),
  `Scope.AccountIds` flat int list. `bq_writer.ADS_DAILY_SCHEMA` updated to
  include `cpl` (was the final blocker). All in `08_pitfalls.md`.
- [ ] **Get Funnel.io read API token** — ask Amar for workspace API token
  + account_id + project_id. Fill `FUNNEL_API_TOKEN/ACCOUNT_ID/PROJECT_ID`.
- [x] **HubSpot leads YTD backfill** — completed 2026-05-04. 24,260 leads → 11,460 rows in `hubspot_leads_module_daily` (2026-01-08 to 2026-05-05). Run with `python -m collectors.hubspot_leads_bq` (module mode).
- [x] **HubSpot deals YTD backfill** — completed 2026-05-04. 31,557 deals → 13,595 rows in `hubspot_deals_daily` (2026-01-08 to 2026-05-05). Run with `python -m collectors.hubspot_deals_bq`.

## P1 — Attribution depth (user explicitly requested)

- [x] **Build `utm_paid_attribution_daily` view** — completed 2026-05-04. View was already in `bq_writer.py`; wired into `refresh_all_views()` in `views.py` with correct dependency order.
- [x] **Adset-grain collector** — already existed: `meta_bq.collect_adsets_and_write`, `google_ads_bq.collect_adgroups_and_write`, `snap_bq.collect_adsets_and_write`, `tiktok_bq.collect_adgroups_and_write`. All wired in `reporting_scheduler.py`.
- [x] **Ad-grain collector** — already existed: `google_ads_bq.collect_ads_and_write`, `meta_bq.collect_ads_and_write`, `tiktok_bq.collect_ads_and_write`. All wired.
- [x] **PMax asset-group collector** — completed 2026-05-04. `collect_pmax_asset_groups_and_write()` added to `collectors/google_ads_bq.py`. Writes to `pmax_asset_groups_daily`. Wired into `reporting_scheduler.py`.
- [ ] **Creative type tagging** — for each ad row, classify as
  `{image, video, carousel, collection, reels, story}`. Requires pulling
  `creative` fields alongside insights.

## P1 — Dashboard expansion (user explicitly requested)

- [x] **Channel Deep Dive (Hex)** — completed 2026-05-04. Section header + SQL 102 (dataframe_20) showing adset × CPL zone (Scale/OK/Watch/Pause) for all channels. Hex published.
- [x] **Leads Funnel (Hex)** — completed 2026-05-04. Text header + SQL 104 (dataframe_21) querying `hubspot_leads_module_daily` for `top_disq_reason` + `top_disq_sub_reason` grouped by disqualified count. Hex published.
- [x] **Insights & Recommendations (Hex)** — completed 2026-05-04. Markdown header + SQL 106 (dataframe_22) querying `v_campaign_leaderboard` with PAUSE/SCALE/OK/WATCH rules (CPQL thresholds $40/$80, min $70 spend). Hex published.
- [x] **Paid Overview (Hex)** — completed 2026-05-05. Markdown header (Markdown 19) + SQL 20 (`dataframe_23`) querying `paid_channel_daily` for channel × spend/leads/sqls/CPL/CPQL/qual_rate_pct/ROAS (30 days). SQL 21 (`dataframe_24`) querying `organic_page_daily` UNION ALL across Meta FB/IG/YouTube/LinkedIn with platform-specific engagement metrics. BQ columns verified before publish. Hex published.
- [x] **"(no UTM — click-ID only)" explicit row** in every campaign table — completed 2026-05-07. All 6 channel campaign SQL cells updated (Google, Snap, TikTok, Meta, Microsoft, LinkedIn). Each now has `lead_utm_campaign != '__none__'` filter in the `hs` CTE + a `no_utm_hs` CTE + UNION ALL row at bottom. Meta uses `lead_utm_content` (ad-level join). Row shows 2410 leads / 904 qualified / 1374 disqualified across all channels. Hex published.

## P2 — Ops hardening

- [x] **LinkedIn token auto-refresh** — completed 2026-05-04. `scripts/linkedin_refresh.py` already existed; wired as step 3f in `operational_scheduler._nightly()`.
- [x] **Slack digest of 6h refresh** — completed 2026-05-04. `_post_refresh_digest()` added to `reporting_scheduler.py` — posts on failures or 06:00 UTC run; non-fatal.
- [x] **Disqualification property probe** — completed 2026-05-04. `scripts/probe_hubspot_props.py` created. Confirmed property names: `leads_disqualification_reason__ops` (main) + `leads_disqualification_reason__sub_reasons` (sub). Both stored in `hubspot_leads_module_daily`.
- [ ] **Deploy dashboard to Replit** — superseded: Hex is canonical dashboard. No Replit deploy needed.

## P1 — Funnel.io learning (dashboard prep)

**Posture: learn-only.** We do not push data to Funnel. Goal: understand
the existing workspace well enough to design Streamlit dashboards that
mirror (and extend) the Looker boards the team already trusts.

- [ ] **Ask Amar the batched questions** in `memory/12_funnel_io.md`
  §"Questions to ask Amar" — read creds, Looker URLs, currency, TZ,
  qualified-lead definition, naming conventions.
- [ ] **UI walkthrough + screenshot** — every Custom Dimension rule and
  every Custom Metric expression. Transcribe under `## Custom Dimensions
  (audited YYYY-MM-DD)` / `## Custom Metrics (audited YYYY-MM-DD)` in
  `memory/12_funnel_io.md`.
- [ ] **Looker board audit** — list every tile, metric it cites, filter
  set. Output becomes the source list for our dashboard spec.
- [ ] **API dim/metric list** (once `FUNNEL_API_TOKEN` lands) — call
  the rows endpoint, dump column names, compare to UI audit.
- [ ] **Baseline snapshot** — 30 days of day × channel × campaign rows
  to `memory/_snapshots/funnel_YYYY-MM-DD.json` as a diff reference.
- [ ] **Reconcile Funnel vs our BQ** — day × channel cost + leads; log
  drift > 5% cases with the root cause.
- [ ] **HubSpot join trace** — walk one SQL contact through Funnel's
  Contact → Association → Deal path; document under
  `## HubSpot join trace (verified YYYY-MM-DD)`.
- [ ] **Create `memory/13_dashboard_spec.md`** — one row per Streamlit
  tile: page, metric name (matching Funnel label), formula, data
  source (Funnel / our BQ / both), tooltip text.
- [ ] **Map Funnel `channel_unified` → our `CHANNEL_MAP`** in
  `collectors/views.py` so labels match across stacks.

## P2 — LinkedIn campaign cloning use case

- [ ] **LinkedIn: clone creatives from closest matching campaign**
  When creating a new LinkedIn campaign via API, find the closest existing campaign
  by keyword/product name match, copy its creative reference URN, and attach it
  to the new ad set automatically. Requires `rw_organization_admin` scope added
  to the LinkedIn app so the token can read `adCreativesV2`.
  Steps:
  1. Add scope in LinkedIn Developer Portal → Products → Marketing Developer Platform
  2. Re-mint token with new scope: `python scripts/linkedin_oauth.py`
  3. Build `executors/linkedin.py::clone_creative(source_campaign_id, target_campaign_id)`
     that reads creative from source and POSTs to `/adCreatives` on target
  4. In `create_campaign()`, add optional `clone_from_campaign_id` param

## P3 — Nice-to-have

- [ ] **Microsoft Ads collector** (env scaffolding now present — unblocked
  once OAuth refresh token is minted)
- [x] **TikTok Ads collector** — connected 2026-05-04. Both accts (Qoyod 2024 + 2025) pulled 56 rows to `campaigns_daily` on first run. Auth URL bug fixed (`business-api.tiktok.com`, not `business.tiktok.com`).
- [x] **TikTok in daily Slack report** — automatic via `paid_channel_daily` view + `v_channel_key_map` (already had `tiktok → TikTok Ads`). $1,313 / 45 leads visible in last 7d.
- [x] **TikTok in agent activities** — already in `main.py::collect_data()` line 128.
- [x] **TikTok executor (post-approval pause)** — wired in `main.py::execute_channel_action()` with campaign/adgroup/ad routing. Default policy for missing-entity left as TODO for explicit decision (see `main.py:670+`).
- [x] **Wire Snapchat + LinkedIn pause routing** — added to `main.py::execute_channel_action()` and `reports/app.py::_execute_approved_action()` (both scale + pause for LinkedIn; Snapchat was already in app.py).
- [x] **Add scale action wiring** — completed 2026-05-04. `execute_channel_action()` in `main.py` now handles `scale`/`adjust`/`increase_budget` → `set_campaign_budget()` per channel, and `enable`/`resume`/`unpause` → channel enable methods. Google Ads campaign-level pause also wired.
- [ ] Snapchat organic (if Snap exposes public page metrics — doubtful)
- [ ] Weekly email digest via existing Gmail SMTP (creds set) of top KPIs
- [ ] A/B test tracker view (campaigns with same utm_audience, different utm_content)
- [ ] SEMrush integration for keyword / competitor view (API key set)

## P2 — Second Microsoft Ads account — DONE 2026-05-10

- [x] **Second MS Ads account wired** — `nexa-qoyod@outlook.com` → customer 254851652
  → account **187231519** (G145REZA, "Automated Cloud Company").
  OAuth via device_code flow (public client — no client_secret on refresh).
  Env vars added: `MS_ACCOUNT_ID_2`, `MS_CUSTOMER_ID_2`, `MS_REFRESH_TOKEN_2` in both
  `.env` and Railway. Collector (`collectors/microsoft_ads_bq.py`) refactored to loop
  over all accounts via `_accounts()` / `_get_access_token_for(public_client=True/False)`.
  Both accounts authenticate. Backfill needed: run collector YTD to populate BQ.

## Done this session (2026-05-11)

- [x] **`rebuild_all` BQ MERGE timeout fix** — batched 658 dates into chunks of 30 per MERGE to avoid the 2400s timeout. 47,019 rows written across 22 batches to `hubspot_leads_module_daily`. Committed `e448918`.
- [x] **Qual/disq rate formula fixed everywhere** — denominator was `leads_total` (included open/pending leads). Corrected to `qualified + disqualified` in all 6 BQ view definitions in `bq_writer.py` (9 instances) and in the Hex "KPI scorecard data" SQL cell. Qual Rate 47.2 + Disq Rate 52.80 = 100.0 ✅. Committed `499b7c6`, Hex published.

## Done this session (2026-05-10)

- [x] **HubSpot deals dual-pass fix** — incremental window extended 2→30 days; closedate pass now runs in ALL modes (not just incremental); explicit `deal_qoyod_source` only (no UTM inference). Eliminated 15–20% count inflation from inference. Fixed undercounting from 721→818 for 90-day Sales Pipeline paid deals (target 789).
- [x] **2025 full backfill** — 110,297 deals → 41,040 rows across 496 partitions. Covers Jan 1 2025 → May 10 2026 via createdate pass + closedate pass. Captures deals created before 2026 but closed in 2026.
- [x] **SDR Offline Sales + Partnerships Revenue stale row fix** — 847 stale inference rows deleted; backfill repopulated both with explicit-source data. SDR: BQ=5, HS=5 (exact). Partnerships: BQ=32, HS=31 (1-deal gap).
- [x] **`hubspot_deals_bq.py` CLI** — added `--start-date YYYY-MM-DD` argparse flag for targeted backfills without modifying script body.
- [x] **Leads gap investigation** — mid-March 2026 dip (weeks of Mar-16/23, ~950 leads vs ~2,000) confirmed as Eid Al-Fitr 2026 seasonality. No collection gap; all dates present in BQ. Documented in `memory/08_pitfalls.md`.
- [x] **Pitfalls documented** — dual-pass architecture, explicit-source-only rule, stale row upsert-key problem, `seen_ids` deduplication requirement, Eid seasonality annotation.

## Done this session (2026-05-06 continued)

- [x] **Full YTD sub-level backfills** — all grains filled to Jan 1, 2026:
  - TikTok adgroups: 1,565 rows (125 days, Jan 1 → May 5)
  - TikTok ads: 10,438 rows (125 days, Jan 1 → May 5)
  - Meta adsets: 2,142 rows (125 days, Jan 1 → May 5)
  - Meta ads: 8,599 rows (125 days, Mar 16 → May 5 — actual data boundary)
  - Google adgroups: 2,313 rows (125 days, Jan 1 → May 5)
  - Google ads: 2,935 rows (125 days, Jan 1 → May 5)
  - Google keywords: 9,747 rows (125 days, Feb 8 → May 5 — keyword setup date)
  - Snap adsets: completed (separate session — full YTD coverage)
  - Snap ads: **completed 2026-05-07** — 142,000 rows (125 days, Jan 1 → May 5). Both accounts: 1,000 + 136 ads. Exact per-ad spend from `/ads/{id}/stats` API. Token auto-refreshed 4× during account 1's 100-min loop. Total $71,770.39 Snapchat ad spend now in `ads_daily` with exact figures (not proportional allocation).
- [x] **Keyword policy extended** — COMPETITOR_PATTERNS list, competitor campaign rules,
  language mismatch detection (AR in EN campaign and vice versa). NEVER_NEGATIVE_PATTERNS
  kept as backwards-compat shim. Committed 2f38a72, pushed to Railway.
- [x] **BQ views refreshed + Hex triggered** — all 13 views refreshed; both Hex notebooks
  (performance + activity) re-triggered after backfills confirmed complete.

## Done this session (2026-05-06)

- [x] **ROAS close-date fix** — `hubspot_deals_bq.py` now uses `closedate` as the partition date for won deals (not `createdate`). SQL `WHERE stage_status='won' AND date BETWEEN x AND y` natively filters by when deals closed. 365-day backfill re-run: 88,034 deals → 35,015 rows.
- [x] **Hex auto-refresh** — `collectors/hex_refresh.py` created. After every BQ refresh pass, the scheduler POSTs to Hex API to re-run both notebooks (performance + activity). Stale dashboard issue eliminated.
- [x] **Snap timezone crash fixed** — `ZoneInfo("UTC")` crashes on Windows (no tzdata). Fixed with `timezone.utc` fallback in `snap_bq.py`.
- [x] **Snap future-date fix** — DAY granularity rejects `end_time` in the future. Capped `end = date.today() - timedelta(days=1)` in both `collect_and_write` and `collect_adsets_and_write`.
- [x] **Zero-row + BQ staleness guards** — `reporting_scheduler.py` now alerts Slack immediately (any time of day) when a paid channel (google_ads, meta, snapchat, tiktok) writes 0 rows, or when `MAX(date)` per paid channel in BQ is >3 days old. Silent failures can never go unnoticed again.
- [x] **Dead code: `collectors/drive_writer.py` deleted** — 0 importers, 212 lines removed.
- [x] **Activity dashboard design spec** — saved to `memory/14_activity_dashboard.md`.
- [x] **Full incremental data pull** — 2,994 rows across 24 collectors. All Hex notebooks triggered. All git changes pushed to Railway.

## Done this session (2026-05-04) — continuation

- [x] **LP Hex cell published** — "LP Performance — Weekly (Test from 2026-05-04)" cell added to Hex notebook, queries `v_lp_weekly_summary WHERE week_start >= '2026-05-04'`. Shows 0 rows on day 1 (expected). Hex published.
- [x] **Silent nightly audit + weekly Slack summary** — nightly audit no longer posts to Slack daily; `_log_nightly_audit_to_bq()` writes counts silently; `_post_weekly_summary()` fires every Monday posting to #notify with weekly totals + recommendations.
- [x] **Scale/enable wiring** — `execute_channel_action()` now handles `scale`/`adjust`/`increase_budget` and `enable`/`resume` per channel (Google, Meta, TikTok, Snapchat, LinkedIn).
- [x] **HubSpot backfills** — leads (24,260 → 11,460 rows) + deals (31,557 → 13,595 rows) backfilled to BQ, 2026-01-08 to 2026-05-05.
- [x] **Landing page performance analysis built** — `final_url` added to `ads_daily` schema and Google Ads BQ collector. New BQ views: `v_lp_performance_weekly` (week × lp_type × campaign, joins HubSpot via campaign_name) and `v_lp_weekly_summary` (week × lp_type rollup). 669 rows backfilled (30 days). Data shows HubSpot LP (`campaigns.qoyod.com`) CPQL ~$127 vs WordPress LP (`lp.qoyod.com`) CPQL ~$713 for week of Apr 27. `google_ads_ads` collector added to `reporting_scheduler.py` so `final_url` updates every 6h.
- [x] **Add LP comparison cell to Hex dashboard** — SQL below. Filter starts 2026-05-04 (WordPress LP test start). Title: "🏠 Landing Page Performance — Weekly (Test from 2026-05-04)".
  ```sql
  SELECT week_start, lp_type, lp_domain, active_campaigns,
         ROUND(spend,2) AS spend_usd, impressions, clicks,
         ROUND(ctr_pct,1) AS ctr_pct, hs_leads, hs_qualified,
         hs_disqualified, ROUND(disq_rate_pct,1) AS disq_rate_pct,
         ROUND(cpl,2) AS cpl, ROUND(cpql,2) AS cpql
  FROM `angular-axle-492812-q4.qoyod_marketing.v_lp_weekly_summary`
  WHERE week_start >= '2026-05-04'
  ORDER BY week_start DESC, spend_usd DESC
  ```

## Done this session (2026-05-04)

- [x] **Hex sub-campaign SQL cells** — added Ad Groups/Ads/Keywords for Google Ads; Ad Sets/Ads for Meta, Snapchat, TikTok, LinkedIn. Each cell joins `adsets_daily`/`ads_daily` → `hubspot_leads_module_daily` on `lead_utm_audience`/`lead_utm_content` showing spend, CTR, leads, SQLs, CPL, CPQL.
- [x] **Organic Search section deleted** — section + all child cells removed from Hex (no paid drill-down data)
- [x] **Orphaned cells deleted** — `adsets_data`, `Ad Performance Summary`, SQL 105, SQL 115 removed
- [x] **Hex dashboard published** — all changes live at https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest
- [x] **`scripts/create_health_tasks.py` deleted** — one-off script with hardcoded wrong spend data
- [x] **`utm-lead-measurement.md` skill created** — codifies CPL/CPQL join patterns at all grains, TikTok trap, zero-lead diagnosis steps
- [x] **Activities summary posted to #notify** — Slack message listing all Hex changes

## Done this session (2026-05-03)

- [x] **Slack cleanup** — stopped verbose "Agent actions" from posting to #notify; only category × count in summary
- [x] **Overdue task Slack blast removed** — `asana_maintenance.py` now logs overdue tasks to console only (no Slack post)
- [x] **Per-channel assignees** — Google Ads tasks → Rana Khalid (GID 1208007704598388); all others → Donia Mohamed (GID 1211896896006183)
- [x] **Morning status task disabled** — `nexa-morning-status` scheduled task disabled (was posting unwanted Slack message with old dashboard URL)
- [x] **Old HTML report routes removed** — `/paid-performance/latest`, `/reports/latest`, `/paid-performance/<date>`, `/reports/<date>` now 301-redirect to Hex dashboard; `/api/regenerate` deleted
- [x] **Session learning hook** — `session_start_review.py` now reads the most recent session transcript summary so each session starts from where the last left off
- [x] **Deep IS recommendations** — `google_ads_audit_tasks.py` now provides root-cause playbook (dayparting, match-type waste, QS components, extensions, LP experience) instead of "raise budget"
- [x] **Hex dashboard as canonical** — DASHBOARD_URL env var → Hex; old Railway HTML URL decommissioned everywhere

## Done this session (for audit trail)

- [x] **Campaign naming enforcement** — `executors/naming.py` with product aliases, audience validation, LinkedIn UTM mapping
- [x] **LinkedIn API fixed** — targetingCriteria, locale en/US, campaign_group_name stored in BQ
- [x] **LinkedIn UTM join** — CASE WHEN in campaign_health.py + bq_writer.py view to join on campaign_group_name
- [x] **Slack daily format** — peak numbers (top+worst per channel), agent actions spelled out, recommendations in follow-up message
- [x] **Asana task footer** — Created, Due, Priority, Type, Channel, Asset level, Action on every task
- [x] **Approval flow** — optimize/junk findings send approval request to #approvals; scale/pause logged as EXECUTED
- [x] **Pre-send review hook** — `.claude/settings.json` PreToolUse hook fires before Slack posts and Asana task creation
- [x] **ASANA_ASSIGNEE_GID** — set to Donia's GID in `.env`
- [x] **CLAUDE.md** — updated with naming convention, LinkedIn UTM table, KPI rules, pre-send review checklist
- [x] Meta multi-account fix
- [x] Snap collector (with `conversion_sign_ups` fix)
- [x] Unified channel_roas_daily view + supporting views
- [x] 6h reporting scheduler
- [x] Meta organic collector (FB + IG with Nov-2025 survivors)
- [x] YouTube collector (awaits creds)
- [x] LinkedIn collector (awaits creds)
- [x] OAuth helper scripts (linkedin_oauth, youtube_oauth, meta_organic_setup)
- [x] 3-page Streamlit dashboard scaffolding
- [x] memory/ playbook (00–09)
- [x] 3-agent restructure (Paid Media / Analyst / PM in repo; Creative +
  MarkOps external) — md_files, claude/roles.py, miro scripts updated
- [x] Snap collector broader conversion fields + currency check + fallback
- [x] LinkedIn refresh helper (`scripts/linkedin_refresh.py`)
- [x] `memory/11_agent_roles.md` (in-repo vs external agent map)
- [x] `memory/12_funnel_io.md` + `.claude/skills/funnel-io.md`
- [x] Funnel.io File Import Webhook creds wired to `.env`
- [x] Deleted dead `collectors/hubspot_bq.py`
- [x] Renamed `scheduler.py` → `operational_scheduler.py`
