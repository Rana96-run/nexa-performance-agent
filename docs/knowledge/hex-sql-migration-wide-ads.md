# Hex SQL Changes Required
Date: 2026-06-16
Reason: wide_ads migration — paid_channel_daily, v_adset_performance, v_ad_performance, channel_roas_daily dropped as physical tables; now exist as VIEWs sourced from wide_ads. New queries should target wide_ads directly.

## How to apply
1. Open the Hex workspace: `Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK`
2. In Logic View, find each cell by searching for the FROM clause pattern shown under "Find this"
3. Replace the FROM clause and column references as shown under "Replace with"
4. Re-run the cell and confirm it returns data before moving to the next

---

## Change 1 — channel_roas_daily → wide_ads

`channel_roas_daily` was a physical table (dropped 2026-06-15). It no longer exists. Replace all references.

**Find this pattern in any Hex cell:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.channel_roas_daily`
```

**Replace with:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
```
Then add or ensure GROUP BY includes: `date, channel`

**Column renames also needed in SELECT:**
| Old column | New column |
|---|---|
| `revenue_won` | `all_revenue_won` (or `SUM(all_revenue_won) AS revenue_won`) |
| `deals_won` | `all_deals_won` (or `SUM(all_deals_won) AS deals_won`) |
| `amount_total` | `all_revenue_won` (channel_roas_daily used amount_total for total revenue — same field) |

**Example — before:**
```sql
SELECT
  date,
  channel,
  SUM(spend) AS spend,
  SUM(revenue_won) AS revenue_won,
  SAFE_DIVIDE(SUM(revenue_won), NULLIF(SUM(spend), 0)) AS roas
FROM `angular-axle-492812-q4.qoyod_marketing.channel_roas_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY 1, 2
```

**Example — after:**
```sql
SELECT
  date,
  channel,
  SUM(spend) AS spend,
  SUM(all_revenue_won) AS revenue_won,
  SAFE_DIVIDE(SUM(all_revenue_won), NULLIF(SUM(spend), 0)) AS roas
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY date, channel
```

---

## Change 2 — paid_channel_daily → wide_ads

`paid_channel_daily` is now a VIEW sourced from wide_ads (not a physical table). For new cells, skip the view and query wide_ads directly — same result, lower dependency chain.

**Find this:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
```

**Replace with:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
```
GROUP BY must include: `date, channel`

**Column renames:**
| Old column | New column |
|---|---|
| `qualified` | `leads_qualified` |
| `open_leads` | `leads_open` |
| `revenue_won` | `all_revenue_won` |
| `deals_won` | `all_deals_won` |
| `leads` | `leads_total` |

**Example — before:**
```sql
SELECT
  date, channel,
  SUM(spend) AS spend,
  SUM(leads) AS leads,
  SUM(qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)) AS cpl,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
GROUP BY 1, 2
```

**Example — after:**
```sql
SELECT
  date, channel,
  SUM(spend) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)) AS cpl,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)) AS cpql
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
GROUP BY date, channel
```

---

## Change 3 — v_adset_performance → wide_ads

`v_adset_performance` is now a VIEW. For new cells, query wide_ads directly with the adset-level GROUP BY.

**Find this:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.v_adset_performance`
```

**Replace with:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
```

**Add/update GROUP BY to include:**
```sql
GROUP BY date, channel, campaign_id, campaign_name, adset_id, adset_name
```

**Column renames:**
| Old column | New column |
|---|---|
| `qualified` | `leads_qualified` |
| `utm_audience` | `adset_name` (same data, different alias in the old view) |
| `revenue_won` | `all_revenue_won` |
| `leads` | `leads_total` |

**Example — before:**
```sql
SELECT
  campaign_name, adset_name,
  SUM(spend) AS spend,
  SUM(leads) AS leads,
  SUM(qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql
FROM `angular-axle-492812-q4.qoyod_marketing.v_adset_performance`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND channel = 'meta'
GROUP BY 1, 2
```

**Example — after:**
```sql
SELECT
  campaign_name, adset_name,
  SUM(spend) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0)) AS cpql
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND channel = 'meta'
GROUP BY date, channel, campaign_id, campaign_name, adset_id, adset_name
```

---

## Change 4 — v_ad_performance → wide_ads

`v_ad_performance` is now a VIEW. For new cells, query wide_ads directly with ad-level GROUP BY.

**Find this:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.v_ad_performance`
```

**Replace with:**
```sql
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
```

**Add/update GROUP BY to include:**
```sql
GROUP BY date, channel, campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name, utm_content
```

**Column renames:**
| Old column | New column |
|---|---|
| `qualified` | `leads_qualified` |
| `open_leads` | `leads_open` |
| `revenue_won` | `all_revenue_won` |
| `deals_won` | `all_deals_won` |
| `leads` | `leads_total` |

**Example — before:**
```sql
SELECT
  ad_name, campaign_name,
  SUM(spend) AS spend,
  SUM(leads) AS leads,
  SUM(qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)) AS cpl
FROM `angular-axle-492812-q4.qoyod_marketing.v_ad_performance`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND channel = 'google_ads'
GROUP BY 1, 2
```

**Example — after:**
```sql
SELECT
  ad_name, campaign_name,
  SUM(spend) AS spend,
  SUM(leads_total) AS leads,
  SUM(leads_qualified) AS sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)) AS cpl
FROM `angular-axle-492812-q4.qoyod_marketing.wide_ads`
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND channel = 'google_ads'
GROUP BY date, channel, campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name, utm_content
```

---

## Tables that are UNCHANGED — no Hex edits needed for these

| Table/View | Status | Note |
|---|---|---|
| `hubspot_leads_module_daily` | VIEW — unchanged | Still the correct join target for leads. Pre-aggregate in a CTE before joining to spend. |
| `hubspot_deals_daily` | VIEW — unchanged | Still the correct table for deal revenue. |
| `wide_ads` | BASE TABLE — primary surface | Use this for all new cells. |
| `wide_keywords` | BASE TABLE — unchanged | Use for keyword-level analysis. |
| `campaigns_daily` | BASE TABLE — unchanged | Use for campaign-level spend including PMax/awareness. |
| `keywords_daily` | BASE TABLE — unchanged | Raw keyword grain (wide_keywords is built from this). |
| `ads_daily` | BASE TABLE — unchanged | Raw ad grain (wide_ads is built from this). |

---

## Column name quick reference — wide_ads

These are the current column names in `wide_ads` as of 2026-06-16:

**Dimensions:**
`date, channel, campaign_id, campaign_name, adset_id, adset_name, ad_id, ad_name, utm_content, utm_audience`

**Spend metrics:**
`spend, impressions, clicks, ctr, cpc`

**Lead metrics:**
`leads_total, leads_qualified, leads_disqualified, leads_open`

**Deal/revenue metrics:**
`all_revenue_won, all_deals_won, all_revenue_total, all_deals_total`

**Derived KPIs (compute inline with SAFE_DIVIDE):**
```sql
SAFE_DIVIDE(spend, NULLIF(leads_total, 0))     AS cpl
SAFE_DIVIDE(spend, NULLIF(leads_qualified, 0)) AS cpql
SAFE_DIVIDE(all_revenue_won, NULLIF(spend, 0)) AS roas
```
