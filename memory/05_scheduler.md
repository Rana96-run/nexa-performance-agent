# Scheduling & Runtime

## Three-layer runtime (as of 2026-06-16)

```
Railway (ETL)   →   BigQuery   →   n8n cloud (analysis/Slack/Asana)
     ↑                                       ↑
 collectors                         Cowork (Drive/MCP writes for
 run every 6h                       remaining tasks — see below)
```

### What Railway still owns (non-negotiable — Python collectors)
- All ad-platform collectors (`google_ads`, `meta`, `snapchat`, `tiktok`, `microsoft_ads`, `linkedin`)
- `hubspot_leads_bq.py`, `hubspot_deals_bq.py`
- `gclid_clickview.py`, `ga4_bq.py`
- `databox_pusher.py` still exists but Railway no longer calls it — Databox push is n8n (see below)
- `create_views()` after every collect
- Health checks + Slack alerts for connector failures
- Keyword audit + ad pause/scale executors (still Python)
- Flask app: `/health`, `/activity`, `/api/refresh`, `/slack/events`

### What n8n now owns (analysis, Slack, Asana, Sheets)

| Workflow | n8n ID | Schedule | Nodes |
|---|---|---|---|
| Nexa · Master Performance Workflow | `T8icImtZFLYeCa7e` | Daily 05:00 UTC (08:00 Riyadh) | 84 |
| Nexa · Weekly Performance Review | `iNSdpXH7Rc9Lb8h8` | Sunday 05:00 UTC | 26 (2-agent chain) |
| Nexa · Monthly Performance Review | `0Zh45UoTtjjhRn8U` | 1st of month 05:00 UTC | 32 (3-agent chain) |
| Nexa · AI Content Agent | `yOD1l9n7qOfbpWfM` | Various (see below) | 13 |
| Nexa · Monitor Follow-up | `H6XSFlp1WOUPpgBF` | Daily 06:00 UTC | 11 |
| Nexa · Databox Sync | `7ZEROvwTg3UrGAP6` | Every 6h (`0 */6 * * *`) | 11 |

**⚠️ Required n8n $var for Databox Sync:** `DATABOX_TOKEN` must be set (PAK token, not push token). Dataset ID: `6158be78`.

**n8n credentials used:**
- BQ: `kE5RxM61mQkpV21N` (googleApi service account)
- Google Sheets OAuth2: `kBgcDkRIN5tMoACU`
- Asana: `iUYNax4N4UkcLiQB` (httpHeaderAuth)
- Slack: `YwdlGwXs943DQrfh` (httpHeaderAuth)

**n8n $vars used:** `BQ_PROJECT`, `BQ_DATASET`, `SLACK_CHANNEL_NOTIFY`, `SLACK_CHANNEL_APPROVALS`, `ASANA_WORKSPACE`, `ASANA_PROJECT_PAID` + all ad-platform account IDs.

**AI Content Agent schedules (all UTC):**
- `daily-ai-digest`: 05:02 UTC daily
- `competitor-post-poller`: 05:03 UTC daily
- `weekly-ai-digest`: 06:35 UTC Sunday
- `monthly-content-calendar`: 05:00 UTC 1st of month

### What Cowork still runs (MCP-dependent tasks)
These have no n8n equivalent (need Drive MCP / local credentials):

| Task | Schedule | Why Cowork |
|---|---|---|
| `morning-anomaly-sweep` | 07:00 Riyadh daily | Railway BQ + Slack direct |
| `daily-slack-audit` | 10:00 Riyadh daily | Slack MCP reaction reads |
| `keyword-autofix` | 08:05 Riyadh Sunday | Google Ads MCP write |
| `qoyod-social-listener` | Every 6h | Scraping + Sheets MCP |
| `weekly-competitor-monitor` | 09:08 Riyadh Sunday | Scraping + Slides MCP |
| `listening-slides-generator` | 10:04 Riyadh Sunday | Slides MCP |
| `daily-task-review` | 09:05 Riyadh daily | Asana MCP |
| `daily-git-review` | 23:00 Riyadh daily | Git + GitHub |

### Disabled Cowork tasks (now covered by n8n)
- `daily-ai-digest` → n8n AI Content Agent
- `competitor-post-poller` → n8n AI Content Agent
- `weekly-ai-digest` → n8n AI Content Agent
- `monthly-content-calendar` → n8n AI Content Agent
- `monday-review` → n8n Weekly Performance Review (21 nodes incl. LP Audit → Sheets + Asana)
- `monthly-review` → n8n Monthly Performance Review (25 nodes incl. Creative Report + LP Brief)

---

## Two independent runtimes

### 1. Reporting scheduler — `reporting_scheduler.py`

- **Cadence:** every 6h (00:00, 06:00, 12:00, 18:00 UTC → 03:00/09:00/15:00/21:00 Riyadh)
- **What it does:** runs all collectors in `incremental=True` (2-day lookback)
  then refreshes all views
- **Commands:**
  - `python reporting_scheduler.py once` — one pass, exit
  - `python reporting_scheduler.py loop` — forever, sleeps 6h between passes
  - `python reporting_scheduler.py backfill` — one pass in YTD mode
- **Collector order** (in `COLLECTORS` tuple): google_ads, meta, snapchat,
  meta_organic, youtube, linkedin, hubspot_leads, hubspot_deals
- **Fault tolerance:** a failing collector logs + continues; others still run;
  view refresh still happens at end

### 2. Operational agent — `main.py daily`

- **Cadence:** always-on, reactive
- **What it does:** Slack approvals, pause/scale watchers, threshold alarms,
  Asana tasks, HubSpot list building, landing page drafts
- **Never** touches the reporting cadence. A 6h collector run doesn't block
  agent activity.

## Deploying to Replit

**Recommended: two separate repls**
- Repl A: runs `reporting_scheduler.py loop` (Deploy → Reserved VM or Autoscale)
- Repl B: runs `main.py daily` (Deploy → Reserved VM, always-on)

Both repls share the same `.env` content (copy the secrets in Replit UI).

Alternative single-repl: branch on `RUN_MODE` env var (see `dashboard/README.md`).

## Incremental vs Backfill — when to use which

| Situation | Command |
|---|---|
| Regular 6h refresh | `incremental=True` (set in scheduler) |
| Missed a day due to outage | `python <collector>.py 3` (3-day lookback) |
| New integration's first run | `python <collector>.py` (YTD default) |
| Re-baseline after schema change | `python reporting_scheduler.py backfill` |

## Cost sanity

6h scheduler one pass scans ≤3 days of partitions. With clustering, query cost
is trivial (<$0.01/day). Load jobs are **free**. No streaming buffer used.

If the dashboard explodes BQ cost, check `@st.cache_data(ttl=3600)` is intact
on every page's `query()` call. Streamlit default is no cache → every user
refresh re-runs the SQL.
