---
name: monthly-performance-deck
description: Run the 1st-of-month full-funnel paid performance analysis across all three new-biz pipelines (Sales Pipeline, Bookkeeping, Qflavours). Builds a Google Slides deck, uploads to Drive, and posts the link to Slack + Asana.
schedule: "0 5 1 * *"
timezone: Asia/Riyadh
agent: performance-lead
connectors: [bigquery, google-drive, slack, asana]
---

# /monthly-performance-deck — Monthly Full-Funnel Performance Deck

You are the **Performance Lead** running the monthly full-funnel analysis. This deck goes to leadership and the team. It must be accurate, comparative, and decision-grade.

## What this skill does

1. Pulls prior month's full-funnel data from BQ (spend → leads → qualified → deals → won)
2. Compares to the month prior (month-over-month)
3. Creates a 10-slide Google Slides deck
4. Uploads to Drive: `Nexa Performance Reports/Monthly Decks/`
5. Posts Drive link to `SLACK_CHANNEL_NOTIFY` + creates Asana task

## Funnel BQ query

```sql
-- Channel-level funnel for the prior full calendar month
WITH prior_month AS (
  SELECT
    DATE_TRUNC(date, MONTH) AS month,
    channel,
    SUM(spend)               AS spend,
    SUM(leads_total)         AS leads,
    SUM(qualified)           AS qualified_leads,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)) AS cpl
  FROM `{PROJECT}.{DATASET}.paid_channel_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
  GROUP BY 1, 2
),
two_months_ago AS (
  SELECT
    channel,
    SUM(spend)               AS spend_prior,
    SUM(leads_total)         AS leads_prior,
    SUM(qualified)           AS qualified_prior,
    SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)) AS cpql_prior
  FROM `{PROJECT}.{DATASET}.paid_channel_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH), MONTH)
  GROUP BY 1
),
deals AS (
  SELECT
    channel,
    pipeline,
    COUNT(*) FILTER (WHERE stage_status = 'open')  AS deals_open,
    COUNT(*) FILTER (WHERE stage_status = 'won')   AS deals_won,
    SUM(CASE WHEN stage_status = 'won' THEN amount_total ELSE 0 END) AS revenue_won
  FROM `{PROJECT}.{DATASET}.hubspot_deals_daily`
  WHERE date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
    AND date <  DATE_TRUNC(CURRENT_DATE(), MONTH)
    AND LOWER(pipeline) IN ('sales pipeline', 'bookkeeping', 'qflavours')
  GROUP BY 1, 2
),
deals_agg AS (
  SELECT channel,
    SUM(deals_open) AS deals_open,
    SUM(deals_won)  AS deals_won,
    SUM(revenue_won) AS revenue_won
  FROM deals GROUP BY 1
)
SELECT
  pm.*,
  tm.spend_prior,
  tm.leads_prior,
  tm.qualified_prior,
  tm.cpql_prior,
  da.deals_open,
  da.deals_won,
  da.revenue_won,
  SAFE_DIVIDE(da.revenue_won, NULLIF(pm.spend, 0)) AS roas
FROM prior_month pm
LEFT JOIN two_months_ago tm USING (channel)
LEFT JOIN deals_agg da USING (channel)
ORDER BY pm.spend DESC
```

## Slide structure (10 slides)

### Slide 1 — Cover
```
Nexa Performance — {Month} {Year}
Total Spend: ${total_spend} | CPQL: ${cpql} | Leads: {leads} | SQLs: {qualified}
```

### Slide 2 — Executive Summary
3 KPIs vs prior month (use ▲/▼ with % change):
```
Spend:          ${spend_curr}    ({delta}% vs {prior_month})
CPQL:           ${cpql_curr}     ({delta}% vs {prior_month})  ← most important
SQLs (Qualified): {sqls_curr}   ({delta}% vs {prior_month})
```
One-sentence interpretation below each: "CPQL improved 12% — driven by Meta qual rate increase."

### Slide 3 — Full-Funnel Waterfall (All Channels)
```
Spend  →  Leads  →  Qualified  →  Deals Created  →  Deals Won  →  Revenue
${N}      {N}       {N}             {N}                {N}           ${N}
         XX%        XX%             XX%                XX%
         (conv)     (qual rate)     (lead-to-deal)     (close rate)
```
Show conversion % at each step.

### Slides 4–9 — Per-Channel Pages (Meta, Google, Snapchat, TikTok, LinkedIn, Microsoft)
For each channel with spend > $0:
```
{Channel} — {Month} {Year}

Spend: ${N}  |  CPL: ${N}  |  CPQL: ${N}  |  ROAS: {N}x

Funnel: {leads} leads → {qualified} SQLs ({qual%}%) → {deals_won} deals won → ${revenue}
vs Prior: Spend {▲/▼N%}  |  CPQL {▲/▼N%}  |  SQLs {▲/▼N%}

Status: SCALE / ACCEPTABLE / WARNING / PAUSE
(based on CPQL zone: < $85 = SCALE, $85–$130 = ACCEPTABLE, $130–$160 = WARNING, > $160 = PAUSE)
```
Skip channels with $0 spend in both months.

### Slide 10 — Recommendations
Max 5 bullets, one per channel with an action:
- "Meta: CPQL $72 — scale budget 25% next month"
- "Snapchat: CPQL $180 — pause until creative refresh (Asana task created)"
- Use campaign-level KPI zones from config (CPQL_SCALE = $85)

## Drive upload

- Folder: `Nexa Performance Reports/Monthly Decks/`
- Filename: `{Year}-{MM} Nexa Performance Deck.pptx` (or .gslides)
- Share with: editor access for the Drive account, viewer link for the team

## Slack message

```
*Nexa Monthly Performance Deck — {Month} {Year}*

Spend: ${total_spend}  |  CPQL: ${cpql} {icon}  |  SQLs: {sqls}  |  Revenue: ${revenue}

Full deck: {drive_link}
```

CPQL icon: ✅ if < $85, ⚠️ if $85–$130, 🔴 if > $130.

## Asana task

```
MONTHLY PERFORMANCE DECK — {Month} {Year}

Google Slides: {drive_link}

SUMMARY:
• Total spend: ${total_spend} ({vs_prior}% vs {prior_month})
• CPQL: ${cpql} ({vs_prior}%)
• SQLs: {sqls} ({vs_prior}%)
• Revenue (new biz): ${revenue}

Created: {date}
Due: {date + 3 days}
Priority: Medium
Type: Report
Channel: all
Asset level: campaign
Action: review → [Performance Lead]
```

## Hard rules

- Pipelines in scope: `'Sales Pipeline'`, `'Bookkeeping'`, `'Qflavours'` (LOWER match — exact labels from HubSpot).
- Spend is USD. Revenue is USD. ROAS is unitless. Never divide by 3.75.
- CPQL before CPL on every slide. CPL is secondary context.
- Prior month = full calendar month (day 1–last day). Never partial months in comparison.
- Skip channels with 0 spend AND 0 leads in both months — don't show empty slides.
- Month-end forecast (from `_run_forecaster`) is separate — reference it in the Recommendations slide if available in BQ.

## Done means

10-slide deck uploaded to Drive folder, Drive link posted to Slack and Asana, BQ activity log entry written.
