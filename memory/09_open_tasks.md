# Open Tasks — Prioritized Work Queue

Ordered by dependency + user priority. Check off as done; append new items at
the bottom of the relevant section.

> **Status as of 2026-05-16:** Agent fully operational on Railway Pro (Marketing Workspace).
> All collectors live, health check green, dashboard rendering real data, nightly
> scheduler running at 08:00 Riyadh. Activity dashboard shows 6-member team roster.
> Recommendation engine now includes alternatives-considered + pre-execution sanity checks.

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
- [ ] **Outbound delivery checks:** verify the daily #approvals Slack digest actually
      posted, Asana tasks actually created, Hex refreshed, Databox pushed, report rendered/
      uploaded to Drive — not just log-on-failure. Owner: `marketing-ops` / `ai-orchestrator`.
- [ ] **Executor-action verification:** after an approved pause/scale/keyword executes,
      confirm it actually applied on-platform (read back the ad/keyword state). Owner: `campaign-manager`.
- [ ] **Credential liveness (not just presence):** `health.py` checks env-var presence;
      add a live ping per integration (token present but expired/revoked = silent fail,
      e.g. LinkedIn). Owner: `marketing-ops`.
- [ ] **Cost/consumption anomaly check:** `cost_tracking` logs token/BQ spend but nothing
      alerts on a spike. Add a sanity check (today's cost > N× 7d avg → flag). Owner: `growth-analyst`.
- [ ] **Aggregate the detectors:** connector_tracker + self_healer + spike_detector +
      dashboard_guard + health.py + the new checks → one police status the orchestrator reads.
- [ ] **Persistent-WARNING → BROKEN escalation** (active channels only) — still to code in connector_tracker.
- [ ] **Align dashboard `reports/app.py` role-sets** to the canonical 11_agent_roles mapping
      (orphans: task_creator, collector, paid_media_strategist, campaign_creator).

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
