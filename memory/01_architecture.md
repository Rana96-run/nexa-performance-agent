# Architecture

## Data flow

```
  Ad platforms            HubSpot             Organic APIs
  ┌───────────┐         ┌───────────┐        ┌───────────┐
  │ Google Ads│         │  Leads    │        │ FB/IG/YT/ │
  │   Meta    │         │  Deals    │        │ LinkedIn  │
  │ Snapchat  │         │ Pipelines │        │           │
  │  TikTok*  │         └─────┬─────┘        └─────┬─────┘
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
        │   channel_roas_daily/...  │
        └─────────────┬─────────────┘
                      │
                      ▼
        ┌───────────────────────────┐
        │ Streamlit (dashboard/*)   │  ← Replit-hosted
        │ Slack agent (agent/*)     │  ← local or Replit, always-on
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
| **Operational agent** | Slack approvals, pause/scale watchers, threshold alarms, Asana tasks, list building, landing page drafts | Always-on, reactive | `main.py daily` (local or Replit repl A) |
| **Reporting scheduler** | Refresh BQ tables + views for the dashboard | Every 6h | `reporting_scheduler.py loop` (local or Replit repl B) |

The 6h cadence is **only** for reporting. The operational agent doesn't wait.

## Repo layout

```
Nexa Performance Agent/
├── agent/                  # operational agent (Slack, decisions)
├── collectors/             # BQ collectors (one per data source)
│   ├── bq_writer.py        # shared: MERGE helper + schemas
│   ├── views.py            # creates channel_roas_*, funnel, etc
│   ├── google_ads_bq.py    # paid
│   ├── meta_bq.py          # paid
│   ├── snap_bq.py          # paid
│   ├── meta_organic_bq.py  # organic (FB+IG)
│   ├── youtube_bq.py       # organic
│   ├── linkedin_bq.py      # organic + ads if approved
│   ├── hubspot_leads_bq.py # lead module daily buckets
│   └── hubspot_deals_bq.py # deals daily buckets
├── dashboard/              # Streamlit app for Replit
├── scripts/                # one-off helpers (OAuth flows)
├── reporting_scheduler.py  # 6h reporting refresh orchestrator
├── main.py                 # operational agent entrypoint
├── config.py               # env-driven config for all collectors
├── memory/                 # ← this folder
├── .claude/skills/         # reusable skill recipes
└── md_files/               # long-form docs (Looker mapping, brand, etc)
```

## Tech choices (and why)

- **BigQuery** over Postgres: free for our volume, native GA4/Sheets/Looker,
  partition pruning keeps query cost near zero.
- **Load jobs, not streaming inserts**: streaming buffer blocks DELETE for 90min,
  breaking idempotent re-runs. See `08_pitfalls.md`.
- **Streamlit over Looker Studio**: full programmatic control, Qoyod branding,
  can embed agent actions (pause/scale buttons). Looker is read-only from code.
- **Replit** for hosting: user already pays for Core; avoids a separate VM.
