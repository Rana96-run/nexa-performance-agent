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

**Deleted 2026-06-17 (stale/superseded):**
- `7ZEROvwTg3UrGAP6` — Nexa · Databox Sync (pushed to legacy Databox API; superseded by Railway Python pusher + direct BQ integration in Databox)
- `H6XSFlp1WOUPpgBF` — Nexa · Monitor Follow-up (BQ monitoring covered by Master workflow)
- `yOD1l9n7qOfbpWfM` — Nexa · AI Content Agent (called `somaa-ai-agent-production.up.railway.app` — different project, not Nexa)

**Approval Listener:** `5Acqsbxsk0XQ5k9e` — Slack webhook at `https://qoyod.app.n8n.cloud/webhook/slack-approval`. Receives `reaction_added` events, resumes waiting executions. Now handles Slack `url_verification` challenge (responds with `{challenge: <value>}` on `type === url_verification`, routes real events to Extract Reaction). Requires Slack App Event Subscriptions configured.

### GitHub Actions collector schedule

`.github/workflows/collectors.yml` — runs all 14 Python BQ collectors at 00:00/06:00/12:00/18:00 UTC.
`.github/workflows/linkedin_token_refresh.yml` — refreshes LinkedIn token daily at 02:00 UTC.

Collectors are the **only** Python runtime still in active use. All other Python entrypoints (`main.py`, `operational_scheduler.py`, `reporting_scheduler.py`, `app_server.py`) were deleted 2026-06-16.

## Repo layout (as of 2026-06-16 cleanup)

Deleted in 2026-06-16 cleanup: `analysers/` (28 files), `notifications/` (7 files), `reports/` (3 files), `main.py`, `operational_scheduler.py`, `reporting_scheduler.py`, `app_server.py`, `claude/` (legacy roles/personas), `Open PowerShell.bat`, `lp_tracker_formatted.xlsx`, 25+ stale scripts.

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
│   └── databox_pusher.py   # manual backfill only; live push is n8n Databox Sync
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
| `hubspot_deals_daily` | hubspot_deals_bq.py | date, pipeline, qoyod_source |
| `organic_page_daily` | meta_organic_bq, youtube_bq | date, channel |
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
| ~~`v_channel_key_map`~~ | Dropped 2026-06-16 — inlined as CASE in consumers |

### Dropped tables (do not recreate)

**Dropped 2026-06-09:**
hubspot_leads_daily, channel_roas_monthly, campaign_performance, campaign_performance_daily,
campaign_performance_monthly, disqualification_matrix, pipeline_funnel, lead_funnel_by_pipeline,
lead_utm_performance, v_lp_combined_weekly, v_lp_ga4_daily, v_lp_ga4_funnel_daily,
v_lp_performance_weekly, v_lp_weekly_summary, v_session_lead_match, v_signup_funnel_weekly,
v_website_funnel_daily

**Dropped 2026-06-15 (replaced by VIEWs from wide_ads — see reporting VIEWs section above):**
utm_paid_attribution_daily, channel_roas_daily

**Dropped 2026-06-16 (0 active analysis consumers):**
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
