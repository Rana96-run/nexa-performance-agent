# Open Tasks — Prioritized Work Queue

Ordered by dependency + user priority. Check off as done; append new items at
the bottom of the relevant section.

## P0 — Unblocks everything else

- [ ] **Re-mint LinkedIn tokens** — `LI_ACCESS_TOKEN/ORG_URN/AD_ACCOUNT_URN`
  currently empty. Run `python scripts/linkedin_oauth.py` then `... orgs`,
  paste outputs to `.env`. Follow-ups via `scripts/linkedin_refresh.py`.
- [ ] **Run YouTube OAuth** — `python scripts/youtube_oauth.py`. Writes
  `YT_REFRESH_TOKEN` + `YT_CHANNEL_ID` to `.env` (slots empty today).
- [ ] **Microsoft Ads — BLOCKED on qoyod IT.** OAuth script exists
  (`scripts/microsoft_oauth.py`), collector exists (`collectors/microsoft_ads_bq.py`,
  3 grains). Blocker: qoyod.com Azure AD tenant lacks the Microsoft Advertising
  service principal (error `AADSTS650052`). Personal-account fallback also
  blocked: Microsoft migrated `rana.khalid@qoyod.com` personal → work
  (`PersonalIdentityMigratedToWork`), and the Ads account itself is locked to
  qoyod.com tenant so fresh outlook.com accounts get rejected (`AADSTS500200`).
  **Fix requires a Global Admin on qoyod.com to run:**
  ```powershell
  Install-Module Microsoft.Graph -Scope CurrentUser -Force
  Connect-MgGraph -Scopes "Application.ReadWrite.All"
  New-MgServicePrincipal -AppId "d42ffc93-c136-491d-b4fd-6f18168c68fd"
  ```
  After that, re-run `python scripts/microsoft_oauth.py` (currently set to
  `/consumers/` — flip back to `/common/`) signed in as `@qoyod.com` work.
  Customer ID already set: `MS_CUSTOMER_ID=254476670`. Account: `G1206XJR`.
  See `memory/08_pitfalls.md` for full trap analysis.
  Deprioritized — MS Ads is ~3% of Saudi paid search.
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

- [ ] **Channel Deep Dive (Hex)** — section header + SQL 102 added to Hex notebook
  (adset grain × CPL zone coloring: Scale/OK/Watch/Pause). Still needs:
  Leads Funnel section + Insights/Recs section (browser was freezing mid-run)
- [ ] **Leads Funnel (Hex)** — disqualification reasons + sub-reasons.
  Property names confirmed: `leads_disqualification_reason__ops` (main, 10 opts)
  + `leads_disqualification_reason__sub_reasons` (31 opts). `top_disq_sub_reason`
  now stored in `hubspot_leads_module_daily`. SQL ready to add to Hex.
- [ ] **Insights & Recommendations (Hex)** — rules-based recs using
  `v_campaign_leaderboard` + `v_channel_scorecard`. SQL ready to add to Hex.
- [ ] **"(no UTM — click-ID only)" explicit row** in every campaign table

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
