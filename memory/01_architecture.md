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
│   ├── views.py            # creates paid_channel_daily, v_lp_*, etc
│   ├── google_ads_bq.py    # campaign + adgroup + ad + keywords grain
│   ├── meta_bq.py          # campaign + adset + ad grain
│   ├── snap_bq.py          # campaign + adset + ad grain
│   ├── tiktok_bq.py        # campaign + adgroup + ad grain
│   ├── linkedin_bq.py      # campaign grain (token refresh needed)
│   ├── microsoft_ads_bq.py # blocked on OAuth (see open_tasks.md)
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
