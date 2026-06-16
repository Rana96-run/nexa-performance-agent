# Open Tasks — Prioritized Work Queue

Ordered by dependency + user priority. Check off as done; append new items at
the bottom of the relevant section.

> **Status as of 2026-06-17:** 12-workflow n8n architecture live (Master + Weekly + Monthly +
> Data Collection + Approval Listener + QA Gate + 6 sub-flows A–F). 3 stale workflows deleted
> (Nexa · Databox Sync, Nexa · Monitor Follow-up, Nexa · AI Content Agent — superseded or wrong project).
> Slack `url_verification` challenge fixed in Approval Listener — webhook now echoes `{challenge}`
> before routing to reaction logic. Railway deprecated — pending shutdown.
> GitHub Actions owns all Python BQ collectors (every 6h). QA Gate wired into Master.
> 3-layer agent hierarchy (AI Orchestrator → QA Auditor + Project Coordinator → 7 agents).

## P0 — Agent clarity + Cowork migration (spec approved 2026-06-11)

Spec: `docs/superpowers/specs/2026-06-11-agent-clarity-cowork-migration-design.md`
5 phases — do in order. Railway stays live as fallback throughout.

- [x] **Phase 1 — Agent file cleanup (Claude Code). DONE 2026-06-11.** Updated all 9 `.claude/agents/*.md`
      files with the 7-field standard (scope + does-NOT-own, skills + trust tiers, memory
      READ/WRITE, receives-from, hands-to, reports-to). Created `memory/agents/` per-agent
      private folder structure. Commits: `dd2f5ff` (folders), `1ea1a64` (agent files).
- [x] **Phase 2 — Cowork skill files. DONE 2026-06-12.** 12 skill files in
      `.claude/skills/cowork/`: daily-loop, weekly-review, keyword-autofix (scheduled),
      campaign-manager, creative-strategist, growth-analyst, cro-specialist,
      project-coordinator, performance-lead (on-demand).
      + 3 new automation skills (2026-06-12): monthly-creative-report (1st of month,
      creative-strategist → Google Sheet per channel, winning criteria qual>50% + CPL≤$30),
      daily-slack-audit (10:00 Riyadh, project-coordinator → check #approvals reactions,
      remind in-thread, flag execution gaps), monthly-performance-deck (1st of month,
      performance-lead → full-funnel Slides deck, all 3 new-biz pipelines).
      Commits: `820efc1` (first 9), pending commit (last 3).
- [x] **Phase 3 — Cowork connectors. DONE 2026-06-12.** All 6 connectors wired in Cowork UI.
      - [x] BigQuery (`angular-axle-492812-q4`)
      - [x] Slack (local dev custom app in Qoyod Slack workspace)
      - [x] Asana (token + workspace ID from Railway)
      - [x] Meta Ads (token + account IDs from Railway)
      - [x] Google Ads (dev token + refresh token + both account IDs from Railway)
      - [x] HubSpot (token from Railway, portal 144952270)
      - [x] Drive folder shared with service account; subfolder IDs set in Railway
      - [x] `collectors/drive_reader.py` complete with upload/find_in_folder
      Note: Slack connector uses a local dev custom Slack app — token lives in Railway (`SLACK_BOT_TOKEN`), all IDs readable from Railway env.
- [ ] **Phase 4 — Daily loop on Cowork.** Multi-agent chain (ai-orchestrator → growth-analyst
      → performance-lead → campaign-manager ∥ creative-strategist) with approval gate.
      Full workflow spec: `docs/cowork-phase4-workflow.md`.
      Key constraint: Cowork sandbox cannot run BQ analysis — Railway runs analysers, Cowork
      reads outputs via Asana + BQ connector. Schedule Cowork at 08:05 Riyadh (5 min after
      Railway 08:00). Run parallel for 14 days, then retire Railway LLM layer.
      Start condition: all 6 Phase 3 connectors wired.
- [ ] **Phase 5 — n8n wiring (optional, independent).** Replace Railway Python collectors
      one-by-one with n8n workflows. Verify BQ ↔ HubSpot reconciliation stays <2% delta
      after each replacement. Owner: `project-coordinator`. Can run independently of Phases 1-4.

**Also included in Phase 1:**
- [x] **Activity dashboard: 4-panel redesign DONE 2026-06-12.** Marketing Decisions
      (performance_audit/keyword_management/daily_digest/spike_detector), Approval Outcomes,
      System Health (collapsed, auto-expands on failure), Cowork Activity (placeholder).
      Heatmap filtered to Panel 1 roles only. No new BQ queries — uses existing detail_rows
      + infra_rows. Commit: `5e3e0f8`.
- [x] **Slack digest: minimal format DONE 2026-06-12.** `post_nightly_approvals_digest` rewritten
      with 3-block structure: PERFORMANCE (one line per channel w/ spend·leads·CPQL icon),
      ACTIONS (scale/pause with single ✅/❌ gate), REVIEW ONLY (Asana links). Channel summary
      fetched from BQ `paid_channel_daily` using `qualified` column. CPQL icons: ✅ <$85, ⚠️ $85–$130,
      🔴 >$130. All 4 smoke tests passing. Commit: `cbbbbf2`.
      Plan: `docs/superpowers/plans/2026-06-11-phase1b-slack-format.md`.

## P0 — Police findings open (detected 2026-06-08, not yet closed)

Surfaced by `connector_health_log` + freshness check. Route via the police loop
(`docs/_shared/police-loop.md`): owner fixes → growth-analyst verifies → orchestrator reports.
- [x] **LinkedIn — 95-day stale → NOT A BUG (resolved 2026-06-08).** There are **no
      active LinkedIn campaigns** and haven't been for ~95 days, so zero data is
      CORRECT (idle, not broken). No fix needed. The real defect is that the police
      *flagged* an idle channel — fixed by the idle-aware rule below.
- [x] **"BROKEN" google/bing/hubspot_leads → FALSE POSITIVES, FIXED 2026-06-08.**
      Root cause was 3 bugs IN `connector_tracker.py` (not the connectors):
      (1) it queried channel `google`/`bing` but `campaigns_daily` stores
      `google_ads`/`microsoft_ads` → 0 rows → false BROKEN; (2) freshness/row SQL
      hardcoded a `channel` column that HubSpot tables lack → `400 Unrecognized name`;
      (3) `_STALE_HOURS=28` false-WARNED 1-day-old data daily. Fixed all three +
      idle-aware (LinkedIn now HEALTHY-IDLE). After fix: 1 BROKEN, 2 WARNING, 6 HEALTHY.
- [x] **`hubspot_deals` ~10-day stale → self-resolved.** VERIFY (2026-06-08) showed
      the collector caught up: MAX(date)=2026-06-08, continuous daily rows since
      2026-05-28. Was a transient incremental-window lag, now fresh. No action.
- [ ] **🔴 PHONE NUMBER IN DEAL AMOUNT (HUMAN fix needed):** deal **`505631711439`**
      ("نوادر الانعام - New Deal", Bookkeeping pipeline, owner **Nouran Emad**) has
      `amount` = **966504406958 SAR** = the phone number **+966 50 440 6958** (966 = KSA
      code) typed into the Amount field — inflating pipeline value to $257.7B.
      Link: https://app.hubspot.com/contacts/144952270/record/0-3/505631711439
      **HubSpot read-only → human sets Amount to the real SAR value**, then re-run
      `collectors/hubspot_deals_bq.py`. Police now auto-detects this (amount_sanity +
      `_looks_like_phone` on the native SAR value).

## P1 — Police expansion: watch the WHOLE system, not just inbound connectors

The police (connector_tracker) is inbound-only. Detectors for other surfaces exist
but are scattered + have gaps. Aggregate all under one health view + close the 🔴 gaps
(see `docs/_shared/police-loop.md` scope table). Each routes through the police loop.
- [x] **Outbound delivery checks — DONE (`e5c8226`).** `check_outbound_action()` + 2 new SYSTEM_MONITORS: `slack_digest_posted` (26h on `posted_approvals_digest`) and `asana_tasks_live` (48h on `asana_task_created`). Also added `bq_refresh_ran` (14h window).
- [ ] **Executor-action verification:** after an approved pause/scale/keyword executes,
      confirm it actually applied on-platform (read back the ad/keyword state). Owner: `campaign-manager`.
- [x] **Credential liveness — DONE (`e5c8226`).** `check_credential_liveness()` makes a live API ping per connector (Meta /me, TikTok /user/info, LinkedIn /me, HubSpot /owners). Returns BROKEN on 401/403. Added as 6th check in `run_connector_check()`.
- [x] **Cost anomaly check — DONE (`e5c8226`).** `check_cost_anomaly()` reads `cost_usd` from `agent_activity_log`; today > 3× 7d avg → WARNING. Added to SYSTEM_MONITORS.
- [x] **Aggregate the detectors — DONE (`e5c8226`).** `get_police_status()` — single call returns `{overall, broken[], warnings[], healthy_count, summary}` across all connectors + monitors. Verified: RED 4 broken, 1 warning, 11 healthy.
- [x] **Persistent-WARNING → BROKEN escalation** — DONE (2026-06-10). `check_persistent_warning()` added to `connector_tracker.py`: 3 consecutive WARNING rows in `connector_health_log` → escalates to BROKEN for that channel. Idle channels exempt.
- [x] **Align dashboard `reports/app.py` role-sets — DONE (`e5c8226`).** Fixed 4 orphans: `task_creator` + `daily_digest` → ai-orchestrator; `paid_media_strategist` → performance-lead; `campaign_creator` → campaign-manager; `collector` → marketing-ops.

## P1 — Attribution overhaul + workflow re-enrollment (DONE — 2026-05-15)

Built on top of Option B from 2026-05-14:

- **`gclid_attribution` BQ table** — daily refresh from Google Ads `click_view` API
  for Auto Cloud (5753494964) + Qoyod New (1513020554) sub-accounts. 30-day rolling
  window. Resolves any gclid to campaign/ad_group/ad. Google ID attribution
  1% → 77%.
- **`v_lead_attribution` view** — 4-strategy unified attribution (A_sync, B_gclid,
  C_url_param, D_name). Diagnostic for ad-hoc queries. Not wired into Hex
  dashboards yet — they use Strategy A + D via existing breakdown views.
- **HubSpot workflow re-enrollment + goal** — `Digital Marketing: Populating
  Qoyod Sources` workflow now re-enrolls on `hs_google_click_id` and
  `hs_facebook_click_id` property changes. Goal locks paid attribution from
  being overwritten. Captures ~90 phantom-paid leads/month.
- **Google + Microsoft Final URL Suffix** — saved at account level, applies
  to all campaigns (overrides included). Adds `campaign_id`/`ad_group_id`/`ad_id`
  to every ad-click URL. HubSpot's URL parameter capture writes them to contact.
- **BQ refresh schedule: 24h → 12h** — second refresh at 20:00 Riyadh in addition
  to the 08:00 Riyadh nightly. Halves attribution-lag for workflow reclassifications.
- **`collectors/gclid_clickview.py` scheduled daily** — runs after `_refresh_bigquery()`
  in `_nightly()`. Without this, the table goes stale and gclid attribution
  degrades to 0% over 30 days.
- **`ATTRIBUTION_EVOLUTION.md`** in `.claude/hex_drilldown/` — markdown doc
  for Hex stakeholder context.

Reconciliation status (settled days, last 7d):
- Deals: BQ 643 vs HubSpot 637 = +0.9% delta ✓
- Leads paid: BQ 1174 vs HubSpot 1211 = -3.1% delta (dominated by today's mirror lag)
- Day-by-day for completed days: ±15 oscillation (sync timing), within ~1% target

## P1 — Option B ID-first attribution rebuild (DONE — 2026-05-14)

`paid_channel_campaign_daily`, `v_adset_performance`, `v_ad_performance` now
join leads + deals on `*_id_sync` first, with name-fallback for channels that
don't populate sync IDs (Google/Bing/LinkedIn website forms).

Verified outcomes:
- Snapchat duplicate-name campaign correctly separates into 2 rows by `campaign_id`
  (one $582 spend + 17 leads, one $0 spend + 1 deal won)
- Google name-fallback reconciles within 0.5% to HubSpot
- Snapchat ID-attribution reconciles within ~2.5% sync lag

Deal sync columns added to `hubspot_deals_daily`:
`deal_campaign_id_sync`, `deal_adgroup_id_sync`, `deal_ad_id_sync`.
YTD backfill complete (15,431 rows). Coverage: Snap 94%, Meta 88%, TikTok 87%,
Google 1% (expected — those go through name-fallback).

### Hex follow-up (manual — flagged for Amar)

Hex dashboards reading `deals_won`, `revenue_won`, `roas`, `amount_total`,
`amount_lost`, `amount_open` from the 3 views will break. Rename to:
- `deals_won` → `new_biz_deals_won`
- `revenue_won` → `new_biz_revenue_won`
- `roas` → `new_biz_roas`
- etc.
The 3 views now expose `campaign_id` (new column on `paid_channel_campaign_daily`)
— useful for disambiguating duplicate-named campaigns.

## P0 — Unblocks everything else

(YouTube + Funnel.io removed 2026-05-14 per user direction — not in scope.)

## P1 — PMax sector campaigns (DONE — 2026-05-13)

All 5 sector campaigns created via API. Amar enabled 3 preferred campaigns,
paused the 5 sector campaigns. Audience signals added manually in UI.

Campaign IDs (customer 5753494964):
- Services: 23834877561 → ag/6712034766 (52 assets)
- Technology: 23844719995 → ag/6712034769 (53 assets, 26 search themes)
- Real Estate: 23835216687 → ag/6712037109 (52 assets, 28 search themes)
- Retail: 23845053748 → ag/6712036947 (50 assets, 19 search themes)
- WP: 23840470733 → ag/6712057318 (51 assets, 42 search themes)
- Retail: 23845053748 → ag/6712036947 (50 assets, 19 search themes)
- WP: 23840470733 → ag/6712057318 (51 assets, 42 search themes)

## P1 — Attribution depth (DONE 2026-05-13)

- [x] **Creative type tagging** — `creative_type STRING` added to `ads_daily` schema.
  Meta: `_creative_type_lookup()` fetches `creative{object_type}` per account.
  TikTok: `ad_format` captured in `_list_ads()` and mapped.
  Snap: `type` field captured in `_list_ads()` and mapped.
  Google/Microsoft: NULL (no creative type at ad grain).
  Values: image | video | carousel | collection | story | other

## P2 — LinkedIn campaign cloning (DONE 2026-05-15)

- [x] `list_campaign_creatives(campaign_id)` — lists all creatives in an ad set
- [x] `clone_campaign_creatives(source, target)` — copies reference URN + lead gen form
- [x] `create_full_campaign(..., clone_from_campaign_id=...)` — optional clone param
- [x] `scripts/linkedin_oauth.py` — added `rw_organization_admin` scope
- [x] **LinkedIn token re-minted** — verified active with `rw_organization_admin`,
  expires 2026-07-19. `clone_campaign_creatives()` now functional.

## P2 — Databox unified dataset (DONE — 2026-06-08)

- [x] **Dataset v3 created** with NUMBER schema at creation time (only way to get SUM/AVG
  aggregation in Databox — type inference always gives STRING/COUNT).
  Dataset ID: `eff4621e-a0ef-4e93-bcf6-9c48f6e8d4ae`
  dataSourceId at creation: `4983171` (PAK-linked source)
- [x] **UTM column naming** — channel=utm_source (BQ slug), qoyod_source=HubSpot label,
  utm_medium=form/placement, grain dimension separates campaign/adset/ad/keyword levels.
  Hierarchy: utm_campaign → utm_audience → utm_content (ads) / utm_term (keywords).
- [x] **Snapchat adsquads included** in adset grain via `v_adset_performance`
  (9,483 rows, 251 distinct adsquads confirmed in last 30 days).
- [x] **365-day backfill complete** — all 4 grains:
  - campaign: 38,184 records
  - adset:    61,763 records
  - ad:      194,394 records
  - keyword:  24,628 records
- [x] **Superseded datasets deleted** — v1 `739cde4e` (wrong names, all-string),
  v2 `9ec1816a` (correct names, all-string). Only v3 active.
- [x] **`collectors/databox_pusher.py`** — `run_push(days=N, grains=[...])` is the
  entry point. PARTITION BY fix (hs. alias scope), flush=True on all prints.

## P3 — Nice-to-have

- [ ] Weekly email digest via Gmail SMTP (creds set)
- [ ] A/B test tracker view (same utm_audience, different utm_content)
- [ ] SEMrush integration for keyword / competitor view (API key set)
- [ ] Snapchat organic (doubtful — no public page metrics API)

---

## Done this session (2026-06-16) — n8n full build

- [x] **n8n Workflow 1: Nexa · Master Performance Workflow** (`T8icImtZFLYeCa7e`) — already existed, audited and hardened across previous sessions. Needs manual activation toggle in n8n UI.
- [x] **n8n Workflow 2: Nexa · Weekly Performance Review** (`iNSdpXH7Rc9Lb8h8`, 21 nodes).
  - Runs Sunday 08:00 Riyadh. BQ 7d vs prior 7d per channel → Claude analysis → Slack + Asana.
  - Added LP Audit branch (parallel from Schedule): BQ LP SQL → Code format → Sheets create tab `LP-{date}` in sheet `120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg` → write rows → Asana `LP Weekly Review — {date}` draft.
  - Needs manual activation toggle in n8n UI.
- [x] **n8n Workflow 3: Nexa · Monthly Performance Review** (`0Zh45UoTtjjhRn8U`, 25 nodes).
  - Runs 1st of month 08:00 Riyadh. Full-funnel BQ → Claude → Slack + Asana.
  - Added Phase 2 Creative Report branch: BQ `v_ad_performance` 30d → classify Winner/Optimise/Underperformer → Sheets tab `Creatives-{YYYY-MM}` → Asana `WINNING CREATIVES — {Month}` task.
  - Added Phase 3 LP Brief branch: BQ best LP prior month → Asana `[DRAFT] LP Duplicate Brief` (skips gracefully if 0 SQLs).
  - Needs manual activation toggle in n8n UI.
- [x] **n8n Workflow 4: Nexa · AI Content Agent** (`yOD1l9n7qOfbpWfM`, 13 nodes) — built and ACTIVE. 4 independent chains: daily-ai-digest, competitor-post-poller, weekly-ai-digest, monthly-content-calendar.
- [x] **Cowork tasks disabled** — 6 tasks now fully covered by n8n and disabled: `daily-ai-digest`, `competitor-post-poller`, `weekly-ai-digest`, `monthly-content-calendar`, `monday-review`, `monthly-review`.
- [x] **Activated:** `Nexa · Master Performance Workflow`, `Nexa · Weekly Performance Review`, `Nexa · Monthly Performance Review`, `Nexa · Monitor Follow-up` — all toggled ON.
- [ ] **⚠️ ACTIVATION NEEDED:** Toggle ON `Nexa · Databox Sync` (`7ZEROvwTg3UrGAP6`) in n8n UI (requires `DATABOX_TOKEN` $var first).
- [ ] **⚠️ n8n $var NEEDED:** Set `DATABOX_TOKEN` in n8n UI → Settings → Variables (PAK token, not push token). Required by `Nexa · Databox Sync` workflow `7ZEROvwTg3UrGAP6`. Dataset ID: `6158be78`.

## P0 — Post-n8n-migration: pending items (2026-06-17)

- [ ] **Add GitHub Secrets to repo** (copy from Railway env vars) — blocks GitHub Actions collectors going live. Required vars: all platform tokens, BQ service account, HubSpot token, etc. Path: GitHub repo → Settings → Secrets and variables → Actions.
- [ ] **Shut down Railway service** (user approval required) — after GitHub Actions confirmed working. Railway project: `nexa-performance-agent` in Marketing Workspace (`57f124d0`).
- [ ] **Configure Slack App Event Subscriptions for Approval Listener** — URL: `https://qoyod.app.n8n.cloud/webhook/slack-approval`, event: `reaction_added`. Required for Master workflow approval gate to resume on ✅/❌ reactions. ✅ `url_verification` challenge fixed 2026-06-17 — webhook now echoes `{challenge}` before routing real events. Go to Slack App → Event Subscriptions → paste URL → it will verify successfully.
- [ ] **Add QA feed cell in Hex** — SQL template in `memory/16_activity_dashboard.md`. User doing manually.
- [ ] **Test Data Collection sub-workflow first run** (`jOnJxdpdaO3Vbi0B`) — verify no runtime errors, all channel data flows into BQ, freshness check fires correctly.
- [ ] **Activate `Nexa · Databox Sync`** (`7ZEROvwTg3UrGAP6`) — after `DATABOX_TOKEN` n8n $var is set.

**PATCH method confirmed for n8n cloud internal API** — `PUT /rest/workflows/{id}` returns 404. Use `PATCH /rest/workflows/{id}` for all workflow updates. See `memory/08_pitfalls.md`.

## Done this session (2026-06-16) — n8n hardening: Tasks 2-7

**Spec:** n8n workflow hardening spec (6 tasks, approved same session).

- [x] **Task 2 — Master workflow error resilience (84 nodes).** All 11 platform HTTP nodes
      now have `onError: continueErrorOutput`. Each has a corresponding `Error Skip · {Channel}`
      Code node (`return []`) so per-channel Merge still fires with 0 items on failure.
      Microsoft Ads was the only gap — added `Error Skip · Microsoft Ads` node + wired both
      MS nodes. Workflow ID: `T8icImtZFLYeCa7e`.

- [x] **Task 3 — BQ freshness guard on Weekly + Monthly.** Both workflows now start:
      `Schedule → BQ · Freshness Check → IF · Data Fresh? → continue or Slack · Stale Data Alert`.
      Freshness SQL: `MAX(date)` from `campaigns_daily`, alert if `days_stale > 1`.
      Weekly: 21→26 nodes. Monthly: 25→32 nodes. IDs: `iNSdpXH7Rc9Lb8h8`, `0Zh45UoTtjjhRn8U`.

- [x] **Task 4 — Nexa · Monitor Follow-up workflow built (11 nodes, ID: `H6XSFlp1WOUPpgBF`).**
      Daily 06:00 UTC. Queries `agent_activity_log` for actions where 7d or 14d post-action
      review is pending → fetches current CPQL from BQ → classifies outcome (improved/neutral/
      regressed/no_data) → posts Asana comment on original task → Slack summary.
      ⚠️ Needs manual activation in n8n UI.

- [x] **Task 5 — Weekly 2-agent chain.** Added `Build · performance-lead` + `Claude · performance-lead`
      after `Claude · weekly-analyst`. Performance-lead validates findings, escalates CPQL
      regressions, adds executive summary. Rewired: analyst → Build PL → Claude PL → Parse · weekly.
      Weekly now 26 nodes.

- [x] **Task 6 — Monthly 3-agent chain.** Main path: monthly-analyst → performance-lead → Parse.
      Creative branch: `Code · Format Creative → Build · creative-strategist → Claude · creative-strategist
      → Sheets · Create Creative Tab`. Creative-strategist classifies Winner / Optimise / Underperformer
      per ad (qual_ratio + CPL). Monthly now 32 nodes.

- [x] **Task 7 — Databox push migrated to n8n (ID: `7ZEROvwTg3UrGAP6`).** New workflow: every 6h,
      4 parallel BQ grain queries (campaign/adset/ad/keyword from `wide_ads`) → Merge → Code transform
      (SOURCE_MAP, strip nulls) → SplitInBatches(100) → HTTP POST to Databox dataset `6158be78`.
      Railway `reporting_scheduler.py` Databox block disabled (`60807b1`). Memory `05_scheduler.md`
      updated with all 6 n8n workflows.
      ⚠️ Needs DATABOX_TOKEN as n8n $var + manual activation.

## Done this session (2026-06-11)

- [x] **GTM: `MetaPixel_Lead_Event` tag created (Tag ID 331, workspace 60).** Client-side `fbq('track','Lead')` on trigger 279 (HS Thank You Page). Published by user 2026-06-11.
- [x] **GTM: Server-side CAPI chain fully verified.** `{{Stape | Server URL}}` resolves to `https://sig.qoyod.com`. `GA4|Configuration` (Tag 131) routes all GA4 events to server via `transport_url`. Elementor forms on both `www.qoyod.com` (tag 328) and `lp.qoyod.com` (tag 326) push `lead_generation_success` to dataLayer → GA4 `generate_lead` event (Tag 257) fires → server container `generate_lead` trigger → Meta CAPI. HubSpot forms (non-Elementor) covered by Tag 331 client-side only.
- [x] **GTM audit false positives all fixed.** `[Stape]` legacy tags skipped, GA4 config detection restricted, pixel ID check Meta-only, GTM variable references not flagged as bad IDs, `_REQUIRED_SERVER_TAGS` updated with real Stape type codes. Committed `e3c6308`, `f347eaa`, `672d862`, `d441b57`.
- [x] **GA4 WoW analysis column fix.** `avg_session_duration_s * sessions` replaces nonexistent `total_session_duration_s`. Committed `d97fca2`.
- [x] **CRO department dashboard gap fixed.** Root cause: dev-time CRO subagents never called `log_activity()`. Created `scripts/log_cro_work.py` CLI logger. Updated `cro-specialist.md`, `ui-ux-designer.md`, `developer.md` — each now has a mandatory BQ log step in "Done means". All future CRO work will appear on the activity dashboard under `cro_analysis` / `lp_design` / `lp_deploy` roles.

## Done this session (2026-06-10, final)

- [x] **Slack listener + LinkedIn connectors now HEALTHY.** Both were showing BROKEN in the activity dashboard — now resolved. Confirmed by user on 2026-06-10.
- [x] **Connector health: idle suppression extended (`bdadded`).** `attribution` and `credentials` checks now suppressed for idle/known_paused channels — LinkedIn no longer generates false WARNINGs when campaigns are paused.
- [x] **Slack listener monitoring added (`bdadded`).** `check_slack_listener_heartbeat()` registered in SYSTEM_MONITORS. `slack_listener.py` writes a BQ heartbeat every 10 poll cycles (~10 min). Health check window: 2h.
- [x] **3-consecutive-BROKEN alert → Asana escalation (`bdadded` + later).** `alert_consecutive_broken()` now creates an Asana task assigned to marketing-ops (not a Slack post) when any connector/monitor has been BROKEN for 3+ consecutive hourly checks. Dedup via `agent_activity_log` (6h window). Marketing-ops owns the fix; growth-analyst reviews after.
- [x] **Hourly health check upgraded (`bdadded`).** `_run_health_check()` in `operational_scheduler.py` now runs the full `run_all_checks()` (with BQ write) instead of the lightweight script — so `alert_consecutive_broken` fires hourly.
- [x] **GA4 collector built (`9a86462`).** `collectors/ga4_bq.py` — daily sessions / engaged sessions / users / conversions / bounce rate from GA4 Data API → `ga4_sessions_daily`. Wired into 6h refresh in `reporting_scheduler.py`. Property ID: 517912363.
- [x] **Connector failure escalation chain defined (`bdadded`).** `marketing-ops.md` updated: owns activity dashboard, diagnoses/fixes connectors, hands off to growth-analyst. `growth-analyst.md` updated: owns post-fix data integrity review (7d BQ↔HS reconciliation, QA gate — 3+ HEALTHY + <2% delta + no view drift — final sign-off).
- [x] **BQ ↔ HubSpot reconciliation tolerance set to 2%** (updated per user request).
- [x] **Creative & Landing Pages on-demand section added to dashboard (`d771ffc`).** Three new cards: (1) Creative Performance Audit → creates Asana task for Creative Strategist with best-to-scale/worst-to-replace direction; (2) New Creative Variants Brief → OCEAN-aligned A/B brief per segment for Creative Strategist; (3) New Landing Page Brief → auto-fills `create_lp_brief()` from live BQ CPQL data, creates Asana chain CRO → UI/UX → Developer.
- [x] **Activity dashboard fully structured.** On-Demand Actions panel now has three rows: Campaign Operations, Audits, Creative & Landing Pages. All existing actions confirmed healthy.

## Done this session (2026-06-10, continued)

- [x] **`/activity` UnboundLocalError resolved (`f7101e5`).** Cache read path was missing 8 variables added after the cache was designed (`user_rows`, `intel_rows`, `task_status_rows`, `executed_rows`, `followup_rows`, `new_ads_rows_raw`, `hc_rows`, `fresh_rows`) — caused `UnboundLocalError` on every request served from cache.
- [x] **4xx requests no longer logged as `dashboard_error`.** `_handle_exception` in `reports/app.py` now skips BQ logging for `HTTPException` with code < 500. `/favicon.ico` 404s were flooding `agent_activity_log` with false dashboard errors.
- [x] **Databox health check switched to BQ (`f7101e5`).** Old check hit `/v1/datasets/{id}/ingestions` which requires UUID format — short ID `6158be78` returns HTTP 400. New check reads `agent_activity_log WHERE role='databox_push'`. `databox_pusher.py` now logs each successful push. Collapsed two Databox monitors into one.

## Done this session (2026-06-10)

- [x] **Views: LOWER/TRIM deal stub matching confirmed correct in Hex (`ee0ab00`).** Deal amounts
      now flow into `v_adset_performance` and `v_ad_performance` via case+space-insensitive
      name matching (`LOWER(TRIM(utm_audience/utm_content))`) — previously deals were silently
      dropped when UTM casing didn't match adset/ad names exactly.
- [x] **Manual HubSpot collect no longer stales Hex (`12700f6`).** `hubspot_deals_bq.py` and
      `hubspot_leads_bq.py` now call `create_views()` automatically after any `collect_and_write()`,
      so a manual re-pull rebuilds all materialized views immediately instead of waiting for
      the next 6h scheduler tick.
- [x] **BQ vs HubSpot reconciliation — PASSED (2026-06-10, window 2026-06-03 to 2026-06-09):**
      Leads: BQ 1,213 vs HS 1,205 = +0.66% delta ✓ (sync timing lag, expected).
      Deals: BQ 1,613 vs HS 1,613 = exact match ✓. Amount: BQ $295,473 vs HS $298,572 = -1.04% ✓ (within 5% tolerance).
      Daily lead volumes: 170 / 185 / 112 / 161 / 179 / 196 / 210 (Wed–Tue). Qualified rate ~39%.

## Done this session (2026-06-09)

- [x] **Knowledge base restructure — complete.** Swept all 18 session transcripts
  and 44 project memory files. Extracted every finding/learning/action into typed
  files under `docs/knowledge/` (52 findings, 15 learnings, 3 actions, 7 project
  docs). Claude Code auto-memory (`C:\Users\qoyod\.claude\projects\...\memory\`)
  now holds ONLY 13 `feedback_*.md` behavior-rule files + MEMORY.md index.
  No knowledge or data lives in memory. No duplicates anywhere.

- [x] **Agent consolidation — complete.** All 9 agent definitions now live ONLY
  in `.claude/agents/<name>.md` (single source of truth per role). Removed stale
  boot-sequence references to `docs/playbooks/` and `memory/agents/` from all 9
  agents. Added `## Done means` to each agent (folded in from deleted playbooks).
  Deleted `docs/playbooks/` (11 files) and `memory/agents/` (21 files). No agent
  definition exists anywhere outside `.claude/agents/`.

- [x] **memory/ clutter removed.** Moved `memory/knowledge_base/` → `docs/knowledge/`;
  moved `memory/utm_template.md` → `.claude/skills/utm-template.md`; deleted
  `memory/audit_findings.md` and `memory/dashboard_violations.jsonl` (data files
  with no home in operational memory). Updated `memory/11_agent_roles.md` to
  remove stale references to deleted paths.

## Done this session (2026-05-16)

- [x] **Activity dashboard — 6-member agent team roster** — new "Agent Team" section
  above the contribution heatmap. 6 cards in a responsive grid, each showing job title,
  description, role identifier chips, 30d/7d action counts, and last action date.
  Role → title mapping: `ops_scheduler` → Performance Marketing Manager,
  `bq_refresh` → Data Engineer, `spike_detector`+`performance_audit` → Analyst & Insights
  Specialist, `llm_cadence` → Strategist Specialist, `keyword_management` → Paid Media
  Manager, `daily_digest`+`slack_approval` → Communication Specialist.
  Zero extra BQ queries — computed by filtering already-fetched `detail_rows`,
  `infra_rows`, `intel_rows` on the `role` column. Commit: `c16439d`.

- [x] **Recommendation engine: alternatives-considered + pre-execution sanity** — 3 improvements:
  1. `analysers/campaign_health.py`: every finding now carries `alt_budget_cut_pct` and
     `alt_recommendation`. For pause candidates, computes whether a budget reduction (10–55%)
     would bring CPQL to `CPQL_ACCEPTABLE` without a full pause. For scale, flags qual rate
     confidence.
  2. `analysers/campaign_health_tasks.py`: Asana task bodies enriched with:
     - Scale tasks: `_recent_spend_trend()` (last-3d vs 14d avg) produces sanity block —
       no_recent_spend / declining / stable / accelerating.
     - Pause tasks: "Alternatives considered" section — Option A (budget cut %) vs Option B
       (full pause) so approvers have reasoning before reacting in Slack.
  3. `notifications/slack.py`: `post_nightly_approvals_digest` enriched one-liners —
     scale shows spend-trend tag (⚠️ declining / ✅ accelerating), pause shows
     💡 alt: cut -N% budget first when viable. Commit: `17e1b97`.

- [x] **Temp debug scripts deleted** — `scripts/_check_*.py`, `scripts/_rebuild_views.py`,
  `scripts/_probe_ms_*.py`, `scripts/_dump_ms_report.py` (9 files, all untracked).
  Working tree clean.

## Done this session (2026-05-15)

- [x] **Activity dashboard KPI bar fixed** — `paid_channel_daily` columns are
  `leads_total` (not `leads`) and `qualified` (not `sqls`). `agent_activity_log`
  timestamp is `ts` (not `created_at`). `ARRAY_AGG ORDER BY NULLS LAST` unsupported
  in BQ — use `COALESCE(cpql, 99999)`. KPI query now uses `WITH latest AS (SELECT
  MAX(date)...)` instead of hardcoded `INTERVAL 1 DAY` so it always shows the
  latest available date. Committed: `a369c5b`.
- [x] **Health check freshness threshold fixed** — `health_check.py` was flagging
  stale at `> 1 day`, causing a nightly false positive (before 08:00 Riyadh data is
  legitimately 2 days old). Aligned to `check_freshness.STALE_THRESHOLD_DAYS = 3`.
  LinkedIn (`KNOWN_PAUSED`) excluded from failure report. Committed: `1f71867`.
- [x] **Railway Pro project confirmed + documented** — live project is
  `nexa-performance-agent` in Marketing Workspace (`57f124d0`). Personal account
  project (`1b3ee05a`) deleted. Documented in memory + `feedback_deploy_workflow.md`.
- [x] **YouTube OAuth script built** — `scripts/youtube_oauth.py` opens Google
  auth in browser, catches callback on :8080, writes `YT_REFRESH_TOKEN` +
  `YT_CHANNEL_ID` to `.env`. Run with `railway run python scripts/youtube_oauth.py`.
  Not yet executed (browser step requires local approval).
- [x] **Dashboard load time: 20s → ~2s** — root cause was 14 BQ queries running
  sequentially after a parallel batch that was supposed to replace them. The parallel
  block pre-fetched all 14 results but 7 downstream blocks re-defined the same SQL
  and re-ran `bq.query().result()` sequentially, overwriting the parallel results.
  Removed all 7 duplicate sequential blocks (-352 lines). Cold load now runs one
  14-way `ThreadPoolExecutor` batch (~2s) with no follow-on queries. Full-page HTML
  cache (5-min TTL) serves warm loads in <100ms. Commits: `5024c55`, `34af5fb`.
- [x] **Railway canonical domain corrected** — `nexa-performance-agent.up.railway.app`
  was never provisioned (returns Railway 404). Confirmed via `railway variables` that
  the live URL is `https://nexa-web-production-6a6b.up.railway.app`. Updated
  `08_pitfalls.md` and user memory. Commit: `c280ac9`.
- [x] **Nightly BQ refresh manually triggered** — nightly at 05:00 UTC May 15
  was missed (service deploy window overlap). Ran `reporting_scheduler once` locally
  to pull May 14 data into `paid_channel_daily`. Dashboard now shows May 14 data.

## Done this session (2026-05-13)

- [x] **Railway dual-project fix** — found two `nexa-performance-agent` projects (trial + pro)
  both auto-deploying from GitHub. Deleted the trial personal workspace project. Canonical
  project: `57f124d0` in Marketing Workspace. Documented in `memory/08_pitfalls.md`.
- [x] **PMax ads tab fix** — added `AND LOWER(utm_campaign) NOT LIKE '%pmax%'` to Google Ads
  `3_ads.sql` to remove PMax asset group names that were appearing as ad names with 0 leads.
- [x] **TikTok/Meta ID-based attribution (Strategy C/D)** — added new matching layers to
  `v_adset_performance` and `v_ad_performance` for when UTM names break:
  - Strategy C: adset-ID fallback via `lead_ad_group_id` (future Meta use)
  - Strategy D (new): TikTok campaign-ID fallback via `lead_campaign_id_sync` →
    `adsets_daily.campaign_id`. Confirmed `lead_campaign_id_sync` matches `campaigns_daily.campaign_id`
    exactly for TikTok leads (e.g. `1863074553592178`). `campaign_id` / `ad_group_id` / `ad_id`
    are NULL for both TikTok and Meta as of 2026-05-13.
  - New BQ columns: `lead_campaign_id_sync`, `lead_campaign_id`, `lead_ad_group_id`, `lead_ad_id`
    in both `hubspot_leads_individual` and `hubspot_leads_module_daily`.
  - `create_views()` updated: auto-drops TABLE before recreating as VIEW (prevents lock).
  - Cursor sync (`mirror`) running to backfill IDs for all 2026 leads.

## Done this session (2026-05-12)

- [x] **Snap concurrent API** — replaced sequential per-ad calls with
  ThreadPoolExecutor(8 workers). Added 429 retry with linear backoff in `_snap_get`.
  Speed: hours → ~5 min for 1,000 ads.
- [x] **Microsoft utm_audience attribution** — 3-layer fix:
  1. Collector now parses `{_adgroup}` custom param key (not `audience`) for utm_audience
  2. `v_adset_performance` platform CTE: `COALESCE(utm_audience, adset_name)` (was `adset_name` only)
  3. `v_ad_performance` platform CTE: `COALESCE(utm_content, ad_name)` (was `ad_name` only)
  Verified: `Bing_AR_Brand_Keywords` spend=1365, leads=194, sqls=104 ✓
- [x] **Microsoft adset rename fix** — "Cloud Accounting" → "Bing_Cloud_Accounting" rename
  caused BQ history mismatch with HubSpot. Fix: YTD backfill (132 days, 1,045 rows).
  Microsoft API returns current name for all historical dates → all rows updated.
  Views rematerialized. Arabic adsets now join correctly.
- [x] **Microsoft ads YTD backfill** — 132 days for ads level (running/complete).
- [x] **PMax sector campaigns created** — `scripts/clone_pmax_sectors.py` updated with
  atomic `GoogleAdsService.mutate()` batch (asset_group + all assets in one call).
  Fixed: LONG_HEADLINE capped at 5, undersized logos (32×32) filtered out,
  LOGO/BUSINESS_NAME pulled from campaign-level assets and merged into batch.
  All 5 campaigns created with full asset groups + search themes copied.
- [x] **Memory/skill cleanup** — `09_open_tasks.md` condensed; auto-refresh skill added.

---

## Archived sessions (condensed)

**2026-05-11:** Full HubSpot mirror sync (no cursor drift), Snapchat channel
mismatch fix, Riyadh date bucketing fix, BQ view materialization (6 heavy views
→ physical tables rebuilt every 6h), qual/disq rate formula fixed.

**2026-05-10:** HubSpot deals dual-pass fix, 2025 full backfill (110K deals),
SDR/Partnerships stale row fix, Eid seasonality confirmed as root cause of
mid-March dip.

**2026-05-06-07:** All YTD sub-level backfills (TikTok, Meta, Google, Snap ads/adsets),
keyword policy extended (competitors, language mismatch), Snap 142K rows, Hex
auto-refresh wired, ROAS close-date fix.

**2026-05-04-05:** HubSpot backfills, LP performance analysis + Hex cell, landing
page CPQL comparison (HubSpot LP $127 vs WP LP $713), Channel Deep Dive / Leads
Funnel / Insights & Recommendations Hex cells, no-UTM row in all campaign tables,
PMax asset-group collector.

**2026-05-03:** Slack cleanup, per-channel Asana assignees, Hex as canonical
dashboard, deep IS recommendations in keyword audit.

**Earlier:** Campaign naming enforcement, LinkedIn/TikTok/Snap collectors, OAuth
helpers, 6h reporting scheduler, meta organic collector, memory playbook.
