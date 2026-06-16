# Infrastructure Guide — How Everything Connects

> **DEPRECATED (2026-06-16):** This guide describes the old Railway + Streamlit + `reporting_scheduler.py` + `main.py` architecture. All of those components were deleted on 2026-06-16. The current stack is: GitHub Actions (collectors) → BigQuery → n8n Cloud (analysis/Slack/Asana) + Hex/Databox (dashboards). Kept as historical record only — do not use as a setup guide.

## 1. The Three Layers

### GitHub — Code Storage
- Holds every Python file, SQL string, and config file
- Nothing runs here — it is a warehouse, not a server
- Full version history of every change ever made
- When a developer pushes code (`git push`), GitHub receives it and triggers Railway to redeploy
- Secrets (API keys, tokens) are NEVER stored here — they live in Railway only
- Repo: `github.com/Rana96-run/nexa-performance-agent`

### Railway — Execution (the running server)
- Takes the code from GitHub and runs it 24/7 on a Linux cloud server
- Auto-deploys every time `main` branch is pushed to GitHub
- Holds all secret environment variables: Meta token, Google Ads credentials, HubSpot token, BQ service account key, Slack bot token, Asana token
- Two permanent processes always running:
  | Process | Entry file | Cadence | What it does |
  |---|---|---|---|
  | Reporting scheduler | `reporting_scheduler.py` | Every 6h | Fires all collectors (Meta/Google/HubSpot → BQ), rebuilds `wide_ads` + `wide_keywords`, refreshes all views |
  | Operational agent | `main.py` | Nightly | Ad audits, pause/scale recommendations, keyword reviews, posts to Slack #approvals |
- Health endpoint: `https://nexa-web-production-6a6b.up.railway.app/health`
- Local development: use `railway run python <script>` — Railway injects all env vars so scripts work locally without hardcoding secrets

### Your machine (Windows) — Editing only
- `D:\Nexa Performance Agent\` is the working copy
- Edit files here → `git push` → GitHub → Railway auto-deploys
- Nothing production runs here

---

## 2. The Full Chain — How Code Becomes Data

```
Developer edits Python on Windows machine
        ↓  git add / git commit / git push
GitHub stores the new code + triggers Railway
        ↓  Railway auto-pulls and redeploys (takes ~60s)
Railway runs reporting_scheduler.py every 6h:
        ↓  calls Meta Ads API → writes to campaigns_daily (BQ)
        ↓  calls Google Ads API → writes to campaigns_daily, keywords_daily (BQ)
        ↓  calls HubSpot API → writes to hubspot_leads_individual (BQ)
        ↓  calls HubSpot API → writes to hubspot_deals_individual (BQ)
        ↓  runs materialize_heavy_views() → rebuilds wide_ads + wide_keywords (BQ)
        ↓  runs refresh_all_views() → refreshes all 3 BQ views
Railway runs main.py every night:
        ↓  queries wide_ads → computes CPQL / pause / scale recommendations
        ↓  posts to Slack #approvals
        ↓  creates Asana tasks
n8n (cloud, separate from Railway) runs 3 workflows on schedule:
        ↓  queries wide_ads in BigQuery
        ↓  posts performance summaries to Slack
Hex (cloud BI tool) queries BigQuery on demand:
        ↓  reads wide_ads, hubspot_leads_module_daily, hubspot_deals_daily
        ↓  renders dashboard for the team
```

---

## 3. BigQuery — How It's Connected and How Tables Are Updated

### Connection
- Railway connects to BQ using a **service account key** stored as the `GOOGLE_APPLICATION_CREDENTIALS` env var in Railway
- Locally: the key file lives at `secrets/bigquery-key.json` (gitignored — never committed)
- The Python library used: `google-cloud-bigquery` — all writes go through `collectors/bq_writer.py`
- Write method: **NDJSON file load** (`load_table_from_file(BytesIO(ndjson_bytes))`) — never streaming inserts (streaming causes duplicates and can't be merged)
- All writes are **UPSERT** (merge by key) — re-running a collector never creates duplicate rows

### How each table gets updated

| Table | Updated by | How often | Method | Key used for dedup |
|---|---|---|---|---|
| `campaigns_daily` | Each platform collector (Meta, Google, Snap, TikTok, LinkedIn, Microsoft) | Every 6h | Full 30-day window re-pull + UPSERT | `date + channel + campaign_id` |
| `ads_daily` | Meta, Google, TikTok collectors | Every 6h | Full 30-day window re-pull + UPSERT | `date + channel + ad_id` |
| `keywords_daily` | Google Ads collector | Every 6h | Full 30-day window re-pull + UPSERT | `date + channel + keyword_id` |
| `hubspot_leads_individual` | HubSpot leads collector | Every 6h | Full window from 2025-01-01 re-pull + UPSERT | `hs_object_id` |
| `hubspot_deals_individual` | HubSpot deals collector | Every 6h | Full window from 2025-01-01 re-pull + UPSERT | `hs_object_id` |
| `wide_ads` | `materialize_heavy_views()` in `collectors/views.py` | Every 6h, after all collectors finish | DROP + full rebuild from store tables | n/a (full rebuild) |
| `wide_keywords` | Same | Every 6h | DROP + full rebuild | n/a |
| `hubspot_leads_module_daily` | `refresh_all_views()` | Every 6h | `CREATE OR REPLACE VIEW` (no data stored — live query) | n/a (VIEW) |
| `hubspot_deals_daily` | `refresh_all_views()` | Every 6h | `CREATE OR REPLACE VIEW` | n/a (VIEW) |
| `v_keyword_performance` | `refresh_all_views()` | Every 6h | `CREATE OR REPLACE VIEW` | n/a (VIEW) |
| `agent_activity_log` | `main.py`, all schedulers | On every agent action | Append-only | n/a |
| `connector_health_log` | `connector_tracker.py` | Every 6h | Append-only | n/a |
| `asana_task_status` | `asana_sync.py` | Nightly | UPSERT | `asana_task_id` |
| `ga4_sessions_daily` | `ga4_bq.py` | Every 6h | UPSERT | `date + page_path + session_source` |
| `organic_page_daily` | `meta_organic_bq.py`, `youtube_bq.py` | Every 6h | UPSERT | `date + channel + page_url` |

### Why UPSERT and not INSERT
Each collector pulls the last 30 days on every run (not just yesterday). This means if Meta retroactively adjusts yesterday's spend (which they do — typically within 48h), the corrected number overwrites the stale one in BQ. INSERT would accumulate duplicates. UPSERT by stable key means re-running is always safe.

### Why wide_ads is a full rebuild (not UPSERT)
`wide_ads` joins spend (campaigns_daily/ads_daily) to leads (hubspot_leads_individual) to deals (hubspot_deals_individual) using id-first attribution. If any source table changes, the join result changes. It's faster and safer to DROP the table and rebuild from scratch every 6h than to track which rows changed across 3 joined sources.

---

## 4. Why Python Can't Be Replaced by n8n (or any no-code tool)

| Responsibility | Why Python is required |
|---|---|
| OAuth token refresh (LinkedIn, TikTok, YouTube) | Multi-step handshake — request refresh token → store new token in BQ → use in next call. Stateful, needs BQ write mid-flow |
| BQ NDJSON upserts | n8n has no MERGE node. Streaming inserts cause duplicates that can't be corrected |
| Google Ads API pagination | 10,000-row page limit, cursor-based. Google Ads Python SDK handles this; n8n HTTP node doesn't |
| Keyword policy enforcement | `keyword_policy.py` — 200+ bilingual Arabic+English rules, pattern matching, brand/competitor/junk buckets |
| Ad pause/scale execution | Requires platform SDK call + approval gate check + BQ audit log write in one atomic sequence |
| HubSpot CDC sync | Cursor-based change detection across 18 months — upsert by stable `hs_object_id` |
| Forecasting + period compare | Multi-step Python math — not expressible in SQL alone |
| Connector health auto-heal | Detects stale data → re-triggers the right collector → logs the retry |

**What DID move to n8n:** The 3 performance summary workflows (Master Daily, Weekly, Monthly) — these are pure "query BQ → format → post to Slack" with no Python logic required.

---

## 5. Quick Reference — Where to Find Things

| Thing | Location |
|---|---|
| All Python source code | `D:\Nexa Performance Agent\` (local) = GitHub repo = Railway server |
| Secret API keys | Railway dashboard → Environment Variables (never in code) |
| Local secret key file | `secrets/bigquery-key.json` (gitignored) |
| BQ dataset | `angular-axle-492812-q4.qoyod_marketing` |
| BQ table structure | `docs/knowledge/bq-table-guide.md` |
| n8n workflows | `https://qoyod.app.n8n.cloud` |
| Hex dashboard | Hex workspace (query wide_ads, hubspot_leads_module_daily) |
| Hex SQL changes needed | `hex/CHANGES_NEEDED.md` |
| Tool stack overview | `docs/knowledge/stack-overview.md` |
| Open tasks | `memory/09_open_tasks.md` |
| Architecture diagram | `memory/01_architecture.md` |
