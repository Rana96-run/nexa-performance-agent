# Open Tasks — Prioritized Work Queue

Ordered by dependency + user priority. Check off as done; append new items at
the bottom of the relevant section.

## P0 — Unblocks everything else

- [ ] **Re-mint LinkedIn tokens** — `LI_ACCESS_TOKEN/ORG_URN/AD_ACCOUNT_URN`
  currently empty. Run `python scripts/linkedin_oauth.py` then `... orgs`,
  paste outputs to `.env`. Follow-ups via `scripts/linkedin_refresh.py`.
- [ ] **Run YouTube OAuth** — `python scripts/youtube_oauth.py`. Writes
  `YT_REFRESH_TOKEN` + `YT_CHANNEL_ID` to `.env` (slots empty today).
- [ ] **Run Microsoft Ads OAuth** — build `scripts/microsoft_oauth.py`
  (AAD v2 auth code flow → refresh_token). Env has client/secret/tenant/
  account; still needs `MS_REFRESH_TOKEN` + `MS_CUSTOMER_ID`.
- [ ] **Get Funnel.io read API token** — ask Amar for workspace API token
  + account_id + project_id. Fill `FUNNEL_API_TOKEN/ACCOUNT_ID/PROJECT_ID`.
- [ ] **HubSpot leads YTD backfill** — `python collectors/hubspot_leads_bq.py`
  (no args = YTD). Current data is only incremental → channel_roas_daily is
  sparse.
- [ ] **HubSpot deals YTD backfill** — `python collectors/hubspot_deals_bq.py`.

## P1 — Attribution depth (user explicitly requested)

- [ ] **Build `utm_paid_attribution_daily` view** — joins HubSpot leads
  (grouped by date + `qoyod_source` + `lead_utm_campaign` + `lead_utm_audience`
  + `lead_utm_content`) to `campaigns_daily` / `adsets_daily` / `ads_daily`
  using dual-strategy matcher (see `07_attribution.md`). Emits `__no_utm__`
  unattributed bucket row per channel/day.
- [ ] **Adset-grain collector** — extend `meta_bq.py` with `level=adset`;
  add `google_ads_adgroups_bq.py`. Write to new `adsets_daily` table.
- [ ] **Ad-grain collector** — `level=ad` for Meta, `ad_group_ad` resource
  for Google Ads. Write to `ads_daily`.
- [ ] **PMax asset-group collector** — GAQL on `asset_group` + `asset_group_asset`
  + `asset_group_asset_view`. Write to `pmax_asset_groups_daily`.
- [ ] **Creative type tagging** — for each ad row, classify as
  `{image, video, carousel, collection, reels, story}`. Requires pulling
  `creative` fields alongside insights.

## P1 — Dashboard expansion (user explicitly requested)

- [ ] **Split dashboard**: `1_Paid_Overview.py` + `2_Organic_Overview.py`
  (current `1_Live_Campaigns.py` is paid-biased)
- [ ] **`3_Channel_Deep_Dive.py`** — per-channel tabs with campaigns / adsets
  / ads tables, CPL-zone coloring, creative type pie, date window filter
- [ ] **`4_Leads_Funnel.py`** — disqualification reasons **with sub-reasons**
  (HubSpot `disqualification_reason` + `disqualification_sub_reason`
  properties — confirm exact property API names before coding)
- [ ] **`5_Insights_Recommendations.py`** — rules-based recs per channel:
  - CPL > pause zone for 3+ days → "pause campaign X"
  - CPL in scale zone + budget < cap → "scale campaign X by 20%"
  - ROAS > 3 + impression share < 70% → "raise budget / loosen targeting"
  - Creative type CTR < 0.5% → "refresh creative"
- [ ] **Deals table on Channel Deep Dive** — show deals by channel with
  stage + amount + owner
- [ ] **"(no UTM — click-ID only)" explicit row** in every campaign table

## P2 — Ops hardening

- [ ] **LinkedIn token auto-refresh** — 60-day expiry; add
  `scripts/linkedin_refresh.py` + nightly cron in scheduler
- [ ] **Slack digest of 6h refresh** — post row counts + failures to Slack
  channel after every `reporting_scheduler` pass
- [ ] **Disqualification property probe** — write
  `scripts/probe_hubspot_props.py` that lists all lead properties matching
  `disqualif*` so we know the exact API names
- [ ] **Deploy dashboard to Replit** — create Repl B per `06_dashboard.md`,
  paste secrets, share URL

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

## P3 — Nice-to-have

- [ ] **Microsoft Ads collector** (env scaffolding now present — unblocked
  once OAuth refresh token is minted)
- [ ] **TikTok Ads collector** (account IDs + pixels present; pending token)
- [ ] Snapchat organic (if Snap exposes public page metrics — doubtful)
- [ ] Weekly email digest via existing Gmail SMTP (creds set) of top KPIs
- [ ] A/B test tracker view (campaigns with same utm_audience, different utm_content)
- [ ] SEMrush integration for keyword / competitor view (API key set)

## Done this session (for audit trail)

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
