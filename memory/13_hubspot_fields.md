# HubSpot Fields, UTM Mapping & Channel Key Map

Last audited: 2026-05-04. Update when new HubSpot properties are added.

---

## Object: Lead Module (object `0-136`)

Table: `hubspot_leads_module_daily`  
Grain: one row per (date, qoyod_source, pipeline, stage, utm_campaign, utm_audience, utm_content, utm_source, utm_medium, utm_term)  
Partitioned by: `date`  
Clustered by: `qoyod_source`, `pipeline`

### BQ Schema

| BQ field | Type | Notes |
|---|---|---|
| `date` | DATE | createdate of the lead (truncated to day) |
| `qoyod_source` | STRING | HubSpot property `lead_qoyod_source` — the channel label written by the landing page or form |
| `pipeline` | STRING | HubSpot pipeline label (e.g. "Lead Pipeline", "Bookkeeping Pipeline") |
| `stage` | STRING | HubSpot stage label (e.g. "Qualified", "Disqualified", "New Lead") |
| `lead_utm_campaign` | STRING | utm_campaign from the lead's form submission — matches `campaign_name` in `campaigns_daily` |
| `lead_utm_audience` | STRING | utm_audience (custom param) — matches `adset_name` in `adsets_daily` |
| `lead_utm_content` | STRING | utm_content — matches `ad_name` in `ads_daily` |
| `lead_utm_source` | STRING | utm_source (e.g. "google", "facebook", "snapchat") |
| `lead_utm_medium` | STRING | utm_medium (e.g. "cpc", "paid_social") |
| `lead_utm_term` | STRING | utm_term — matches `keyword_text` in `keywords_daily` |
| `leads_total` | INT64 | All leads in this bucket for the day |
| `leads_qualified` | INT64 | Leads in "Qualified" stage |
| `leads_disqualified` | INT64 | Leads in "Disqualified" stage |
| `leads_open` | INT64 | Leads still open (not yet qualified or disqualified) |
| `top_disq_reason` | STRING | Most common disqualification reason in this bucket |
| `updated_at` | TIMESTAMP | When this row was last written |

### HubSpot raw property names → BQ field names

| HubSpot property API name | BQ field |
|---|---|
| `lead_qoyod_source` | `qoyod_source` |
| `lead_utm_campaign` | `lead_utm_campaign` |
| `lead_utm_audience` | `lead_utm_audience` |
| `lead_utm_content` | `lead_utm_content` |
| `lead_utm_source` | `lead_utm_source` |
| `lead_utm_medium` | `lead_utm_medium` |
| `hs_pipeline` | resolved to `pipeline` label |
| `hs_pipeline_stage` | resolved to `stage` label |
| `hs_lead_is_open` | used to compute `leads_open` |
| `leads_disqualification_reason__ops` | feeds `top_disq_reason` (Lead pipeline) |
| `leads_disqualification_reason__ops_qflavour` | feeds `top_disq_reason` (Qflavours pipeline) |
| `disqualification_reason_bookkeeping` | feeds `top_disq_reason` (Bookkeeping pipeline) |
| `leads_disqualification_reason__sub_reasons` | fetched but NOT stored in BQ yet |
| `lead_original_traffic_source` | fetched but NOT stored in aggregated BQ (used for qoyod_source fallback logic) |
| `lead_latest_traffic_source` | fetched but NOT stored in BQ |
| `lead_original_traffic_source_drilldown_1` | fetched but NOT stored in BQ |
| `lead_latest_traffic_source_drilldown_1` | fetched but NOT stored in BQ |
| `lead_original_traffic_source_drilldown_2` | fetched but NOT stored in BQ |
| `lead_latest_traffic_source_drilldown_2` | fetched but NOT stored in BQ |

---

## UTM → BQ join key mapping (universal)

| UTM parameter | What it identifies | HubSpot BQ field | Paid channel BQ field | BQ table |
|---|---|---|---|---|
| `utm_campaign` | Campaign | `lead_utm_campaign` | `campaign_name` | `campaigns_daily` |
| `utm_audience` | Ad Set / Ad Group / Ad Squad | `lead_utm_audience` | `adset_name` | `adsets_daily` |
| `utm_content` | Ad / Creative | `lead_utm_content` | `ad_name` | `ads_daily` |
| `utm_term` | Keyword | `lead_utm_term` | `keyword_text` | `keywords_daily` |
| `utm_source` | Channel source | `lead_utm_source` | `channel` (via map) | — |
| `utm_medium` | Medium | `lead_utm_medium` | — | — |

**Join pattern (always pre-aggregate HubSpot first):**

```sql
WITH hs AS (
  SELECT lower(lead_utm_campaign) AS key,
         SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_campaign IS NOT NULL
  GROUP BY 1
)
SELECT c.campaign_name, c.spend,
       COALESCE(hs.leads, 0) AS leads,
       SAFE_DIVIDE(c.spend, NULLIF(hs.leads, 0)) AS cpl
FROM (SELECT campaign_name, SUM(spend) AS spend
      FROM qoyod_marketing.campaigns_daily
      WHERE date BETWEEN ... AND channel = 'google_ads'
      GROUP BY 1) c
LEFT JOIN hs ON LOWER(c.campaign_name) = hs.key
```

---

## Channel key map: `channel` slug ↔ HubSpot `qoyod_source`

View: `v_channel_key_map`

| BQ `channel` (in campaigns_daily) | HubSpot `qoyod_source` | Display name |
|---|---|---|
| `google_ads` | `Google Ads` | Google Ads |
| `meta` | `Meta Ads` | Meta Ads |
| `snapchat` | `Snapchat Ads` | Snapchat Ads |
| `tiktok` | `Tiktok Ads` | TikTok Ads (**lowercase 'i'** — critical for joins) |
| `microsoft` | `Microsoft Ads` | Microsoft Ads |
| `linkedin` | `LinkedIn Ads` | LinkedIn Ads |
| `organic_search` | `Organic Search` | Organic Search |

**⚠️ TikTok trap**: HubSpot writes `'Tiktok Ads'` (lowercase i), not `'TikTok Ads'`. The `v_channel_key_map` is hardcoded to match this. Never change it.

---

## Pipelines

| Pipeline label | What it covers |
|---|---|
| `Lead Pipeline` | Main product (accounting / e-invoice / ZATCA). Also matched by `NOT LIKE '%book%'` |
| `Bookkeeping Pipeline` | Qbookkeeping product |

In `channel_roas_daily` and Hex SQL:
- `leads_total/leads_qualified` across ALL pipelines → `hs_leads / hs_qualified`
- `leads_accounting / qualified_accounting` → Lead Pipeline only
- `leads_bookkeeping / qualified_bookkeeping` → Bookkeeping Pipeline only

---

## Cross-platform field name equivalences (CRITICAL)

All paid channel data is normalised into the same field names in BQ regardless
of what the platform calls them. The join to HubSpot always uses the BQ name.

| BQ normalised field | Google Ads | Meta | Snapchat | TikTok | LinkedIn | HubSpot UTM |
|---|---|---|---|---|---|---|
| `adset_name` | Ad Group name | Ad Set name | Ad Squad name | Ad Group name | Campaign name (utm_audience level) | `lead_utm_audience` |
| `ad_name` | Ad name | Ad name | Creative name | Ad name | Ad name | `lead_utm_content` |
| `keyword_text` | Keyword | — | — | — | — | `lead_utm_term` |
| `campaign_name` | Campaign name | Campaign name | Campaign name | Campaign name | Campaign Group name | `lead_utm_campaign` |

**Join rules (always lower-case both sides):**
```
lower(adsets_daily.adset_name)   = lower(hubspot_leads_module_daily.lead_utm_audience)
lower(ads_daily.ad_name)         = lower(hubspot_leads_module_daily.lead_utm_content)
lower(campaigns_daily.campaign_name) = lower(hubspot_leads_module_daily.lead_utm_campaign)
lower(keywords_daily.keyword_text)   = lower(hubspot_leads_module_daily.lead_utm_term)
```

These are always the same field regardless of channel:
- `adset_name` always holds what was the "Ad Group" (Google), "Ad Set" (Meta),
  "Ad Squad" (Snapchat), "Ad Group" (TikTok), or "Campaign" (LinkedIn) — never use
  platform-specific names when querying BQ.
- `ad_name` always holds what was the "Creative name" (Snapchat), "Ad" (Meta/Google/TikTok/LinkedIn).

---

## CPL / CPQL methodology (summary)

| Grain | Spend source | Leads source | Join key |
|---|---|---|---|
| **Channel** (KPI boxes) | `campaigns_daily` grouped by `channel` | `hubspot_leads_module_daily` grouped by `qoyod_source` | `v_channel_key_map` (channel ↔ qoyod_source) via `channel_roas_daily` |
| **Campaign** (utm_campaign) | `campaigns_daily.campaign_name` | `hubspot_leads_module_daily.lead_utm_campaign` | `lower(campaign_name) = lower(lead_utm_campaign)` |
| **Ad Set / Ad Group** (utm_audience) | `adsets_daily.adset_name` | `hubspot_leads_module_daily.lead_utm_audience` | `lower(adset_name) = lower(lead_utm_audience)` |
| **Ad / Creative** (utm_content) | `ads_daily.ad_name` | `hubspot_leads_module_daily.lead_utm_content` | `lower(ad_name) = lower(lead_utm_content)` |
| **Keyword** (utm_term) | `keywords_daily.keyword_text` | No HubSpot join (keywords don't get UTM tracking) | N/A — use platform conversions |

---

## Qualified lead definition

A "qualified lead" = a lead in the **Qualified** stage of its pipeline.  
`leads_qualified` in BQ = count of leads where `stage_label` contains "qualified" and NOT "dis".

CPQL = `spend / leads_qualified` (never `spend / leads_total`).

**Never use:** `hubspot_leads_daily` (legacy contact lifecycle table — nothing writes to it).  
**Always use:** `hubspot_leads_module_daily` (Lead Module object `0-136`).

---

## Disqualification reasons (stored in `top_disq_reason`)

Values seen in production (from the disqualification matrix):
- `No lead response`
- `After 8+ sales attempts`
- `Number failed`
- `Not a Buyer`
- `No Registered business`
- `Browsing/Testing`
- `Training`
- `Existing customer`
- `Urdu speaker`
- `Unknown` (fallback when no reason property is set)

Sub-reasons are fetched (`leads_disqualification_reason__sub_reasons`) but not yet stored in BQ — only `top_disq_reason` (the primary reason) is persisted.

---

## HubSpot API

- **Base URL**: `https://api.hubapi.com`
- **Lead module object type**: `0-136`  
- **Search endpoint**: `/crm/v3/objects/0-136/search`  
- **Properties endpoint**: `/crm/v3/properties/0-136`  
- **10,000 row hard cap** on search API after `after=10000` → use 7-day windows
- **READ-ONLY** unless Amar explicitly approves in Slack

---

## 00_index.md entry

Add under "Memory files":
```
memory/13_hubspot_fields.md   HubSpot BQ schema, UTM→field mapping, channel key map, CPL methodology
```
