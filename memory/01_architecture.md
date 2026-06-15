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
        │ Flask (reports/app.py)    │  ← Railway-hosted
        │   /health, /api/refresh   │
        │   /slack/events           │
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
| **Operational scheduler** | Daily: BQ refresh, spike detector, keyword approvals, Google Ads audit, campaign health, Asana tasks, Slack daily summary | 08:00 Riyadh daily + 6h health checks | `operational_scheduler.py` → Railway |
| **Reporting scheduler** | Refresh BQ tables + views for the Hex dashboard | Every 6h | `reporting_scheduler.py loop` → Railway |

`main.py` = the LLM analysis layer (paid_media_strategist Claude role). Called by `operational_scheduler.py` for weekly/monthly/quarterly cadences only. Daily work is deterministic (no LLM).

## Repo layout

```
Nexa Performance Agent/
├── analysers/              # deterministic analysis (no LLM)
│   ├── campaign_health.py        # 14d CPQL/CPL cross-channel audit
│   ├── campaign_health_tasks.py  # → Asana tasks + scale/pause execution
│   ├── google_ads_audit.py       # IS, QS, search terms analysis
│   ├── google_ads_audit_tasks.py # → Asana tasks
│   ├── spike_detector.py         # yesterday vs 7d baseline anomaly alerts
│   ├── creative_performance.py   # per-creative qual rate (utm_content)
│   └── ad_drilldown.py           # ad/keyword drill-down Markdown tables
├── collectors/             # BQ collectors (one per data source)
│   ├── bq_writer.py        # shared: MERGE helper + schemas
│   ├── views.py            # creates all reporting VIEWs (paid_channel_daily, v_adset_performance, etc.) sourced from wide_ads; refresh_all_views() runs every 6h
│   ├── google_ads_bq.py    # campaign + adgroup + ad + keywords grain
│   ├── meta_bq.py          # campaign + adset + ad grain
│   ├── snap_bq.py          # campaign + adset + ad grain
│   ├── tiktok_bq.py        # campaign + adgroup + ad grain
│   ├── linkedin_bq.py      # campaign grain — CONNECTED (token valid 2026-05-12)
│   ├── microsoft_ads_bq.py # CONNECTED both accounts (188176729 + 187231519) 2026-05-12
│   ├── hubspot_leads_bq.py # lead module daily buckets
│   ├── hubspot_deals_bq.py # deals daily buckets
│   ├── windsor_bq.py       # Windsor.ai unified channel fallback
│   └── zapier.py           # Zapier error monitor + auto-replay
├── executors/              # write actions (pause, scale, Asana, keywords)
├── notifications/          # Slack formatters (daily_summary, slack.py)
├── logs/                   # activity_logger.py → agent_activity_log BQ
├── scripts/                # OAuth flows + bulk_ads + bulk_keywords tools
├── reports/app.py          # Flask: /health, /api/refresh, /slack/events
├── operational_scheduler.py # daily 08:00 Riyadh orchestrator
├── reporting_scheduler.py  # 6h BQ refresh for Hex dashboards
├── main.py                 # LLM cadence runner (weekly/monthly/quarterly)
├── config.py               # env-driven config
├── memory/                 # ← this folder
└── .claude/skills/         # reusable skill recipes
```

## BQ table inventory (canonical — update when tables are added/dropped)

### Source tables (written by collectors)
| Table | Collector | Key fields |
|---|---|---|
| `campaigns_daily` | google_ads_bq, meta_bq, snap_bq, tiktok_bq, linkedin_bq, microsoft_ads_bq | date, channel, campaign_id |
| `adsets_daily` | same collectors | date, channel, campaign_id, adset_id |
| `ads_daily` | same collectors | date, channel, campaign_id, ad_id |
| `keywords_daily` | google_ads_bq, microsoft_ads_bq | date, channel, campaign_id, adgroup_id |
| `pmax_asset_groups_daily` | google_ads_bq | date, channel, campaign_id |
| `platform_campaign_snapshot` | platform_snapshot.py | channel, campaign_id |
| `hubspot_leads_module_daily` | hubspot_leads_bq.py | date, qoyod_source, lead_utm_campaign |
| `hubspot_leads_individual` | hubspot_leads_bq.py | hs_object_id |
| `hubspot_deals_daily` | hubspot_deals_bq.py | date, pipeline, qoyod_source |
| `organic_page_daily` | meta_organic_bq, youtube_bq | date, channel |
| `gclid_attribution` | google_ads_bq | gclid |
| `agent_activity_log` | activity_logger.py | role, status |
| `connector_health_log` | connector_tracker.py | connector, check_type |
| `asana_task_status` | asana_sync.py | task_id |
| `qa_gate_events` | gate.py | surface, check_name |

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
| Layer 0 (store) | `campaigns_daily`, `adsets_daily`, `ads_daily`, `keywords_daily`, `hubspot_leads_module_daily`, `hubspot_deals_daily`, etc. | collectors/* |
| Layer 1 (individual mirrors) | Per-platform raw rows in the above store tables | same collectors |
| Layer 2 (wide tables) | `wide_ads`, `wide_keywords` | `collectors/views.py::materialize_wide_tables()` — rebuilt every 6h |
| Layer 3 (reporting views) | `paid_channel_daily`, `paid_channel_campaign_daily`, `v_adset_performance`, `v_ad_performance`, `v_keyword_performance`, `v_channel_key_map`, `v_agent_activity_dashboard` | `collectors/views.py::refresh_all_views()` — sourced from wide_ads/wide_keywords |

### Lightweight views (from `ALL_VIEWS` + `_sub_campaign_views()`)
| View | Purpose |
|---|---|
| `v_channel_key_map` | Channel slug → display name mapping |
| `v_agent_activity_dashboard` | Agent activity heatmap (Nexa-Agent-Activity Hex) |
| `v_keyword_performance` | Keyword grain with QS, IS, leads |

### Dropped tables (do not recreate)

**Dropped 2026-06-09:**
hubspot_leads_daily, channel_roas_monthly, campaign_performance, campaign_performance_daily,
campaign_performance_monthly, disqualification_matrix, pipeline_funnel, lead_funnel_by_pipeline,
lead_utm_performance, v_lp_combined_weekly, v_lp_ga4_daily, v_lp_ga4_funnel_daily,
v_lp_performance_weekly, v_lp_weekly_summary, v_session_lead_match, v_signup_funnel_weekly,
v_website_funnel_daily

**Dropped 2026-06-15 (replaced by VIEWs from wide_ads — see reporting VIEWs section above):**
utm_paid_attribution_daily, channel_roas_daily

## Tech choices (and why)

- **BigQuery** over Postgres: free for our volume, native GA4/Sheets/Looker,
  partition pruning keeps query cost near zero.
- **Load jobs, not streaming inserts**: streaming buffer blocks DELETE for 90min,
  breaking idempotent re-runs. See `08_pitfalls.md`.
- **Hex over Streamlit**: Hex reads directly from BQ, survives Railway redeploys,
  no separate hosting cost, collaborative editing. Dashboards at:
  - Performance: `Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK`
  - Activity: `Nexa-Agent-Activity-033ArC9Xytz3SK6tPXwk9D`
- **Railway** for hosting: single dyno runs both schedulers + Flask; env vars
  managed via Railway dashboard or `scripts/sync_railway_env.py`.
- **Databox** for external BI dashboards: two active datasets pushed by `collectors/databox_pusher.py`.
  - **Daily Spend** (`199c5297`): channel-day grain. Fields: date (DATETIME), channel (STRING),
    spend/impressions/clicks/leads/sqls/cpl/cpql (NUMBER). Use SUM for volumes, AVG for ratios.
  - **All Grains** (`6158be78`): 4-grain unified dataset (campaign/adset/ad/keyword).
    Fields: date (DATETIME), grain/channel/utm_campaign (STRING),
    spend/impressions/clicks/leads/sqls/cpl/cpql/qual_rate_pct (NUMBER).
  Data source ID: `4983171` (PAK-linked "Qoyod BQ"). Account ID: `756469`.
  Superseded All Grains IDs: v3 `eff4621e` (bad schema wrapper → string types), v1/v2 all-string.
  Run backfill: `railway run python -c "from collectors.databox_pusher import run_push; run_push(days=365)"`
  Police check: `analysers/connector_tracker.py` SYSTEM_MONITORS includes both datasets.
