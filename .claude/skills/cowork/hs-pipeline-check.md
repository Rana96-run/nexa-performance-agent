---
name: hs-pipeline-check
description: Monday morning HubSpot pipeline health check — compares last 7 days of leads, SQLs, and deal progression against the prior 7 days by channel. Flags drops in lead volume, SQL rate, or deal conversion. Posts a structured summary to Slack and creates Asana tasks for flagged gaps. Gives the team a pipeline state briefing every Monday before the week starts.
schedule: "0 5 * * 1"
timezone: Asia/Riyadh
agent: growth-analyst
connectors: [bigquery, slack]
---

# /hs-pipeline-check — Monday Pipeline Health Check

You are the **Growth Analyst** running the Monday morning pipeline review. Your job is to surface funnel gaps — drops in lead volume, SQL rate, or deal conversion — before the team is too deep in the week to react.

## What this skill does

1. Queries BQ for last 7d vs prior 7d: leads, SQLs, CPQL, and deal amounts by channel
2. Flags: lead volume drop > 20%, SQL rate drop > 15%, or CPQL jump > 30%
3. Posts a structured pipeline summary to the notify Slack channel
4. Creates one Asana task per flagged gap

## BQ query

```sql
WITH hs_7d AS (
  SELECT
    lead_utm_campaign,
    SUM(leads_total)        AS leads_7d,
    SUM(leads_qualified)    AS sqls_7d
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY lead_utm_campaign
),
hs_prior AS (
  SELECT
    lead_utm_campaign,
    SUM(leads_total)        AS leads_prior,
    SUM(leads_qualified)    AS sqls_prior
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
                 AND DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY)
  GROUP BY lead_utm_campaign
),
spend AS (
  SELECT
    LOWER(campaign_name)    AS campaign_key,
    channel,
    SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
             THEN spend END) AS spend_7d,
    SUM(CASE WHEN date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
                           AND DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY)
             THEN spend END) AS spend_prior
  FROM `{PROJECT}.{DATASET}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  GROUP BY campaign_key, channel
)
SELECT
  sp.channel,
  SUM(hs7.leads_7d)      AS leads_7d,
  SUM(hp.leads_prior)    AS leads_prior,
  SUM(hs7.sqls_7d)       AS sqls_7d,
  SUM(hp.sqls_prior)     AS sqls_prior,
  SUM(sp.spend_7d)       AS spend_7d,
  SUM(sp.spend_prior)    AS spend_prior,
  SAFE_DIVIDE(SUM(sp.spend_7d), NULLIF(SUM(hs7.sqls_7d), 0))   AS cpql_7d,
  SAFE_DIVIDE(SUM(sp.spend_prior), NULLIF(SUM(hp.sqls_prior), 0)) AS cpql_prior,
  SAFE_DIVIDE(SUM(hs7.sqls_7d), NULLIF(SUM(hs7.leads_7d), 0))  AS sql_rate_7d,
  SAFE_DIVIDE(SUM(hp.sqls_prior), NULLIF(SUM(hp.leads_prior), 0)) AS sql_rate_prior
FROM spend sp
LEFT JOIN hs_7d hs7 ON LOWER(sp.campaign_key) = LOWER(hs7.lead_utm_campaign)
LEFT JOIN hs_prior hp ON LOWER(sp.campaign_key) = LOWER(hp.lead_utm_campaign)
GROUP BY sp.channel
HAVING SUM(sp.spend_7d) > 50
ORDER BY sp.channel
```

## Deal pipeline query

```sql
SELECT
  EXTRACT(WEEK FROM closedate) AS close_week,
  pipeline,
  dealstage,
  COUNT(*)                     AS deal_count,
  SUM(amount_total)            AS amount_usd
FROM `{PROJECT}.{DATASET}.hubspot_deals_daily`
WHERE closedate >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND date = (SELECT MAX(date) FROM `{PROJECT}.{DATASET}.hubspot_deals_daily`)
GROUP BY close_week, pipeline, dealstage
ORDER BY close_week, dealstage
```

Note: `amount_total` is USD (pre-converted by the collector at 3.75 SAR peg). Do NOT divide by 3.75.

## Flag thresholds

- Lead volume drop: `(leads_7d / leads_prior) < 0.80` (> 20% drop)
- SQL rate drop: `(sql_rate_7d / sql_rate_prior) < 0.85` (> 15% drop)
- CPQL jump: `(cpql_7d / cpql_prior) > 1.30` (> 30% increase)

## Slack summary (notify channel)

```
*Pipeline check — week of {week_start}*

{for each channel:}
• {channel}: {leads_7d} leads ({delta:+.0f}% WoW), {sqls_7d} SQLs ({sql_delta:+.0f}%), CPQL ${cpql_7d:.0f} ({cpql_delta:+.0f}%)
  {if flagged: ⚠ [{flag_type}] — Asana task created}

*Deal pipeline (last 14 days):*
{for each pipeline/stage with > 0 deals:}
• {pipeline} — {dealstage}: {deal_count} deals, ${amount_usd:,.0f}

{if no flags:} All metrics within range — pipeline healthy this week.
{if flags:} {N} flag(s) above — Asana tasks created for each.
```

## Asana task (one per flag)

```
PIPELINE GAP: {flag_type} — {channel} — {week_start}

FLAG: {flag_description}
This week: {current_value}
Prior week: {prior_value}
Change: {delta:+.0f}%
Threshold: {threshold}

CONTEXT:
Spend this week: ${spend_7d:.0f} vs prior: ${spend_prior:.0f}
Leads this week: {leads_7d} vs prior: {leads_prior}
SQLs this week: {sqls_7d} vs prior: {sqls_prior}

POSSIBLE CAUSES:
{for LEAD_DROP: lower spend, paused campaigns, platform delivery issue, seasonal effect}
{for SQL_RATE_DROP: lead quality change, qualification criteria change, new audience mix}
{for CPQL_JUMP: rising CPL, lower SQL rate, or both — drill into campaign mix}

RECOMMENDED ACTION:
Drill into the {channel} campaign mix for this period. Pull the period compare from analysers/period_compare.py and identify which campaigns drove the change.

Date range: {date_from} to {date_to}
Created: {date}
Due: {date + 2 days}
Priority: Medium
Type: Review
Channel: {channel}
Asset level: channel
Action: investigate → [Growth Analyst]
```

## Hard rules

- Amounts are USD — never SAR. Never divide by 3.75.
- CPQL uses HubSpot SQLs (`leads_qualified` from `hubspot_leads_module_daily`), not platform conversions.
- Always pre-aggregate HubSpot before joining to spend to avoid fan-out duplication.
- Minimum 14-day window for CPQL (7d current + 7d prior). Never evaluate on less data.
- Post the summary even if no flags — the team needs to see the numbers every Monday.

## Done means

Slack summary posted with full channel breakdown. One Asana task per flagged gap. All-clear note in the Slack message if no flags.
