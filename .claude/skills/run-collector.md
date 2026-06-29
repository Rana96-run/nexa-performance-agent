# Skill — Run a collector

Use when Amar says "re-pull X" / "backfill Y" / "run the scheduler".

## Decide the mode

| Situation | Command |
|---|---|
| Regular refresh (scheduled) | GitHub Actions collectors.yml (automatic, runs every 6h) |
| Re-pull last N days for one source | `railway run python collectors/<name>_bq.py <N>` |
| Full YTD backfill (one source) | `railway run python collectors/<name>_bq.py` |
| Full YTD rebuild (everything) | Trigger collectors.yml manually in GitHub Actions UI |

## Collector names

`google_ads_bq`, `meta_bq`, `snap_bq`, `meta_organic_bq`,
`linkedin_bq`, `hubspot_leads_bq`, `hubspot_deals_bq`

## Before running

1. Check `.env` has the creds (see `memory/02_credentials.md` for the
   per-source env keys).
2. If collector is organic/LinkedIn/YouTube, confirm OAuth has been run —
   refresh tokens don't expire but access tokens do.
3. For HubSpot: tokens never expire (Private App), just run it.

## After running

1. Verify row counts with the `bq-verify` skill (look at
   `memory/03_bigquery.md` for table names).
2. If `channel_roas_daily` looks sparse, likely cause is HubSpot leads
   YTD backfill not run — see `memory/09_open_tasks.md`.
3. If one collector fails, the scheduler keeps going. Failures print to
   stdout with `[collector-name] ERROR: ...`.

## Don't

- Don't rewrite the collector to use streaming inserts. Load jobs only
  (see pitfall in `memory/08_pitfalls.md`).
- Don't run multiple collectors for the same source in parallel — the
  MERGE can lock.
