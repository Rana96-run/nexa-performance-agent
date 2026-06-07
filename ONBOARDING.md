# Qoyod Performance Agent — Onboarding Guide

## What is this?

A daily AI agent that monitors Qoyod's paid media performance across Google Ads, Meta, Snapchat, TikTok, Microsoft Ads, and LinkedIn. It pulls data into BigQuery, analyzes CPQL/CPL/ROAS, creates Asana tasks, and posts a nightly digest to Slack for human approval before executing any changes.

---

## Key URLs

| Resource | URL |
|---|---|
| Live Dashboard | https://nexa-web-production-6a6b.up.railway.app/activity |
| Railway Deploys | https://railway.app (ask Amar for access) |
| Asana Project | Linked in config via `ASANA_PROJECT_ID` |
| Slack Channels | `#approvals` (actions), `#notifications` (alerts) |

---

## Architecture in 60 seconds

```
Ad Platforms → Collectors → BigQuery → Analysers → Slack #approvals
                                  ↓
                           Reports (Flask) → /activity dashboard
```

- **Collectors** (`collectors/`) — pull raw data from each platform API, write to BQ via `load_table_from_file` (never streaming inserts)
- **BigQuery** (`BQ_PROJECT_ID.BQ_DATASET`) — the single source of truth; materialized views pre-join spend + leads + deals
- **Analysers** (`analysers/`) — CPQL/CPL health, spike detection, period comparisons, forecasting
- **Executors** (`executors/`) — scale/pause/keyword actions, always approval-gated
- **Scheduler** (`operational_scheduler.py`) — runs everything on cron via Railway
- **Self-healer** (`monitors/self_healer.py`) — daily 09:30 Riyadh, detects and fixes failures silently

---

## Daily schedule (Riyadh time)

| Time | What runs |
|---|---|
| 05:00 | Action sheet → Google Sheets |
| 06:30 | QA gate self-test |
| 07:00 | Compliance monitor |
| 08:00 | **Main nightly** — collectors, analysis, Asana tasks, Slack digest |
| 09:00 | HubSpot full mirror + workday spend refresh |
| 09:30 | **Self-healer** — stale views, failed collectors, dashboard 500s |
| 09–17 | Hourly health checks |
| 11/13/15 | Workday spend refresh (closes same-day platform adjustment gap) |
| 15:00 | HubSpot midday mirror |
| 18:00 | Compliance recheck |
| 20:00 | Second BQ refresh |
| 22:00 | HubSpot end-of-day mirror |

---

## KPI rules (non-negotiable)

- **Cost** → always from `campaigns_daily.spend` (USD, never SAR)
- **Leads/SQLs** → always from `hubspot_leads_module_daily` (never `hubspot_leads_daily`)
- **Evaluation order** → CPQL first, then CPL
- **Minimum decision window** → 14 days
- **Deal amounts in BQ** → USD already (collector converts at write time, do NOT divide by 3.75)

---

## Approval flow

Every scale/pause action goes through Slack `#approvals`:
1. Nightly digest is posted with all candidates
2. ✅ reaction = execute all scale + pause items
3. ❌ reaction = skip all
4. Review items (optimize/junk/drilldown) are Asana-only — no execution

**The agent never auto-executes without a ✅.**

---

## Campaign naming convention

`{Channel}_{Type}_{Language}_{Product}_{Audience}`

Valid audiences: `Interests` | `Lookalike` | `Retargeting` | `Broad`  
"Prospecting" is **invalid** — use `Interests` or `Lookalike` instead.

---

## Running locally

All secrets are in Railway. Use `railway run python <script>` for local runs — Railway injects all env vars. Never hardcode secrets.

```bash
# Check BQ freshness
railway run python scripts/check_freshness.py

# Run a collector manually
railway run python -c "from collectors.meta_bq import collect_and_write; collect_and_write()"

# Run the self-healer
railway run python -m monitors.self_healer
```

---

## Key memory files

| File | What's in it |
|---|---|
| `memory/CRITICAL_KPI_RULES.md` | Non-negotiable KPI rules — read every session |
| `memory/01_architecture.md` | BQ schema, table names, view names |
| `memory/08_pitfalls.md` | Known API traps and bugs (auto-updated by self-healer) |
| `memory/09_open_tasks.md` | Pending and in-progress work across sessions |
| `docs/PLAYBOOK.md` | Who we are, audience, voice, market rules |

---

## Self-healing infrastructure

`monitors/self_healer.py` runs daily at 09:30 Riyadh and fixes:

1. **Stale views** — if `paid_channel_daily` is >1 day behind, rebuilds all materialized views
2. **Failed collectors** — retries any collector that failed in the last 24h
3. **Dashboard 500s** — clears the HTML cache so the next `/activity` load renders fresh
4. **Stuck approvals** — re-posts reminder if a pending approval is >72h unresolved
5. **Memory auto-update** — if an error fires on 3+ separate days in 7, appends it to `memory/08_pitfalls.md` and commits to git

All actions logged to `agent_activity_log` (action=`self_heal`) — visible in the Activity Dashboard.
