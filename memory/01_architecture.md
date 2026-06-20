# Architecture

## Data flow

```
  Ad platforms            HubSpot             Organic APIs
  ┌───────────┐         ┌───────────┐        ┌───────────┐
  │ Google Ads│         │  Leads    │        │ FB/IG/YT/ │
  │   Meta    │         │  Deals    │        │ LinkedIn  │
  │ Snapchat  │         │ Pipelines │        │           │
  │  TikTok   │         └─────┬─────┘        └─────┬─────┘
  │ Microsoft*│               │                    │
  │ LinkedIn* │               │                    │
  └─────┬─────┘               │                    │
        │                     │                    │
        └─ collectors/*_bq.py ─┴────────────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │   BigQuery: qoyod_marketing│
        │   (partitioned + clustered)│
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │   Views (collectors/views)│
        │   paid_channel_daily/...  │
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │ Hex dashboards (2)        │  ← Hex-hosted (read from BQ)
        │   Performance: Qoyod-marketing-performance
        │   Activity:    Nexa-Agent-Activity
        │ n8n Cloud                 │  ← analysis, Slack, Asana, approvals
        │   7 workflows             │
        └───────────────────────────┘

* = pending / blocked (see 02_credentials.md)
```

## Parallel pipeline: Funnel.io (learn-only reference)

Funnel.io is the team's existing reporting layer. We do **not** write to
it. We read it — via UI audits, API, and the Funnel BQ export (if
enabled) — to understand the custom dims/metrics that power the Looker
boards Amar's team already uses. Our Streamlit dashboards are then
designed to mirror Funnel's labels + formulas (so numbers match) and
extend them where Funnel can't reach (HubSpot Lead module, adset/ad
grain, creative-type tags).

```
  Same ad platforms + HubSpot
        │
        └─► Funnel.io (Connect/Organize) ─┬─► Looker Studio (existing boards)
                     │                    ├─► Funnel BQ export (if enabled)
                     │                    └─► Google Sheets (ad-hoc)
                     │
                     └── READ ONLY ──► our `memory/12_funnel_io.md`
                                        (custom dim/metric audit,
                                         dashboard spec input)
```

- **Funnel** = canonical cross-channel view the team already trusts.
  Our job: understand it, don't touch it.
- **Our pipeline** = agent-readable BigQuery + Streamlit, code-owned,
  feeds pause/scale decisions and adds the dims Funnel can't show.

See `.claude/skills/funnel-io.md` for the audit / reconciliation recipes.

## Two runtimes — do NOT conflate

| Runtime | Purpose | Cadence | Where |
|---|---|---|---|
| **n8n Cloud** | All scheduling, analysis, Slack, Asana, Sheets, approval gates | Daily/weekly/monthly + various sub-schedules | n8n Cloud (qoyod.app.n8n.cloud) |
| **GitHub Actions** | Python BQ collectors — all platform data writes to BigQuery | Every 6h (00/06/12/18 UTC) | `.github/workflows/collectors.yml` |

**Railway:** deprecated — no longer runs schedulers or analysis. Still live pending user decision to shut down and GitHub Secrets migration.

`operational_scheduler.py`, `reporting_scheduler.py`, `main.py` — **deleted** (2026-06-16 cleanup). n8n and GitHub Actions own all cadences.

### n8n workflow inventory (12 workflows — canonical)

| Workflow | n8n ID | Schedule | Nodes | Status |
|---|---|---|---|---|
| Nexa · Master Performance Workflow | `T8icImtZFLYeCa7e` | Daily 05:00 UTC (08:00 Riyadh) | 84 | ACTIVE |
| Nexa · Weekly Performance Review | `iNSdpXH7Rc9Lb8h8` | Sunday 05:00 UTC | 26 | ACTIVE |
| Nexa · Monthly Performance Review | `0Zh45UoTtjjhRn8U` | 1st of month 05:00 UTC | 32 | ACTIVE |
| Nexa · Data Collection | `jOnJxdpdaO3Vbi0B` | Called by Master (sub-flow) | 52 | ACTIVE |
| Nexa · Approval Listener | `5Acqsbxsk0XQ5k9e` | Webhook (Slack reactions) | 7 | ACTIVE |
| Nexa · QA Gate | `ug3niLKrjPfO9Iz7` | Called by Master (sub-flow) | — | ACTIVE |
| Nexa · Sub-Flow A (ROAS & Channel Health) | `MHCdIiAtKzHNve1x` | Called by Master Switch | — | ACTIVE |
| Nexa · Sub-Flow B (CPL Fix) | `Qd5SoGxZbgT1ohYP` | Called by Master Switch | — | ACTIVE |
| Nexa · Sub-Flow C (CPQL Fix) | `jfE5KKnPJQBf7MCj` | Called by Master Switch | — | ACTIVE |
| Nexa · Sub-Flow D (Qual Ratio Fix) | `PxFBmtXDVgcNGzIM` | Called by Master Switch | — | ACTIVE |
| Nexa · Sub-Flow E (Impression Share Fix) | `eL0V6ReftV2U1wNf` | Called by Master Switch | — | ACTIVE |
| Nexa · Sub-Flow F (Creative & CTR Fix) | `smHaEhWloComRQyz` | Called by Master Switch | — | ACTIVE |
| Infra: Agent Activity Dashboard → GitHub Pages | `Szq6QhBIn44SfaHH` | Every 1 hour | 7 | ACTIVE |

**GitHub Pages activity dashboard:** `https://rana96-run.github.io/nexa-performance-agent/` — built by workflow `Szq6QhBIn44SfaHH`. Queries `agent_activity_log` (last 50), `asana_task_status` (open, 20), `connector_health_log` (last 24h). Pushes `docs/index.html` via GitHub Contents API. Repo made public 2026-06-19 to enable Pages. GITHUB_TOKEN added to n8n variables.

**Deleted 2026-06-17 (stale/superseded):**
- `7ZEROvwTg3UrGAP6` — Nexa · Databox Sync (superseded; Databox reads directly from BQ via native connector)
- `H6XSFlp1WOUPpgBF` — Nexa · Monitor Follow-up (BQ monitoring covered by Master workflow)
- `yOD1l9n7qOfbpWfM` — Nexa · AI Content Agent (called `somaa-ai-agent-production.up.railway.app` — different project, not Nexa)

**Approval Listener:** `5Acqsbxsk0XQ5k9e` — Slack webhook at `https://qoyod.app.n8n.cloud/webhook/slack-approval`. Receives `reaction_added` events, resumes waiting executions. Now handles Slack `url_verification` challenge (responds with `{challenge: <value>}` on `type === url_verification`, routes real events to Extract Reaction). Requires Slack App Event Subscriptions configured.

### GitHub Actions collector schedule

`.github/workflows/collectors.yml` — runs all 13 Python BQ collectors at 00:00/06:00/12:00/18:00 UTC. `google_ads_bq.py` is called with `all 35` (35-day rolling window to avoid full-history timeout in CI).
`.github/workflows/linkedin_token_refresh.yml` — refreshes LinkedIn token daily at 02:00 UTC.

Collectors are the **only** Python runtime still in active use. All other Python entrypoints (`main.py`, `operational_scheduler.py`, `reporting_scheduler.py`, `app_server.py`) were deleted 2026-06-16.

## Repo layout (as of 2026-06-16 cleanup)

Deleted in 2026-06-16 cleanup: `analysers/` (28 files), `notifications/` (7 files), `main.py`, `operational_scheduler.py`, `reporting_scheduler.py`, `claude/` (legacy roles/personas), `Open PowerShell.bat`, `lp_tracker_formatted.xlsx`, 25+ stale scripts.

`app_server.py` and `reports/` still live — required by Railway web service, pending shutdown.

```
Nexa Performance Agent/
├── collectors/             # BQ collectors (one per data source) — run by GitHub Actions
│   ├── bq_writer.py        # shared: MERGE helper + schemas
│   ├── views.py            # creates all reporting VIEWs; refresh_all_views() called after each collect
│   ├── google_ads_bq.py    # campaign + adgroup + ad + keywords grain
│   ├── meta_bq.py          # campaign + adset + ad grain
│   ├── snap_bq.py          # campaign + adset + ad grain
│   ├── tiktok_bq.py        # campaign + adgroup + ad grain
│   ├── linkedin_bq.py      # campaign + ads grain
│   ├── microsoft_ads_bq.py # CONNECTED both accounts (188176729 + 187231519)
│   ├── hubspot_leads_bq.py # lead module daily buckets
│   ├── hubspot_deals_bq.py # deals daily buckets
│   ├── ga4_bq.py           # GA4 sessions/conversions
│   └── databox_pusher.py   # manual backfill only; Databox reads directly from BQ via native connector
├── executors/              # write actions (pause, scale, Asana, keywords)
├── logs/                   # activity_logger.py → agent_activity_log BQ
├── scripts/                # OAuth flows + audit tools (no schedulers)
├── .github/
│   └── workflows/
│       ├── collectors.yml         # runs all collectors every 6h (00/06/12/18 UTC)
│       └── linkedin_token_refresh.yml # refreshes LinkedIn token daily 02:00 UTC
├── config.py               # env-driven config
├── memory/                 # ← this folder (shared org memory)
├── docs/                   # playbooks, knowledge, shared docs
└── .claude/                # agents, skills, hooks, settings
```

## BQ table inventory (canonical — update when tables are added/dropped)

### Source tables (written by collectors)
| Table | Collector | Key fields |
|---|---|---|
| `campaigns_daily` | google_ads_bq, meta_bq, snap_bq, tiktok_bq, linkedin_bq, microsoft_ads_bq | date, channel, campaign_id |
| `ads_daily` | same collectors | date, channel, campaign_id, ad_id |
| `keywords_daily` | google_ads_bq, microsoft_ads_bq | date, channel, campaign_id, adgroup_id |
| `hubspot_leads_module_daily` | hubspot_leads_bq.py | date, qoyod_source, lead_utm_campaign |
| `hubspot_leads_individual` | hubspot_leads_bq.py | hs_object_id |
| `hubspot_deals_daily` | hubspot_deals_bq.py (VIEW — compat wrapper over `hubspot_deals_individual`; collector writes via `mirror` subcommand) | date, pipeline, qoyod_source |
| `hubspot_deals_individual` | hubspot_deals_bq.py (`mirror` subcommand) | hs_object_id |
| `organic_page_daily` | meta_organic_bq, youtube_bq | date, channel |
| `ga4_sessions_daily` | ga4_bq.py | date, landing_page (last seen 2026-06-17, 37 rows) |
| `gsc_organic_daily` | planned — collector not yet built (no gsc_*.py in collectors/) | date, page, query |
| `gsc_organic_staging` | planned — collector not yet built | date, page, query |
| `agent_activity_log` | activity_logger.py | role, status |
| `connector_health_log` | connector_tracker.py | connector, check_type |
| `asana_task_status` | asana_sync.py | task_id |

### Reporting VIEWs (sourced from wide_ads, refreshed every 6h by `refresh_all_views()`)

As of 2026-06-15, all reporting views are `CREATE OR REPLACE VIEW` objects sourced from `wide_ads`
(not materialized physical tables). They are rebuilt by `refresh_all_views()` in `collectors/views.py`
every 6h via the reporting scheduler.

| View | Source | Notes |
|---|---|---|
| `paid_channel_campaign_daily` | `wide_ads` | Campaign-level blended: spend + leads + deals + CPL/CPQL/ROAS |
| `paid_channel_daily` | `wide_ads` | Channel-level daily rollup |
| `v_adset_performance` | `wide_ads` | Adset-level performance |
| `v_ad_performance` | `wide_ads` | Ad-level performance |
| `v_keyword_performance` | `wide_keywords` | Keyword-level performance |

**DROPPED 2026-06-15 (were BASE TABLEs, replaced by VIEWs from wide_ads):**
- `paid_channel_daily` — was a materialized chain table; now a VIEW sourced from wide_ads
- `paid_channel_campaign_daily` — same
- `v_adset_performance` — same
- `v_ad_performance` — same

**DROPPED 2026-06-15 (no longer used):**
- `utm_paid_attribution_daily` — attribution spine replaced by wide_ads materialization
- `channel_roas_daily` — replaced by `paid_channel_daily` (wide_ads-sourced VIEW)

### Current layer summary
| Layer | Tables/Views | Written by |
|---|---|---|
| Layer 0 (store) | `campaigns_daily`, `ads_daily`, `keywords_daily`, `hubspot_leads_module_daily`, `hubspot_deals_daily`, etc. | collectors/* |
| Layer 1 (individual mirrors) | Per-platform raw rows in the above store tables | same collectors |
| Layer 2 (wide tables) | `wide_ads`, `wide_keywords` | `collectors/views.py::materialize_wide_tables()` — rebuilt every 6h |
| Layer 3 (reporting views) | `paid_channel_daily`, `paid_channel_campaign_daily`, `v_adset_performance`, `v_ad_performance`, `v_keyword_performance`, `v_channel_key_map` | `collectors/views.py::refresh_all_views()` — sourced from wide_ads/wide_keywords |

### Lightweight views (from `ALL_VIEWS` + `_sub_campaign_views()`)
| View | Purpose |
|---|---|
| `v_keyword_performance` | Keyword grain with QS, IS, leads |
| `v_channel_key_map` | RESTORED 2026-06-16 — still referenced by Hex SQL cells; 'Tiktok Ads' casing bug fixed 2026-06-19 |

### Dropped tables (do not recreate)

**Dropped 2026-06-09:**
hubspot_leads_daily, channel_roas_monthly, campaign_performance, campaign_performance_daily,
campaign_performance_monthly, disqualification_matrix, pipeline_funnel, lead_funnel_by_pipeline,
lead_utm_performance, v_lp_combined_weekly, v_lp_ga4_daily, v_lp_ga4_funnel_daily,
v_lp_performance_weekly, v_lp_weekly_summary, v_session_lead_match, v_signup_funnel_weekly,
v_website_funnel_daily

**Dropped 2026-06-15 (replaced by VIEWs from wide_ads — see reporting VIEWs section above):**
utm_paid_attribution_daily, channel_roas_daily

**Dropped 2026-06-16 (0 active analysis consumers) — physically deleted from BQ 2026-06-19:**
platform_campaign_snapshot, pmax_asset_groups_daily, v_agent_activity_dashboard,
v_agent_consumption_daily, v_new_biz_daily

**Dropped 2026-06-16 (dataset consolidation — write-only sinks or migrated):**
- `qa_gate_events` — write-only ops sink; gate.py/self_test.py now log to stdout
- `adsets_daily` — only consumer (reports/app.py scale endpoint) migrated to wide_ads;
  6 collector write calls removed (Google/Meta/Snap/TikTok/LinkedIn/Microsoft)
- `gclid_attribution` — write-only; no Python reads feed attribution decisions;
  gclid_clickview daily scheduler call removed; gclid removed from connector_tracker
- `v_channel_key_map` — 7-row CASE view inlined into 3 consumers as CASE expressions

## Tech choices (and why)

- **BigQuery** over Postgres: free for our volume, native GA4/Sheets/Looker,
  partition pruning keeps query cost near zero.
- **Load jobs, not streaming inserts**: streaming buffer blocks DELETE for 90min,
  breaking idempotent re-runs. See `08_pitfalls.md`.
- **Hex over Streamlit**: Hex reads directly from BQ, survives Railway redeploys,
  no separate hosting cost, collaborative editing. Dashboards at:
  - Performance: `Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK`
  - Activity: `Nexa-Agent-Activity-033ArC9Xytz3SK6tPXwk9D`
- **Railway** for hosting: **DEPRECATED** (2026-06-16). Was running schedulers + Flask. Now pending shutdown pending GitHub Secrets migration. n8n Cloud owns all scheduling/analysis; GitHub Actions owns collectors.
- **Databox** for external BI dashboards: two active datasets pushed by the n8n `Nexa · Master Performance Workflow` (Databox chain embedded as parallel branch after Schedule trigger). `collectors/databox_pusher.py` still exists for manual backfills.
  - **Daily Spend** (`199c5297`): channel-day grain. Fields: date (DATETIME), channel (STRING),
    spend/impressions/clicks/leads/sqls/cpl/cpql (NUMBER). Use SUM for volumes, AVG for ratios.
  - **All Grains** (`6158be78`): 4-grain unified dataset (campaign/adset/ad/keyword).
    Fields: date (DATETIME), grain/channel/utm_campaign (STRING),
    spend/impressions/clicks/leads/sqls/cpl/cpql/qual_rate_pct (NUMBER).
  Data source ID: `4983171` (PAK-linked "Qoyod BQ"). Account ID: `756469`.
  Superseded All Grains IDs: v3 `eff4621e` (bad schema wrapper → string types), v1/v2 all-string.
  Run backfill: `railway run python -c "from collectors.databox_pusher import run_push; run_push(days=365)"`
  Police check: `analysers/connector_tracker.py` SYSTEM_MONITORS includes both datasets.

## HubSpot Field Distinct Values (confirmed from BQ — 2026-06-19)

### hubspot_leads_individual — qoyod_source

| qoyod_source | cnt |
|---|---|
| Google Ads | 10535 |
| Direct Traffic | 4435 |
| Snapchat Ads | 4053 |
| Meta Ads | 4029 |
| Organic Search | 3934 |
| Offline | 2436 |
| Tiktok Ads | 1645 |
| Direct In-app Purchase | 1502 |
| Microsoft Ads | 750 |
| Organic Social | 185 |
| Email Marketing | 163 |
| Referrals | 159 |
| Other | 59 |
| LinkedIn Ads | 9 |
| youtube | 1 |
| Twitter Ads | 1 |

### hubspot_leads_individual — lead_utm_medium

| lead_utm_medium | cnt |
|---|---|
| NULL | 12010 |
| ppc | 10441 |
| Meta_LeadGen_Form_CallTimeAdded_New | 1582 |
| Snapchat_LeadGenForm_Generic | 1498 |
| INSTANT_FORM | 1118 |
| Snpchat_Beginning2026_Short | 1007 |
| Meta_Form_Beginning2026_MoreVolume_Short | 922 |
| none | 629 |
| New Structure Form 2025 | 546 |
| Phone Call | 509 |
| Meta_Bookkeeping_MoreVolume | 399 |
| organic | 348 |
| Snapchat_Generic_Form_New_Account | 336 |
| Snpchat_NewAcc_Beginning2026_Short | 257 |
| Meta_Form_Beginning2026_HigherIntent_Short | 246 |
| Whatsapp_Marketing_Messages | 218 |
| email | 201 |
| Pangle | 190 |
| social | 186 |
| Snapchat_Bookkeeping_Qoyod2024 | 133 |
| organic search | 126 |
| Bookkeeping2026_NewAcc | 104 |
| Meta_Bookkeeping_HigherIntent | 92 |
| Facebook_Mobile_Feed | 79 |
| Whatsapp | 78 |
| an | 77 |
| Facebook_Mobile_Reels | 75 |
| paidsocial | 51 |
| referral | 35 |
| Bookkeeping_Form_New_Account | 31 |
| paid | 30 |
| Snapchat_FoundingDay_SimpleForm | 30 |
| Whatsapp_Meta_Flow | 27 |
| Snapchat_Bookkeeping_Simpleform | 26 |
| Instagram_Reels | 25 |
| Tiktok_Form_Beginning2026_Short | 20 |
| TikTok | 19 |
| Comment | 18 |
| __PLACEMENT__ | 12 |
| Tiktok_LeadGenForm_Generic_NewAccount | 12 |
| internal | 10 |
| Message | 10 |
| facebook_feed | 9 |
| Tiktok | 8 |
| Snapchat | 8 |
| Instagram_Feed | 8 |
| Office Visit | 7 |
| snapchat | 6 |
| test-med | 5 |
| - | 5 |
| facebook_mobile_feed | 5 |
| Social | 5 |
| LinkedIn_E-Invoice_Form | 4 |
| Facebook_Stories | 4 |
| Email | 4 |
| Ads | 3 |
| offline | 3 |
| Instagram_Stories | 3 |
| Others | 3 |
| test_medium | 3 |
| Facbook_Mobile_Feed | 3 |
| Facebook_Instream_Video | 3 |
| Facebook_Desktop_Feed | 2 |
| linkedin | 2 |
| Facebook_Notification | 2 |
| Snapchat_LeadGen_QFlavours_2024 | 2 |
| Event | 2 |
| Meta | 2 |
| reseller | 2 |
| Twitter | 2 |
| . | 2 |
| Snpachat | 1 |
| PPC | 1 |
| Tiktok_MainForm_TimeAdded_NewZap/EOY | 1 |
| unknown | 1 |
| {{placement}} | 1 |
| Paid Social | 1 |
| POP-UP | 1 |
| Behavior Based | 1 |
| c | 1 |
| call | 1 |

### hubspot_leads_individual — lead_utm_source

| lead_utm_source | cnt |
|---|---|
| NULL | 11383 |
| Google | 9442 |
| Snapchat | 4017 |
| fb | 3168 |
| Tiktok | 1550 |
| Bing | 916 |
| ig | 697 |
| direct | 630 |
| Other | 587 |
| google.com | 400 |
| hs_email | 191 |
| chatgpt.com | 172 |
| bing.com | 110 |
| an | 91 |
| tiktok.com | 79 |
| tiktok | 66 |
| bing | 64 |
| instagram.com | 26 |
| snapchat | 26 |
| Meta | 25 |
| Email Marketing | 23 |
| snapchat.com | 19 |
| twitter.com | 19 |
| qoyod.com | 18 |
| Facebook.com | 18 |
| partnerstack | 14 |
| youtube.com | 11 |
| qoyod | 10 |
| Offline | 10 |
| facebook.com | 9 |
| Instagram.com | 9 |
| adwords | 9 |
| Event | 8 |
| search.yahoo.com | 8 |
| - | 5 |
| LinkedIn | 5 |
| facebook | 5 |
| google | 5 |
| test-so | 5 |
| app.qoyod.com | 4 |
| Social media | 4 |
| copilot.com | 3 |
| LinkedIn.com | 3 |
| test_source | 3 |
| Email | 3 |
| . | 2 |
| linkedin.com | 2 |
| com.google.android.googlequicksearchbox | 2 |
| partnership | 2 |
| Snapchat.com | 2 |
| email | 1 |
| call | 1 |
| {{site_source_name}} | 1 |
| tagassistant.com | 1 |
| Whatsapp | 1 |
| c | 1 |
| yahoo.com | 1 |
| template | 1 |
| Twitter | 1 |
| hs_automation | 1 |
| perplexity | 1 |
| personal | 1 |
| Qoyod | 1 |
| Snpachat | 1 |
| Tiktok.com | 1 |
| ا | 1 |

### hubspot_deals_individual — qoyod_source

| qoyod_source | cnt |
|---|---|
| Google Ads | 27272 |
| Offline | 18854 |
| Direct Traffic | 13199 |
| Organic Search | 6732 |
| Other | 5704 |
| Meta Ads | 4306 |
| Snapchat Ads | 3499 |
| Tiktok Ads | 2734 |
| Email Marketing | 1139 |
| Referrals | 572 |
| Direct In-app Purchase | 416 |
| Microsoft Ads | 320 |
| Organic Social | 221 |
| LinkedIn Ads | 17 |
| Twitter Ads | 15 |
