# Skill — Verify BigQuery state

Use after a collector run, or when the dashboard "looks off".

## NON-NEGOTIABLE — refresh keys + schemas before every verification

**Before you do any dedupe / freshness / reconciliation check:**

1. **Read the live table schema** (`client.get_table(...).schema` or
   `INFORMATION_SCHEMA.COLUMNS`) — not your memory of what columns exist.
   Schemas evolve (new metrics columns, renamed fields, dropped legacy
   columns). Memory is stale by definition.

2. **Read the collector's actual `key_fields=[...]`** before checking for
   duplicates. The full uniqueness key is what the upsert uses, not a
   subset. Subsets produce false-positive "duplicates" that waste time.

3. **Re-read `memory/01_architecture.md`** for table names, view names,
   and recent migrations — these change. The last creator/closer date
   in the doc footer tells you if it's worth re-reading.

4. **Pull current values for "right answer"** from the source of truth
   (HubSpot API, ad platform) — don't compare BQ to a cached HubSpot UI
   screenshot or yesterday's snapshot.

This rule exists because on 2026-05-13:
  - I ran a leads dedupe with a partial key (missed `lead_utm_source` +
    `lead_utm_medium`) and reported "1.073x duplicates" — false alarm,
    full key showed 1.000x clean.
  - I tried to read `paid_channel_daily.leads` when the column had been
    renamed to `leads_total` — column didn't exist, error.
  - I asked the user to verify HubSpot numbers manually instead of
    pulling them via API myself — they had to push back.

**Checklist before any "verify" command:**

- [ ] `client.get_table(table).schema` → know current columns
- [ ] `grep "key_fields" collectors/*.py` for the table → know real upsert key
- [ ] Read `memory/01_architecture.md` if it's been > 1 day since last read
- [ ] Pull HubSpot/platform side via API (not user screenshot) for compare


## Quick row-count by table

```sql
SELECT table_name, row_count, TIMESTAMP_MILLIS(last_modified_time) AS last_modified
FROM `${BQ_PROJECT_ID}.${BQ_DATASET}.__TABLES__`
ORDER BY last_modified DESC
```

## Per-day freshness check

```sql
SELECT channel, MAX(date) AS latest_day, COUNT(*) AS rows_7d
FROM `${BQ_PROJECT_ID}.${BQ_DATASET}.campaigns_daily`
WHERE date >= CURRENT_DATE() - 7
GROUP BY channel ORDER BY latest_day DESC
```

Do the same for `organic_page_daily`, `hubspot_leads_module_daily`,
`hubspot_deals_daily`.

## Channel_roas_daily sanity

```sql
SELECT channel, SUM(spend) AS spend, SUM(leads_total) AS leads,
       SAFE_DIVIDE(SUM(spend), SUM(leads_total)) AS cpl
FROM `${BQ_PROJECT_ID}.${BQ_DATASET}.channel_roas_daily`
WHERE date >= CURRENT_DATE() - 30
GROUP BY channel
```

If a channel shows `leads=0` and spend>0 → attribution join is broken
(HubSpot data missing or `qoyod_source` not matching CHANNEL_MAP).

## Partition / clustering (don't remove)

Every `_daily` table must be:
- `PARTITION BY date`
- `CLUSTER BY channel` (where applicable)

Check via `INFORMATION_SCHEMA.PARTITIONS`.

## Common failure modes

- Empty recent partition → collector silently returned 0 rows (network or
  API deprecation; check stdout log)
- Old data still showing → dashboard cache; hit "Force refresh cache"
- Rows present but not in view → view not rebuilt; run
  `python -c "from collectors.views import rebuild_all; rebuild_all()"`
