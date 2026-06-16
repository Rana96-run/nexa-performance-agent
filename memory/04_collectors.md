# Collectors

Every collector exposes the **same base signature**:
```python
collect_and_write(days: int = None, incremental: bool = False) -> int
```

HubSpot collectors add an optional `start_date` param:
```python
# hubspot_leads_bq.py / hubspot_deals_bq.py
collect_and_write(days: int = None, start_date: date = None,
                  incremental: bool = False) -> int
```

Modes:
- `incremental=True` → last 2 days (for scheduled 6h runs; light)
- `days=N` → last N days (targeted re-pull)
- `start_date=<date>` (HubSpot only) → explicit window start; combine with
  `days` or leave `days=None` to run start→today
- neither → **YTD** (Jan 1 of current year; used for initial backfills)

Returns number of rows written.

## Paid collectors

### `google_ads_bq.py`
- Reads `GOOGLE_ADS_CUSTOMER_IDS` (comma-sep, dashes stripped)
- GAQL query on `campaign` resource, daily segment
- Writes `campaigns_daily` with `channel='google_ads'`
- Cost is in micros (`cost_micros / 1_000_000`)

### `meta_bq.py`
- Loops `META_AD_ACCOUNT_1` + `_2`
- `level=campaign, time_increment=1` insights call
- Extracts `leads` from `actions` where `action_type=='lead'`

### `snap_bq.py`
- Refreshes access token every run (`_refresh_access_token()`)
- Detects account native currency in `_get_account()`; spend is converted to USD via `collectors/currency.py` (peg 3.75 SAR/USD, preserved as `spend_native` / `currency_native`)
- Lists campaigns per account, then hits `/campaigns/{id}/stats` per campaign
- Spend in **micro-currency** (`/ 1_000_000`)
- Pulls the broader `SNAP_STATS_FIELDS` set; on field-validation error falls
  back to `SNAP_STATS_FIELDS_SAFE` automatically
- `leads` = `conversion_sign_ups` (our lead definition)
- `conversions` = sum of all Snap conversion events (reconciles with Snap UI)
- `conversion_lead` / `total_conversions` are NOT valid field names

## Organic collectors

### `meta_organic_bq.py`
- FB page metrics: `page_impressions_unique`, `page_post_engagements`,
  `page_follows`, `page_daily_follows_unique`, `page_views_total`
  (Nov-2025 survivors only — see 08_pitfalls.md)
- IG: `reach` as daily series; other metrics (profile_views, website_clicks,
  accounts_engaged, total_interactions) come as `metric_type=total_value`
  period-aggregates attributed to the end_date row
- Writes `organic_page_daily` with `channel='meta_organic'`

### `youtube_bq.py`
- Uses YouTube Analytics API for daily series + Data API v3 for subscriber snapshot
- Needs `YT_REFRESH_TOKEN` + `YT_CHANNEL_ID`
- Writes `organic_page_daily` with `channel='youtube'`

### `linkedin_bq.py`
- Organic page share statistics via `organizationalEntityShareStatistics`
- Follower count via `networkSizes/{urn}`
- If `LI_AD_ACCOUNT_URN` set → also pulls `adAnalytics` → `campaigns_daily`
- Writes `organic_page_daily` with `channel='linkedin'`
- **Token hygiene:** `LI_ACCESS_TOKEN` expires in 60d. Run
  `python scripts/linkedin_refresh.py --write-env` before expiry; the helper
  uses the refresh_token grant and rewrites `.env` in place.

## HubSpot collectors

### `hubspot_leads_bq.py`
- Object type `0-136` (Lead module, separate from Contacts)
- HubSpot Search API **10k hard cap** → walks 7-day windows
- Buckets by (date, qoyod_source, pipeline, stage, utm_*)
- Pipeline/stage names resolved via `/crm/v3/pipelines/0-136` (cached in module)
- Qualification logic:
  - qualified = stage label contains "qualified" and not "dis"
  - disqualified = stage label contains "disqualified"

### `hubspot_deals_bq.py`
- Standard deals object
- **Won/lost classification** by `stage.probability`:
  - 1.0 → won
  - 0.0 → lost
  - 0 < p < 1 → open
  - null → label-based fallback ("won" / "lost" / else open)
- Same 7-day window walking for the 10k cap

## Common patterns

### Windowed pagination (HubSpot 10k cap)
```python
window = timedelta(days=7)
while win_start < end_dt:
    win_end = min(win_start + window, end_dt)
    after = None
    while True:
        data = _search(... since=win_start, until=win_end, after=after ...)
        # process
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after or pages >= 500: break
    win_start = win_end
```

### Graceful skip when creds missing
```python
if not os.getenv("YT_REFRESH_TOKEN"):
    print("[yt] missing creds — skipping")
    return 0
```

## Adding a new collector — 5-step recipe

1. Add `.env` keys to `02_credentials.md` first
2. Create `collectors/<name>_bq.py` with `collect_and_write(days=None, incremental=False)`
3. Table schema: reuse `campaigns_daily` if paid; else create a `_ensure_table()`
   helper that declares schema + partitioning + clustering
4. Add a step to `.github/workflows/collectors.yml` under the jobs section (`reporting_scheduler.py` was deleted 2026-06-16)
5. Add a view rebuild to `collectors/views.py` if the new table needs to
   feed `channel_roas_daily` etc.
