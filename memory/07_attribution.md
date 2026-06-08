# Attribution Model

**Rule:** channel totals use HubSpot's `qoyod_source` property.
Campaign/adset/ad totals use UTMs. They don't always reconcile — that gap
is a real signal, not a bug.

## Hierarchy

| Grain | HubSpot field | Ad-platform equivalent |
|---|---|---|
| Channel | `qoyod_source` | `channel` (google_ads, meta, …) |
| Campaign | `lead_utm_campaign` / `deal_utm_campaign` | `campaign_name` |
| Ad group / Adset | `lead_utm_audience` / `deal_utm_audience` | `adset_name` / `ad_group_name` |
| Ad | `lead_utm_content` / `deal_utm_content` | `ad_name` |

## Key insight (user-stated)

> "The channel total number of leads comes from qoyod_source, but each
> campaign by UTM — and the UTMs summed may NOT equal the channel total
> because some leads attribute to the channel via click ID (gclid, fbclid)
> but have no campaign name in UTM."

### Implication for views and charts

- **Channel KPI tile** (e.g. "Google Ads: 420 leads this month"): count from
  `qoyod_source = 'Google Ads'`
- **Campaign breakdown table:** count grouped by `utm_campaign`
- **Reconciliation row:** `leads_unattributed_to_campaign = channel_total - sum(utm_breakdown)` — show this as an explicit "(no UTM)" row so users see the
  gap, not hide it

## Join strategy — try BOTH (user directive)

### Strategy A: exact (normalized) match
```sql
LOWER(TRIM(hs.lead_utm_campaign)) = LOWER(TRIM(ga.campaign_name))
```

### Strategy B: slugified match
Normalize both sides with the same slugify rule: lowercase, collapse whitespace/
dashes/underscores to single `_`, strip non-ASCII word chars except `_`.

```sql
REGEXP_REPLACE(
  REGEXP_REPLACE(LOWER(TRIM(x)), r'[^a-z0-9]+', '_'),
  r'^_+|_+$', ''
) AS slug
```
Then `hs_slug = ad_slug`.

**Pattern:** use COALESCE(exact_match, slug_match) and record which strategy
hit in a `match_method` column for debugging.

## The "unattributed" bucket

For every channel, emit a row where:
```
utm_campaign = '__no_utm__'
leads = channel_total - sum(utm_campaign_breakdown)
```

This is shown in dashboards as "(no UTM — click-ID attribution only)" so
users understand the number, not wonder why tables don't sum to totals.

## Current state (implemented)

- HubSpot collectors capture `lead_utm_audience` and `lead_utm_content` as
  aggregation keys in `hubspot_leads_module_daily`.
- `channel_roas_daily` joins HubSpot ↔ paid by `qoyod_source ↔ channel` at
  channel grain.
- **`utm_paid_attribution_daily` is live** — defined as
  `UTM_PAID_ATTRIBUTION_VIEW_SQL` in `collectors/bq_writer.py`. It joins
  `adsets_daily` spend with `hubspot_leads_module_daily` UTM attribution at
  campaign/adset/ad grain, including a UTM-proxy CTE for cases where
  `utm_audience` is only in HubSpot. Rematerialized every 6h via
  `materialize_heavy_views()` in `collectors/views.py`. Powers
  `v_adset_performance` and `v_ad_performance`.

## Sanity check queries

### Channel total (authoritative)
```sql
SELECT qoyod_source, COUNT(*) AS leads
FROM hubspot_leads_module_daily
WHERE date BETWEEN @start AND @end
GROUP BY 1
```

### UTM breakdown within a channel
```sql
SELECT lead_utm_campaign, COUNT(*) AS leads
FROM hubspot_leads_module_daily
WHERE qoyod_source = 'Google Ads' AND date BETWEEN @start AND @end
GROUP BY 1 ORDER BY leads DESC
```

### The gap (should be published as a metric, not hidden)
```sql
SELECT
  (SELECT SUM(leads_total) FROM ... WHERE qoyod_source='Google Ads') -
  (SELECT SUM(leads_total) FROM ... WHERE qoyod_source='Google Ads'
                                      AND lead_utm_campaign IS NOT NULL)
  AS leads_with_no_utm
```
