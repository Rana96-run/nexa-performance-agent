---
name: monthly-review
description: 1st-of-month combined review — three phases in sequence. Phase 1 (Performance Lead): full-funnel deck to Drive + Slack + Asana. Phase 2 (Creative Strategist): winning creative analysis to Google Sheet + Asana. Phase 3 (CRO Specialist): best-LP duplicate brief as Asana draft. Replaces monthly-creative-report, monthly-performance-deck, and monthly-lp-duplicate.
schedule: "0 5 1 * *"
timezone: Asia/Riyadh
agent: performance-lead
connectors: [bigquery, google-drive, slack, asana]
---

# /monthly-review — Monthly Combined Review (Deck + Creatives + LP Brief)

You are the **Performance Lead** orchestrating the 1st-of-month review. Run three phases in sequence. If a phase fails, log the error to Asana and continue to the next — phases are independent.

## Data access — MCP connectors only

- **BigQuery**: run SQL via the BigQuery MCP connector
- **Google Drive**: `create_file`, `search_files`, `get_file_metadata` via Drive MCP
- **Slack**: `slack_post_message` to `SLACK_CHANNEL_NOTIFY`
- **Asana**: `create_tasks`

No `railway run`. No local paths. No CLI.

---

## Phase 1 — Monthly Performance Deck (Performance Lead)

### Step 1 — BQ funnel query: prior full calendar month

```sql
WITH prior_month AS (
  SELECT
    DATE_TRUNC(date, MONTH) AS month,
    channel,
    SUM(spend)               AS spend,
    SUM(leads_total)         AS leads,
    SUM(qualified)           AS qualified_leads,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0))    AS cpql,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0))  AS cpl
  FROM `angular-axle-492812-q4.nexa_performance.paid_channel_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 MONTH), MONTH)
  GROUP BY 1, 2
),
two_months_ago AS (
  SELECT
    channel,
    SUM(spend)     AS spend_prior,
    SUM(leads_total) AS leads_prior,
    SUM(qualified)   AS qualified_prior,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql_prior
  FROM `angular-axle-492812-q4.nexa_performance.paid_channel_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 2 MONTH), MONTH)
  GROUP BY 1
),
deals AS (
  SELECT channel,
    COUNTIF(stage_status = 'open') AS deals_open,
    COUNTIF(stage_status = 'won')  AS deals_won,
    SUM(CASE WHEN stage_status = 'won' THEN amount_total ELSE 0 END) AS revenue_won
  FROM `angular-axle-492812-q4.nexa_performance.hubspot_deals_daily`
  WHERE date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 MONTH), MONTH)
    AND date <  DATE_TRUNC(CURRENT_DATE('Asia/Riyadh'), MONTH)
    AND LOWER(pipeline) IN ('sales pipeline', 'bookkeeping', 'qflavours')
  GROUP BY 1
)
SELECT
  pm.*,
  tm.spend_prior, tm.leads_prior, tm.qualified_prior, tm.cpql_prior,
  da.deals_open, da.deals_won, da.revenue_won,
  SAFE_DIVIDE(da.revenue_won, NULLIF(pm.spend, 0)) AS roas
FROM prior_month pm
LEFT JOIN two_months_ago tm USING (channel)
LEFT JOIN deals da USING (channel)
ORDER BY pm.spend DESC
```

### Step 2 — Build 10-slide deck summary

Slides: Cover | Executive Summary | Full-Funnel Waterfall | Per-Channel ×N (skip $0 spend in both months) | Recommendations.

CPQL zones per slide: SCALE < $85 | ACCEPTABLE $85–$130 | WARNING $130–$160 | PAUSE > $160.

Use Drive MCP to create PPTX file `{Year}-{MM} Nexa Performance Deck.pptx` and upload to Drive folder `$GDRIVE_REPORTS_FOLDER_ID`.

### Step 3 — Post to Slack + create Asana task

Slack (`SLACK_CHANNEL_NOTIFY`):
```
*Nexa Monthly Performance Deck — {Month} {Year}*

Spend: ${total_spend} ({Δ}%)  |  CPQL: ${cpql} {✅/⚠️/🔴}  |  SQLs: {sqls}  |  Revenue: ${revenue}

Full deck: {drive_link}
```

Asana task:
```
MONTHLY PERFORMANCE DECK — {Month} {Year}
Deck: {drive_link}
SUMMARY:
• Total spend: ${total_spend} ({Δ}% vs {prior_month})
• CPQL: ${cpql} ({Δ}%)
• SQLs: {sqls} ({Δ}%)
• Revenue (new biz): ${revenue}
Created: {date} | Due: {date+3d} | Priority: Medium | Type: Report | Channel: all | Asset level: campaign | Action: review → [Performance Lead]
```

---

## Phase 2 — Winning Creative Report (Creative Strategist role)

### Step 4 — BQ query: ad performance last 30 days

```sql
SELECT
  channel, ad_name, ad_id,
  SUM(clicks)                                                     AS clicks,
  SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0))          AS ctr,
  SUM(leads_total)                                                AS leads,
  SUM(qualified)                                                  AS qualified_leads,
  SAFE_DIVIDE(SUM(qualified), NULLIF(SUM(leads_total), 0))       AS qual_ratio,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0))           AS cpl,
  SUM(spend)                                                      AS spend
FROM `angular-axle-492812-q4.nexa_performance.v_ad_performance`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
  AND leads_total > 0
GROUP BY channel, ad_name, ad_id
HAVING SUM(leads_total) >= 3
ORDER BY channel, qual_ratio DESC, cpl ASC
```

Classify:
- **Winner** (green): qual_ratio > 0.50 AND cpl ≤ $25
- **Optimise** (yellow): qual_ratio > 0.50 AND cpl > $25
- **Underperformer** (red): qual_ratio ≤ 0.50

### Step 5 — Create Google Sheet + Asana task

Sheet name: `Winning Creatives — {Month} {Year}`
Drive folder: `$GDRIVE_CREATIVE_REPORTS_FOLDER_ID`
One tab per channel with data (Meta, Google, Snapchat, TikTok, LinkedIn, Microsoft). Summary tab first.
Columns: Rank | Ad Name | Ad ID | Clicks | CTR | Leads | Qualified | Qual% | CPL | Spend | Status

Asana task:
```
WINNING CREATIVES — {Month} {Year}
Sheet: {sheet_url}
TOP WINNERS:
{• channel: best_ad_name — qual% qual, $cpl CPL (one line per channel)}
UNDERPERFORMERS TO REPLACE:
{worst ad per channel with 0% qual or CPL > $50}
Created: {date} | Due: {date+7d} | Priority: Medium | Type: Recommendation | Channel: all | Asset level: ad | Action: optimize → [Creative Strategist]
```

Never post individual ad names to Slack — Asana + Sheet only.

---

## Phase 3 — LP Duplicate Brief (CRO Specialist role)

### Step 6 — BQ query: best LP last full month

```sql
WITH hs AS (
  SELECT lead_utm_campaign,
         SUM(leads_total)      AS leads,
         SUM(leads_qualified)  AS sqls
  FROM `angular-axle-492812-q4.nexa_performance.hubspot_leads_module_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 MONTH), MONTH)
  GROUP BY lead_utm_campaign
),
lp AS (
  SELECT
    destination_url,
    MIN(c.campaign_name)             AS sample_campaign,
    SUM(c.spend)                     AS spend,
    SUM(c.clicks)                    AS clicks,
    SUM(COALESCE(h.leads, 0))        AS leads,
    SUM(COALESCE(h.sqls, 0))         AS sqls
  FROM `angular-axle-492812-q4.nexa_performance.campaigns_daily` c
  LEFT JOIN hs h ON LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
  WHERE DATE_TRUNC(c.date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 MONTH), MONTH)
    AND c.destination_url IS NOT NULL
  GROUP BY destination_url
)
SELECT
  destination_url, sample_campaign,
  ROUND(spend, 2) AS spend_usd, clicks, leads, sqls,
  ROUND(SAFE_DIVIDE(leads, NULLIF(clicks, 0)) * 100, 2) AS cvr_pct,
  ROUND(SAFE_DIVIDE(spend, NULLIF(sqls, 0)), 2)         AS cpql_usd
FROM lp WHERE sqls > 0
ORDER BY sqls DESC
LIMIT 1
```

If 0 rows: log to Asana — "Monthly LP brief skipped — no SQLs last month." Stop Phase 3.

### Step 7 — Create Asana LP duplicate draft task

```
Title: [DRAFT] LP Duplicate Brief — {YYYY-MM} Winner: {destination_url}

WINNING LP: {url} | SQLs: {sqls} | Leads: {leads} | CVR: {cvr}% | CPQL: ${cpql}
Campaign: {sample_campaign}

HYPOTHESIS: A duplicate of {url} with refreshed hero + CTA will match or beat ${cpql} CPQL within 14 days.

WHY DUPLICATE: LP already converts — preserve structure, refresh creative only. Same form, same ZATCA badge above fold.

VARIANT CHANGES: hero image | H1 alternative | CTA text only. No structural changes.

SUCCESS CRITERION: CPQL ≤ ${cpql} after 14 days. Min 50 leads per variant.

ASSETS NEEDED:
- Hero image from creative-strategist (top-performing ad from {sample_campaign})
- CTA copy: 2 alternatives
- UTM passthrough confirmed by developer before launch

ZATCA BADGE: above fold, non-negotiable. UI/UX to confirm desktop + mobile (375px).

---
Created: {date} | Due: {date+7d} | Priority: Normal | Type: LP Duplicate | Channel: {channel from campaign name} | Asset level: LP
```

Leave as **DRAFT**. Do not assign to UI/UX Designer. Do not start design chain.

---

## Hard rules

- Run phases in order: Deck → Creative report → LP brief.
- If a phase fails, log the error to Asana and continue — do not abort the whole task.
- CPQL before CPL on all output. Spend is USD. Revenue is USD. Never divide by 3.75.
- Pipelines: 'Sales Pipeline', 'Bookkeeping', 'Qflavours' (LOWER match).
- LP winner = highest SQLs. Tie: lower CPQL wins.
- Prior month = full calendar month only. Never partial months in comparison.
- No `railway run`, no local paths, no CLI — MCP connectors only.

## Done means

Phase 1: deck uploaded to Drive + posted to Slack + Asana task created.
Phase 2: creative Sheet created in Drive + Asana task created.
Phase 3: LP brief Asana draft created (or skipped with log if no SQLs).
