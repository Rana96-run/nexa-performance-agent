# BigQuery

Project: `angular-axle-492812-q4`  ·  Dataset: `qoyod_marketing`  ·  Location: `europe-west1`

All tables are **DAY-partitioned on `date`** and clustered on high-cardinality
filter fields. All writes go through `collectors/bq_writer.upsert_rows()`.

## Tables

| Table | Grain | Cluster on | Written by |
|---|---|---|---|
| `campaigns_daily` | (date, channel, campaign_id) | channel, campaign_id | google_ads_bq, meta_bq, snap_bq, linkedin_bq (ads) |
| `ads_daily` | (date, channel, ad_id) | channel, campaign_id, ad_id | (schema exists, collectors TBD) |
| `hubspot_leads_module_daily` | (date, qoyod_source, pipeline, stage, utm_campaign) | qoyod_source, pipeline | hubspot_leads_bq |
| `hubspot_deals_daily` | (date, qoyod_source, pipeline, stage_status, utm_campaign) | qoyod_source, pipeline, stage_status | hubspot_deals_bq |
| `organic_page_daily` | (date, channel) | channel | meta_organic_bq, youtube_bq, linkedin_bq (organic) |

## Databox view mapping (which view powers which Databox dataset)

| Databox dataset | BQ view | Notes |
|---|---|---|
| Campaign | `paid_channel_campaign_daily` | ID-first attribution — spend + leads + deals stay together through renames. **Not** `utm_paid_attribution_daily`. |
| Adset | `v_adset_performance` | Sourced from `wide_ads` (as of 2026-06-15) |
| Ad | `v_ad_performance` | Sourced from `wide_ads` (as of 2026-06-15) |
| Keyword | `v_keyword_performance` | Keyword grain |

**Do not attempt to use `utm_paid_attribution_daily` — it was DROPPED 2026-06-15.**
Campaign reporting uses `paid_channel_campaign_daily` (now a VIEW sourced from `wide_ads`)
which uses ID-first attribution and includes deals + ROAS.

Correct Databox SQL for each level (all include `utm_source`):

**Campaign:**
```sql
SELECT
  date, channel, campaign_name, status, utm_source,
  spend, leads, qualified AS sqls,
  cpl, cpql, qual_rate_pct AS qual_rate,
  -- New business (Sales Pipeline + Bookkeeping + Qflavours)
  new_biz_deals_won, new_biz_revenue_won, new_biz_amount_lost, new_biz_amount_open, new_biz_amount_total, new_biz_roas,
  -- All pipelines
  all_deals_won AS deals_won, revenue_won, amount_lost, amount_open, amount_total, roas
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_campaign_daily`
ORDER BY date DESC
```

**Adset:**
```sql
SELECT
  date, channel_name, utm_campaign AS campaign_name, adset_name, status, utm_source,
  SUM(spend) AS spend, SUM(leads) AS leads, SUM(leads_qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), SUM(leads)) AS cpl,
  SAFE_DIVIDE(SUM(spend), SUM(leads_qualified)) AS cpql,
  SAFE_DIVIDE(SUM(leads_qualified), SUM(leads)) AS qual_rate,
  -- New business
  SUM(new_biz_deals_won) AS new_biz_deals_won,
  SUM(new_biz_revenue_won) AS new_biz_revenue_won,
  SUM(new_biz_amount_lost) AS new_biz_amount_lost,
  SUM(new_biz_amount_open) AS new_biz_amount_open,
  SUM(new_biz_amount_total) AS new_biz_amount_total,
  SAFE_DIVIDE(SUM(new_biz_revenue_won), SUM(spend)) AS new_biz_roas,
  -- All pipelines
  SUM(revenue_won) AS revenue_won,
  SUM(amount_lost) AS amount_lost,
  SUM(amount_open) AS amount_open,
  SUM(amount_total) AS amount_total,
  SAFE_DIVIDE(SUM(revenue_won), SUM(spend)) AS roas
FROM `angular-axle-492812-q4.qoyod_marketing.v_adset_performance`
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY date DESC
```

**Ad:**
```sql
SELECT
  date, channel_name, utm_campaign AS campaign_name, utm_audience AS adset_name, ad_name, status, utm_source,
  SUM(spend) AS spend, SUM(leads) AS leads, SUM(leads_qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), SUM(leads)) AS cpl,
  SAFE_DIVIDE(SUM(spend), SUM(leads_qualified)) AS cpql,
  SAFE_DIVIDE(SUM(leads_qualified), SUM(leads)) AS qual_rate,
  -- New business
  SUM(new_biz_deals_won) AS new_biz_deals_won,
  SUM(new_biz_revenue_won) AS new_biz_revenue_won,
  SUM(new_biz_amount_lost) AS new_biz_amount_lost,
  SUM(new_biz_amount_open) AS new_biz_amount_open,
  SUM(new_biz_amount_total) AS new_biz_amount_total,
  SAFE_DIVIDE(SUM(new_biz_revenue_won), SUM(spend)) AS new_biz_roas,
  -- All pipelines
  SUM(revenue_won) AS revenue_won,
  SUM(amount_lost) AS amount_lost,
  SUM(amount_open) AS amount_open,
  SUM(amount_total) AS amount_total,
  SAFE_DIVIDE(SUM(revenue_won), SUM(spend)) AS roas
FROM `angular-axle-492812-q4.qoyod_marketing.v_ad_performance`
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY date DESC
```

**Keyword:**
```sql
SELECT
  date, channel_name, utm_campaign AS campaign_name, adgroup_name, utm_term AS keyword, status, utm_source,
  SUM(spend) AS spend, SUM(leads) AS leads, SUM(leads_qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), SUM(leads)) AS cpl,
  SAFE_DIVIDE(SUM(spend), SUM(leads_qualified)) AS cpql,
  SAFE_DIVIDE(SUM(leads_qualified), SUM(leads)) AS qual_rate,
  -- New business
  SUM(new_biz_deals_won) AS new_biz_deals_won,
  SUM(new_biz_revenue_won) AS new_biz_revenue_won,
  SUM(new_biz_amount_lost) AS new_biz_amount_lost,
  SUM(new_biz_amount_open) AS new_biz_amount_open,
  SUM(new_biz_amount_total) AS new_biz_amount_total,
  SAFE_DIVIDE(SUM(new_biz_revenue_won), SUM(spend)) AS new_biz_roas,
  -- All pipelines
  SUM(revenue_won) AS revenue_won,
  SUM(amount_lost) AS amount_lost,
  SUM(amount_open) AS amount_open,
  SUM(amount_total) AS amount_total,
  SAFE_DIVIDE(SUM(revenue_won), SUM(spend)) AS roas
FROM `angular-axle-492812-q4.qoyod_marketing.v_keyword_performance`
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY date DESC
```

⚠️ Column is `leads_qualified` NOT `sqls` in all views. `status` = ACTIVE / PAUSED from the platform — use to filter in Databox.
All deal amounts are in USD by deal createdate. New biz = Sales Pipeline + Bookkeeping + Qflavours. All pipelines = every HubSpot pipeline.

## Views (all `CREATE OR REPLACE VIEW`, rebuilt by `collectors/views.py`)

> **As of 2026-06-15, all reporting views source from `wide_ads`. See `docs/knowledge/bq-naming-convention.md` for the layer map.**
> `utm_paid_attribution_daily` and `channel_roas_daily` were DROPPED 2026-06-15 and are no longer live.

### Reporting VIEWs (sourced from wide_ads, refreshed every 6h via `refresh_all_views()`)

| View | Purpose |
|---|---|
| `paid_channel_campaign_daily` | Campaign-level blended: spend + leads + deals + CPL/CPQL/ROAS |
| `paid_channel_daily` | Channel-level daily rollup (replaces dropped `channel_roas_daily`) |
| `v_adset_performance` | Adset-level performance sourced from wide_ads |
| `v_ad_performance` | Ad-level performance sourced from wide_ads |

**Dropped 2026-06-15 (were physical BASE TABLEs in the old chain architecture):**
- `utm_paid_attribution_daily` — attribution spine replaced by wide_ads materialization
- `channel_roas_daily` — replaced by `paid_channel_daily` (wide_ads VIEW)
- `paid_channel_daily`, `paid_channel_campaign_daily`, `v_adset_performance`, `v_ad_performance` were BASE TABLEs; now VIEWs from wide_ads

### Lightweight views

| View | Purpose |
|---|---|
| `v_channel_key_map` | Lookup: ad-platform `channel` ↔ HubSpot `qoyod_source` label |
| `v_agent_activity_dashboard` | Agent activity log for the activity dashboard |
| `v_keyword_performance` | Keyword-level performance metrics |

## Schemas at a glance

### `campaigns_daily`
`date, channel, account_id, campaign_id, campaign_name, status, objective,
spend, impressions, clicks, ctr, leads, conversions, cpl, updated_at`

### `hubspot_leads_module_daily`
`date, qoyod_source, pipeline, stage, lead_utm_campaign, lead_utm_audience,
lead_utm_content, lead_utm_source, lead_utm_medium, lead_utm_term,
leads_total, leads_qualified, leads_disqualified, leads_open,
top_disq_reason, updated_at`

### `hubspot_deals_daily`
`date, qoyod_source, pipeline, stage_status (won|lost|open|unknown),
deal_utm_campaign, deal_utm_audience, deal_utm_content, deal_utm_source,
deal_utm_medium, deal_utm_term, deals_total, deals_won, deals_lost,
deals_open, amount_total, amount_won, amount_lost, amount_open,
avg_time_in_current_stage_ms, updated_at`

### `organic_page_daily`
Tall schema with per-platform columns (fb_*, ig_*, yt_*, li_*) so one row
per (date, channel). Null where a platform doesn't apply.

## Write pattern (idempotent)

`upsert_rows(table, rows, key_fields)` does:
1. Group rows by `date`
2. For each date, `DELETE FROM table WHERE date = @d AND scope_field IN UNNEST(@sv)`
   — scope_field is `key_fields[1]` (e.g. "channel")
3. `LOAD` via JSON → lands in partition immediately (NOT streaming buffer)

**Never use streaming inserts for collectors** — streaming data sits in a
90-min buffer that blocks subsequent DELETEs, breaking idempotency.

## Query cost discipline

- Always filter by `date >= '...'` — partition pruning saves >95% of scan
- Prefer `SUM()` + `GROUP BY` over window funcs when possible
- Use views for common joins so tiles don't repeat SQL
- `SAFE_DIVIDE()` not `/` — avoids div-by-zero errors

## Bootstrap from scratch

```bash
python collectors/bq_writer.py bootstrap   # creates dataset + base tables
python collectors/views.py                 # creates all views
```

## Reset a table (dev only!)

```python
from collectors.bq_writer import get_client
get_client().query("DROP TABLE `project.dataset.table`").result()
# next collector run will recreate it
```
