# Wide-table redesign — "be our own Funnel" (2026-06-15)

## Goal
Hold all channel data in BigQuery, full history **from 2025-01-01**, refreshed
**4×/day**, where each sync re-reads the window and updates whatever changed
(spend, lead stage, qoyod_source, deal stage/amount). No incremental tail that
can silently fall behind. Result: any HubSpot/ad-platform filter + any date
range reproduces exactly in BQ — nothing dropped, no double-count.

This replaces the fragile "group-B" materialized chain that caused repeated
data drops (incremental windows missing backdated rows; rename/join-chain
nulls).

## Why we depended on Funnel
Funnel's one guarantee: all channel data, full history, one place, kept current
without babysitting a pipeline. Our own BQ kept failing at exactly that. This
design brings that guarantee in-house and adds what Funnel can't reach
(record-level HubSpot lead/deal detail).

## Final table set — 6 stores + reporting views

**Store (the truth):**
| Table | Grain | Status |
|---|---|---|
| `campaigns_daily` | date × channel × campaign | exists |
| `adsets_daily` | + adset | exists |
| `ads_daily` | + ad | exists |
| `keywords_daily` | + adgroup × keyword (Google + Microsoft) | exists |
| `hubspot_leads_individual` | one row per lead (all stages/UTM/source) | exists |
| `hubspot_deals_individual` | one row per deal (stage, amount, pipeline, source, UTM, sync IDs) | **built 2026-06-15** |

**Reporting:** thin views join spend ↔ leads ↔ deals (e.g. `wide_ads` ad-grain
hierarchy + `wide_keywords`). Channel/campaign/adset rollups are `GROUP BY`s
over the ad-grain view — single grain, safe to aggregate up.

## Sync model
- **Spend collectors + HubSpot mirrors:** full-window re-pull from 2025-01-01,
  upsert by key — `hubspot_deals_bq.sync_full_mirror_deals()` /
  `hubspot_leads_bq.sync_full_mirror()`. Backdated backfills always land.
- Cadence: 4×/day (every 6h) — hooks into existing `reporting_scheduler`.
- BQ cost is negligible (tables are MB-scale; load jobs free). The real limit
  is source-API rate, not BQ.

## Deal → ad-grain attribution rule (verified 2026-06-15)
Live HubSpot check on 2,000 paid deals YTD:
- `deal_qoyod_source` (channel): **100%** → channel revenue is complete/exact.
- `deal_utm_campaign`: 66% · `deal_utm_content`: 51% · `deal_utm_audience`: 44%.
- `deal_campaign_id_sync`: 21% but **100% resolves cleanly** in `campaigns_daily`.
- Among deals with both name+id: name is **ambiguous (>1 campaign) 26%** of the
  time; id agrees with name 94%, and where it disagrees (3.7%) id is correct.

**Rule (per grain, one key per deal — never both ANDed):**
1. `*_id_sync` present → join on stable ID (clean).
2. else UTM name present **and unambiguous** → resolve to id, join.
3. else (no id; name missing or ambiguous) → channel `(unknown)` bucket —
   counted at channel, never mis-pinned to a campaign.

This is the existing `paid_channel_campaign_daily` logic (mutually-exclusive
`deals_by_id` WHERE id IS NOT NULL / `deals_by_name` WHERE id IS NULL, summed),
**plus** the new ambiguity guard. Channel = exact; campaign = best-effort with a
visible unattributed remainder so `SUM(campaign) == channel`.

## Loses nothing — by construction
- Full-window MERGE/mirror daily → no incremental drift.
- Stable-ID joins → no rename/duplicate-name drops or fan-out.
- Each fact at its own grain; deals summed UP to channel, never forced DOWN onto
  spend rows (prevents the 1.84× fan-out seen 2026-05-13).
- `(unknown)` buckets keep unattributable spend/leads/deals visible at the level
  they're known.

## Migration order (build → parallel → reconcile → repoint → remove)
1. Build `hubspot_deals_individual` + full-window mirror. ✅ (this session)
2. Run new tables/views in parallel; change nothing downstream.
3. Reconcile to HubSpot (7-day sample, match within sync timing).
4. Repoint consumers: Hex, Databox, analysers, `daily_summary`, Flask.
5. Remove extras **only after** zero-consumer confirmation, in order:
   7 stale `v_*` views → group-B chain (`paid_channel_daily`,
   `paid_channel_campaign_daily`, `channel_roas_daily`,
   `utm_paid_attribution_daily`, `v_ad_performance`, `v_adset_performance`,
   `v_keyword_performance`) → HubSpot daily buckets (`hubspot_leads_module_daily`,
   `hubspot_deals_daily`).

## Backups taken before any change (2026-06-15)
- **BQ exact copy:** dataset `qoyod_marketing_backup_20260615` — 22/22 base
  tables, 0 row-count mismatches. (Primary restore path.)
- **Local copy:** `C:\Users\qoyod\Desktop\bq_backup_2026-06-15\` — NDJSON +
  schema + view DDL per object.
- Note: `v_campaign_leaderboard` is a dead orphan view (references long-dropped
  `campaign_performance_daily`) — confirmed safe to drop.
