# utm-lead-measurement — Join paid spend to HubSpot leads via UTM params

## When to use

Any time you need to compute CPL / CPQL at campaign, ad-set, or ad grain — or
explain why a cell shows zero leads for a campaign you know got clicks.

---

## The four UTM join grains

| Grain | Spend table | HubSpot field | Paid field | Join key |
|---|---|---|---|---|
| Channel | `campaigns_daily` grouped by `channel` | `qoyod_source` | via `v_channel_key_map` | `channel ↔ qoyod_source` |
| Campaign | `campaigns_daily` | `lead_utm_campaign` | `campaign_name` | `lower(campaign_name) = lower(lead_utm_campaign)` |
| Ad Set | `adsets_daily` | `lead_utm_audience` | `adset_name` | `lower(adset_name) = lower(lead_utm_audience)` |
| Ad | `ads_daily` | `lead_utm_content` | `ad_name` | `lower(ad_name) = lower(lead_utm_content)` |

**Keywords** (`keywords_daily`) do NOT join HubSpot — use platform conversions instead.

---

## The golden rule: always pre-aggregate HubSpot first

Never join raw `hubspot_leads_module_daily` rows directly to spend tables.
Each HubSpot row is a (date, source, campaign, adset, ad, …) bucket — joining
without pre-aggregating fans out spend × number of matching HubSpot rows.

```sql
-- CORRECT: pre-aggregate HubSpot into a CTE, then join
WITH hs AS (
  SELECT lower(lead_utm_campaign) AS key,
         SUM(leads_total)     AS leads,
         SUM(leads_qualified) AS sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_campaign IS NOT NULL
  GROUP BY 1
)
SELECT c.campaign_name, c.spend,
       COALESCE(hs.leads, 0) AS leads,
       SAFE_DIVIDE(c.spend, NULLIF(hs.leads,  0)) AS cpl,
       SAFE_DIVIDE(c.spend, NULLIF(hs.sqls,   0)) AS cpql
FROM (
  SELECT campaign_name, SUM(spend) AS spend
  FROM qoyod_marketing.campaigns_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel = 'google_ads'
  GROUP BY 1
) c
LEFT JOIN hs ON LOWER(c.campaign_name) = hs.key
ORDER BY c.spend DESC
```

---

## Full SQL templates

### Campaign grain (any channel)
```sql
WITH hs AS (
  SELECT lower(lead_utm_campaign) as key,
         sum(leads_total) as leads,
         sum(leads_qualified) as sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_campaign IS NOT NULL
  GROUP BY 1
),
campaigns AS (
  SELECT campaign_name,
         any_value(status) as status,
         sum(spend) as spend,
         sum(impressions) as impressions,
         sum(clicks) as clicks
  FROM qoyod_marketing.campaigns_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel = '{CHANNEL}'        -- e.g. 'google_ads', 'meta', 'snapchat', 'tiktok', 'linkedin'
  GROUP BY campaign_name
)
SELECT c.campaign_name, c.status,
  c.spend, c.impressions, c.clicks,
  round(safe_divide(c.clicks, nullif(c.impressions,0)) * 100, 4) as ctr,
  coalesce(hs.leads, 0) as leads,
  coalesce(hs.sqls,  0) as sqls,
  safe_divide(c.spend, nullif(hs.leads, 0)) as cpl,
  safe_divide(c.spend, nullif(hs.sqls,  0)) as cpql
FROM campaigns c
LEFT JOIN hs ON lower(c.campaign_name) = hs.key
ORDER BY c.spend DESC
```

### Ad Set grain (any channel)
```sql
WITH hs AS (
  SELECT lower(lead_utm_audience) as key,
         sum(leads_total) as leads,
         sum(leads_qualified) as sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_audience IS NOT NULL
  GROUP BY 1
),
adsets AS (
  SELECT adset_name, campaign_name,
         any_value(status) as status,
         sum(spend) as spend,
         sum(impressions) as impressions,
         sum(clicks) as clicks
  FROM qoyod_marketing.adsets_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel = '{CHANNEL}'
  GROUP BY adset_name, campaign_name
)
SELECT a.campaign_name, a.adset_name, a.status,
  a.spend, a.impressions, a.clicks,
  round(safe_divide(a.clicks, nullif(a.impressions,0)) * 100, 4) as ctr,
  coalesce(hs.leads, 0) as leads,
  coalesce(hs.sqls,  0) as sqls,
  safe_divide(a.spend, nullif(hs.leads, 0)) as cpl,
  safe_divide(a.spend, nullif(hs.sqls,  0)) as cpql
FROM adsets a
LEFT JOIN hs ON lower(a.adset_name) = hs.key
ORDER BY a.spend DESC
```

### Ad grain (any channel)
```sql
WITH hs AS (
  SELECT lower(lead_utm_content) as key,
         sum(leads_total) as leads,
         sum(leads_qualified) as sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_content IS NOT NULL
  GROUP BY 1
),
ads AS (
  SELECT ad_name, adset_name, campaign_name,
         any_value(status) as status,
         sum(spend) as spend,
         sum(impressions) as impressions,
         sum(clicks) as clicks
  FROM qoyod_marketing.ads_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel = '{CHANNEL}'
  GROUP BY ad_name, adset_name, campaign_name
)
SELECT a.campaign_name, a.adset_name, a.ad_name, a.status,
  a.spend, a.impressions, a.clicks,
  round(safe_divide(a.clicks, nullif(a.impressions,0)) * 100, 4) as ctr,
  coalesce(hs.leads, 0) as leads,
  coalesce(hs.sqls,  0) as sqls,
  safe_divide(a.spend, nullif(hs.leads, 0)) as cpl,
  safe_divide(a.spend, nullif(hs.sqls,  0)) as cpql
FROM ads a
LEFT JOIN hs ON lower(a.ad_name) = hs.key
ORDER BY a.spend DESC
```

### Channel grain (uses `channel_roas_daily` view — preferred for KPI boxes)
```sql
SELECT channel, spend, impressions, clicks,
       hs_leads, hs_qualified,
       safe_divide(spend, nullif(hs_leads,     0)) as cpl,
       safe_divide(spend, nullif(hs_qualified, 0)) as cpql
FROM qoyod_marketing.channel_roas_daily
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
GROUP BY channel, spend, impressions, clicks, hs_leads, hs_qualified
ORDER BY spend DESC
```

---

## Qualified lead definition

`leads_qualified` = leads where HubSpot stage label contains "qualified" and NOT "dis".

**CPQL = `spend / leads_qualified`** — always prefer this over CPL for decisions.

Never use `hubspot_leads_daily` (legacy, nothing writes to it).
Always use `hubspot_leads_module_daily` (Lead Module object `0-136`).

---

## Channel slug → qoyod_source map

| `channel` (BQ) | `qoyod_source` (HubSpot) |
|---|---|
| `google_ads` | `Google Ads` |
| `meta` | `Meta Ads` |
| `snapchat` | `Snapchat Ads` |
| `tiktok` | `Tiktok Ads` ← lowercase 'i' — never change |
| `microsoft` | `Microsoft Ads` |
| `linkedin` | `LinkedIn Ads` |

⚠️ **TikTok trap**: HubSpot writes `'Tiktok Ads'` (lowercase i). The view is
hardcoded to this value. Do not "fix" it to `TikTok Ads` or the join breaks.

---

## LinkedIn UTM mapping (different from other channels)

LinkedIn's hierarchy maps to UTM params differently:

| LinkedIn level | UTM param | Name format |
|---|---|---|
| Campaign Group | `utm_campaign` | `LinkedIn_{Product}` |
| Campaign | `utm_audience` | `LinkedIn_{Type}_{Language}_{Audience}` |
| Ad | `utm_content` | `LinkedIn_{CreativeVariant}` |

So `adsets_daily.adset_name` for LinkedIn holds the *Campaign* name (not Group).
Join: `lower(adset_name) = lower(lead_utm_audience)`.

---

## Diagnosing zero leads on a campaign you know got traffic

Run in order:

1. **Check UTM coverage in HubSpot:**
   ```sql
   SELECT lead_utm_campaign, lead_utm_audience, lead_utm_content, COUNT(*) as n
   FROM qoyod_marketing.hubspot_leads_module_daily
   WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
     AND qoyod_source = 'Google Ads'   -- or whichever channel
   GROUP BY 1,2,3
   ORDER BY n DESC
   LIMIT 20
   ```
   If campaign appears with NULL utm_campaign → UTM params missing from landing page URL.

2. **Check case mismatch:**
   ```sql
   SELECT lower(campaign_name), lower(lead_utm_campaign)
   FROM qoyod_marketing.campaigns_daily c
   LEFT JOIN qoyod_marketing.hubspot_leads_module_daily hs
     ON lower(c.campaign_name) = lower(hs.lead_utm_campaign)
   WHERE c.date >= ... AND hs.lead_utm_campaign IS NULL
   LIMIT 10
   ```

3. **Check date range**: HubSpot uses `createdate` of the lead, not the click date.
   A click on Apr 30 might become a lead on May 2. Widen the date window ±3 days.

4. **Check pipeline**: HubSpot rows exist for all pipelines. If querying only
   `Lead Pipeline`, bookkeeping leads won't appear. Use `AND pipeline IS NOT NULL`
   to include all, or name the pipeline explicitly.

---

## Notes

- `lead_utm_audience` and `lead_utm_content` are sparse — only filled when those
  UTM params are set on the landing page URL. Zero leads at adset/ad grain does NOT
  mean the campaign failed; check UTM coverage first.
- Always lower-case both sides of every join. Mixed-case values exist in production.
- Pre-aggregate on the HubSpot side first (fan-out prevention) — this is the
  most common source of inflated CPL numbers in ad-hoc queries.
