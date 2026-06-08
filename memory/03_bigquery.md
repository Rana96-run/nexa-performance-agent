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

## Views (all `CREATE OR REPLACE`, rebuilt by `collectors/views.py`)

### Materialized tables (rematerialized every 6h via `materialize_heavy_views()`)

| Table | Purpose |
|---|---|
| `utm_paid_attribution_daily` | Campaign/adset/ad grain: adsets_daily spend + hubspot_leads_module_daily UTM attribution; includes UTM-proxy CTE for cases where utm_audience is only in HubSpot |
| `paid_channel_campaign_daily` | Campaign-level blended: spend + leads + deals + CPL/CPQL/ROAS |
| `channel_roas_daily` | Per (date, channel): spend + leads + deals + CPL/CPQL/ROAS + zones |
| `paid_channel_daily` | Channel-level daily rollup |
| `v_adset_performance` | Adset-level performance powered by utm_paid_attribution_daily |
| `v_ad_performance` | Ad-level performance powered by utm_paid_attribution_daily |

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
