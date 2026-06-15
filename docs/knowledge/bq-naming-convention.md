# BQ Table & Python File Naming Convention

Established 2026-06-15 after `utm_paid_attribution_daily` was dropped and three
reporting views were found unregistered in `ALL_VIEWS`. Documented here to prevent
recurrence.

---

## BQ Table Layers

### Layer 0 — Raw store (physical tables, upserted by collectors)

Pattern: `{source}_{grain}`

| Table | Description |
|---|---|
| `campaigns_daily` | Spend by campaign × day (all channels) |
| `adsets_daily` | Spend by adset × day |
| `ads_daily` | Spend by ad × day |
| `keywords_daily` | Keyword perf × day (Google + Microsoft only) |
| `platform_tokens` | OAuth refresh tokens |
| `agent_activity_log` | Agent action log (scheduler telemetry) |

### Layer 1 — Individual mirrors (physical tables, full-window re-pull every sync)

Pattern: `{source}_individual`

| Table | Description |
|---|---|
| `hubspot_leads_individual` | One row per HubSpot lead (record-level mirror, 2025-01-01+) |
| `hubspot_deals_individual` | One row per HubSpot deal (record-level mirror, all pipelines) |

### Layer 2 — Wide joined tables (materialized every 6h by `materialize_heavy_views()`)

Pattern: `wide_{grain}`

Built from layer 0 + layer 1 using id-first attribution (platform sync ID → utm name fallback).

| Table | Description |
|---|---|
| `wide_ads` | Ad grain — spend (ads_daily) + leads + deals (hubspot_*_individual) |
| `wide_keywords` | Keyword grain — spend (keywords_daily) + leads + deals (hubspot_*_individual) |

### Layer 3 — Reporting views (BQ VIEWs, GROUP BY rollups — in `ALL_VIEWS` + `_sub_campaign_views()`)

Pattern: `{scope}_{grain}` or `v_{grain}_performance`

These are `CREATE OR REPLACE VIEW` DDL registered in `collectors/views.py::ALL_VIEWS`
(or `_sub_campaign_views()` for views defined in `bq_writer.py`).
They are recreated on every 6h `refresh_all_views()` call.

| View | Grain | Source |
|---|---|---|
| `paid_channel_daily` | Channel × day | `wide_ads` |
| `paid_channel_campaign_daily` | Campaign × day | `wide_ads` |
| `v_adset_performance` | Adset × day | `wide_ads` |
| `v_ad_performance` | Ad × day | `wide_ads` |
| `v_keyword_performance` | Keyword × day | `wide_keywords` + `hubspot_deals_daily` |
| `v_channel_key_map` | Channel slug → display name | static UNNEST |

> **Dropped 2026-06-16 (0 active consumers):** `v_new_biz_daily`, `v_agent_activity_dashboard` — do not recreate.

### Layer 3b — Compat views (BQ VIEWs, aggregate from layer 1 — same name as old physical tables)

Pattern: preserve old table name (zero Python change for all consumers)

| View | Old physical table replaced | Source |
|---|---|---|
| `hubspot_leads_module_daily` | `hubspot_leads_module_daily` (physical, dropped 2026-06-15) | `hubspot_leads_individual` |
| `hubspot_deals_daily` | `hubspot_deals_daily` (physical, dropped 2026-06-15) | `hubspot_deals_individual` |

---

## Python Collector File Naming

Pattern: `{source}_bq.py`

| File | Writes to |
|---|---|
| `collectors/meta_bq.py` | `campaigns_daily`, `adsets_daily`, `ads_daily` |
| `collectors/google_bq.py` | `campaigns_daily`, `adsets_daily`, `keywords_daily` |
| `collectors/snapchat_bq.py` | `campaigns_daily` |
| `collectors/linkedin_bq.py` | `campaigns_daily`, `adsets_daily` |
| `collectors/tiktok_bq.py` | `campaigns_daily` |
| `collectors/microsoft_ads_bq.py` | `campaigns_daily` |
| `collectors/hubspot_leads_bq.py` | `hubspot_leads_individual` |
| `collectors/hubspot_deals_bq.py` | `hubspot_deals_individual` |

## Python View/Schema File Naming

| File | Responsibility |
|---|---|
| `collectors/views.py` | ALL_VIEWS list + layer 2 wide-table DDL + layer 3b compat view DDL + `refresh_all_views()` |
| `collectors/bq_writer.py` | Upsert helpers + layer 3 view DDL for adset/ad/keyword grain (`V_ADSET_PERFORMANCE_SQL`, `V_AD_PERFORMANCE_SQL`, `V_KEYWORD_PERFORMANCE_SQL`) |

---

## Rules for new tables

| Scenario | Layer | Naming pattern | Registration |
|---|---|---|---|
| New collector output | 0 | `{source}_{grain}` | None (physical table) |
| New record-level mirror | 1 | `{source}_individual` | None (physical table) |
| New joined wide table | 2 | `wide_{grain}` | Add to `_heavy_views_list()` in `views.py` |
| New reporting rollup | 3 | `v_{grain}_performance` or `{scope}_{grain}` | Add to `ALL_VIEWS` in `views.py` (or `_sub_campaign_views()` if DDL lives in `bq_writer.py`) |
| New compat shim | 3b | preserve old name | Add to `ALL_VIEWS` in `views.py` |

**Never create a new physical table for reporting — use VIEWs at layer 3.**

---

## Why this matters — lessons from 2026-06-15

1. `utm_paid_attribution_daily` was a transient intermediate table that was silently
   dropped when the wide-table redesign completed. `v_keyword_performance` had two CTEs
   pointing to it — the next 6h scheduler run would have crashed the keyword view rebuild.
   **Fix:** rewrite off `wide_keywords` + `hubspot_leads_individual`.

2. `paid_channel_daily` and `paid_channel_campaign_daily` had `CREATE OR REPLACE VIEW`
   DDL in `views.py` but were NOT in `ALL_VIEWS`. Nothing refreshed them after the old
   physical tables were dropped. **Fix:** add to `ALL_VIEWS`.

3. `v_adset_performance` and `v_ad_performance` DDL lived in `bq_writer.py` and were
   only called via `create_views()` which ran one view. They were not wired into the
   6h cycle. **Fix:** import into `_sub_campaign_views()`.

---

## Forward-looking query rule

Any NEW query (n8n, Hex, new scripts) should target `wide_ads` or `wide_keywords` directly
with an inline GROUP BY — not the reporting views. The reporting views (`paid_channel_daily`,
`v_adset_performance`, `v_ad_performance`, `v_keyword_performance`) exist for backward compat
with existing consumers only and will be deprecated once those consumers are migrated.
