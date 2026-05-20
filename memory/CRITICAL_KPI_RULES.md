# CRITICAL KPI RULES — RE-READ BEFORE EVERY ANALYSIS

These are non-negotiables that the agent has historically violated. They
are repeated here in compact form for unmissable re-checking.

## 1. NEVER use `campaigns_daily.leads` as a leads metric

The column exists in the schema because channels (Bing, Meta, etc.) report
their own conversion counts. **These are NOT real leads.** For
WebsiteTraffic-objective campaigns specifically, the channel often counts
page visits as conversions.

**Caught violations (don't repeat these):**

- **2026-05-19 (Rana)** — claimed Bing_WebsiteTraffic_Search_AR_Generic
  was a top performer at $1.48 CPL (1,157 channel-reported "leads" for
  $1,711 spend). Reality on HubSpot side: 31 leads / 9 SQLs → $190 CPQL
  (worst campaign, should pause).

**Correct pattern (mandatory for any analysis touching leads/SQLs):**

```sql
WITH hs AS (
  SELECT
    LOWER(lead_utm_campaign) AS campaign_key,
    SUM(leads_total)     AS leads,
    SUM(leads_qualified) AS sqls
  FROM hubspot_leads_module_daily
  WHERE date BETWEEN ... AND ...
  GROUP BY campaign_key
),
spend AS (
  SELECT campaign_name, SUM(spend) AS spend, SUM(clicks) AS clicks
  FROM campaigns_daily
  WHERE channel = '...' AND date BETWEEN ...
  GROUP BY campaign_name
)
SELECT s.*, hs.leads, hs.sqls,
       SAFE_DIVIDE(s.spend, hs.leads) AS cpl,
       SAFE_DIVIDE(s.spend, hs.sqls)  AS cpql
FROM spend s LEFT JOIN hs ON LOWER(s.campaign_name) = hs.campaign_key
```

## 2. Pre-execution checklist for ANY new analysis script

Before writing a Python/SQL script that touches campaign performance, the
agent MUST mentally verify ALL of these:

1. **Does this script report leads, SQLs, CPL, CPQL, or qualification rate?**
   - If yes → the leads side MUST come from `hubspot_leads_module_daily`
   - If using `campaigns_daily` at all, it can ONLY supply spend/clicks/impressions/IS

2. **Is there a pre-aggregate-then-join step?**
   - Joining campaigns_daily to hubspot_leads_module_daily without pre-agg
     causes spend fan-out (multiplies spend by matching HS rows).
   - Always: `WITH hs AS (SELECT ... GROUP BY ...) ... JOIN hs ON ...`

3. **Is the date window explicit?**
   - Never "last 7 days" in narrative. Always `YYYY-MM-DD to YYYY-MM-DD`
     so HubSpot UI verification is possible.

4. **For ad-level analysis (Meta/Snap/TikTok):**
   - Channel-reported conversions on ads_daily are also unreliable.
   - Join to `hubspot_leads_module_daily` on `lead_utm_content` for the
     leads count, not on the ads_daily `leads` column.

## 3. Self-check after writing a script — before running

Before executing any new analysis script, scan the SQL for:
- `SELECT .* leads .* FROM .* campaigns_daily` → VIOLATION
- `SELECT .* qualified .* FROM .* campaigns_daily` (column doesn't exist anyway, but flag pattern) → VIOLATION
- `SELECT .* conversions .* FROM .* (campaigns_daily|ads_daily)` and reporting it as "leads" → VIOLATION

If found → rewrite using the WITH-hs-pre-agg pattern above.
