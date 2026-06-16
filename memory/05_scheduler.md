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
- `gclid_clickview.py`, `ga4_bq.py`, `databox_pusher.py`
- `create_views()` after every collect
- Health checks + Slack alerts for connector failures
- Keyword audit + ad pause/scale executors (still Python)
- Flask app: `/health`, `/activity`, `/api/refresh`, `/slack/events`

### What n8n now owns (analysis, Slack, Asana, Sheets)

| Workflow | n8n ID | Schedule | Nodes |
|---|---|---|---|
| Nexa · Master Performance Workflow | `T8icImtZFLYeCa7e` | Daily 08:00 Riyadh (05:00 UTC) | ~50+ |
| Nexa · Weekly Performance Review | `iNSdpXH7Rc9Lb8h8` | Sunday 08:00 Riyadh (05:00 UTC) | 21 |
| Nexa · Monthly Performance Review | `0Zh45UoTtjjhRn8U` | 1st of month 08:00 Riyadh | 25 |
| Nexa · AI Content Agent | `yOD1l9n7qOfbpWfM` | Various (see below) | 13 |

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
| `daily-slack-audit` | 10:00 Riyadh daily | 