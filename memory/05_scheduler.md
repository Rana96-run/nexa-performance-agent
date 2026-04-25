# Scheduling & Runtime

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
