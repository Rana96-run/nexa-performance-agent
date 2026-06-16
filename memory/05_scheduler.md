# Scheduling & Runtime

## Three-layer runtime (as of 2026-06-17)

```
GitHub Actions (ETL)   →   BigQuery   →   n8n cloud (analysis/Slack/Asana)
  collectors every 6h                              ↑
  (00/06/12/18 UTC)              Cowork (Drive/MCP writes for
                                 remaining tasks — see below)
```

**Railway: DEPRECATED.** Still live pending GitHub Secrets migration + user shutdown decision. No schedulers or analysis run on Railway anymore.

### What GitHub Actions owns (Python collectors — BQ writes only)

`.github/workflows/collectors.yml` runs every 6h (00/06/12/18 UTC):
- All ad-platform collectors (`google_ads`, `meta`, `snapchat`, `tiktok`, `microsoft_ads`, `linkedin`)
- `hubspot_leads_bq.py`, `hubspot_deals_bq.py`
- `ga4_bq.py`
- `databox_pusher.py` exists for manual backfill only — live Databox push is n8n Databox Sync
- `create_views()` runs after every collector pass

`.github/workflows/linkedin_token_refresh.yml` — daily 02:00 UTC LinkedIn token refresh.

### What n8n now owns (analysis, Slack, Asana, Sheets)

| Workflow | n8n ID | Schedule | Nodes |
|---|---|---|---|
| Nexa · Master Performance Workflow | `T8icImtZFLYeCa7e` | Daily 05:00 UTC (08:00 Riyadh) | 84 |
| Nexa · Weekly Performance Review | `iNSdpXH7Rc9Lb8h8` | Sunday 05:00 UTC | 26 (2-agent chain) |
| Nexa · Monthly Performance Review | `0Zh45UoTtjjhRn8U` | 1st of month 05:00 UTC | 32 (3-agent chain) |
| Nexa · AI Content Agent | `yOD1l9n7qOfbpWfM` | Various (see below) | 13 |
| Nexa · Monitor Follow-up | `H6XSFlp1WOUPpgBF` | Daily 06:00 UTC | 11 |
| Nexa · Databox Sync | `7ZEROvwTg3UrGAP6` | Every 6h (`0 */6 * * *`) | 11 |
| Nexa · Data Collection | `jOnJxdpdaO3Vbi0B` | Every 6h | 52 |
| Nexa · Approval Listener | `5Acqsbxsk0XQ5k9e` | Webhook (always-on) | — |
| Nexa · QA Gate | `ug3niLKrjPfO9Iz7` | Sub-flow (called by Master) | — |

**⚠️ Required n8n $var for Databox Sync:** `DATABOX_TOKEN` must be set (PAK token, not push token). Dataset ID: `6158be78`.

**Data Collection workflow (`jOnJxdpdaO3Vbi0B`):** 52 nodes, every 6h. Runs all platform collectors + BQ reconciliation + freshness check. Alerts `#data-health` if any channel stale >1 day.

**Approval Listener (`5Acqsbxsk0XQ5k9e`):** Slack webhook at `https://qoyod.app.n8n.cloud/webhook/slack-approval`. Receives `reaction_added` events, resumes waiting executions from the Master workflow's approval gate. Requires Slack App Event Subscriptions configured (event: `reaction_added`, URL: above).

**n8n credentials used:**
- BQ: googleApi service account (see n8n Credentials)
- Google Sheets OAuth2 (see n8n Credentials)
- Asana: httpHeaderAuth (see n8n Credentials)
- Slack: httpHeaderAuth (see n8n Credentials)

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

## DELETED runtimes (do not reference)

`reporting_scheduler.py`, `operational_scheduler.py`, `main.py`, `app_server.py` — all deleted 2026-06-16.
- Use GitHub Actions (`.github/workflows/collectors.yml`) for collector cadence.
- Use n8n for all analysis, Slack, Asana, approval gates.
- Railway is deprecated (still live, pending shutdown).

## Incremental vs Backfill — when to use which

| Situation | Command |
|---|---|
| Regular 6h refresh | `incremental=True` (set in collector via GitHub Actions) |
| Missed a day due to outage | `python <collector>.py 3` (3-day lookback) |
| New integration's first run | `python <collector>.py` (YTD default) |
| Re-baseline after schema change | Run the relevant collector directly: `python collectors/<name>_bq.py` (`reporting_scheduler.py` was deleted 2026-06-16) |

## Cost sanity

6h scheduler one pass scans ≤3 days of partitions. With clustering, query cost
is trivial (<$0.01/day). Load jobs are **free**. No streaming buffer used.

If BQ query costs spike, check the Hex notebook SQL — Hex caches results per cell but re-runs on refresh. Databox pulls from BQ on its own schedule (every 6h via n8n Databox Sync). Streamlit/`@st.cache_data` is no longer relevant — Streamlit was deleted 2026-06-16.
