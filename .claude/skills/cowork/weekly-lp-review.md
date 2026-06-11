---
name: weekly-lp-review
description: Weekly CRO review of all live landing pages — leads, qualified leads, CVR and CPQL per LP pulled from BQ, written to Google Sheet as a draft. Runs every Monday. Leave Asana task as draft; no auto-posting.
schedule: "0 3 * * 1"
timezone: Asia/Riyadh
agent: cro-specialist
connectors: [bigquery, google-drive]
---

# /weekly-lp-review — Weekly Landing Page Performance Review

You are the **CRO Specialist** running the weekly LP audit. Pull live BQ data, populate the Google Sheet report, and leave an Asana draft. No Slack post. No auto-execution.

## What this skill does

Every Monday at 06:00 Riyadh (03:00 UTC), query last 7 days of LP performance from BQ (grouped by `destination_url`), match HubSpot qualified lead counts, compute CVR and CPQL per LP, and write the result to the weekly LP Google Sheet as a new tab. Create an Asana task as a draft for the CRO team to review.

## BQ query — LP performance last 7 days

```sql
WITH hs AS (
  SELECT lead_utm_campaign,
         SUM(leads_total)      AS leads,
         SUM(leads_qualified)  AS sqls
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  GROUP BY lead_utm_campaign
),
lp AS (
  SELECT
    destination_url,
    MIN(c.campaign_name)                   AS sample_campaign,
    SUM(c.spend)                           AS spend,
    SUM(c.clicks)                          AS clicks,
    SUM(c.impressions)                     AS impressions,
    SUM(COALESCE(h.leads, 0))              AS leads,
    SUM(COALESCE(h.sqls, 0))               AS sqls
  FROM `{PROJECT}.{DATASET}.campaigns_daily` c
  LEFT JOIN hs h
    ON LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
  WHERE c.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    AND c.destination_url IS NOT NULL
  GROUP BY destination_url
)
SELECT
  destination_url,
  sample_campaign,
  ROUND(spend, 2)                                          AS spend_usd,
  clicks,
  impressions,
  leads,
  sqls,
  ROUND(SAFE_DIVIDE(leads, NULLIF(clicks, 0)) * 100, 2)   AS cvr_pct,
  ROUND(SAFE_DIVIDE(spend, NULLIF(sqls, 0)), 2)           AS cpql_usd
FROM lp
WHERE spend > 0
ORDER BY leads DESC
```

Note: `cvr_pct` = leads / clicks (paid visits as proxy — page-level GA4 is not in BQ at this time).

## Google Sheet output

Write results to the main reporting sheet (ID: `120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg`) — the same sheet used by `action_points_sync.py` and `sheet_action_logger.py`. Add a new tab named `LP-YYYY-MM-DD` (report date). If a tab with that name already exists, overwrite it.

Columns (in order):
| destination_url | sample_campaign | spend_usd | clicks | impressions | leads | sqls | cvr_pct | cpql_usd |

Sort: leads DESC.

## Asana task (draft — do NOT publish)

Create a draft Asana task in the CRO project with:

```
Title: LP Weekly Review — {YYYY-MM-DD}

Body:
Weekly LP performance summary for the 7 days ending {date}.

| LP URL | Leads | SQLs | CVR% | CPQL |
|--------|-------|------|------|------|
[top 10 rows from BQ query]

Full results: {Google Sheet link}

Flags:
- LPs with CPQL > $85: [list]
- LPs with CVR% < 1%: [list]
- LPs with 0 leads this week: [list]

Action required: CRO Specialist to review and update test backlog.

---
Created: {date} | Due: {date + 3 days} | Priority: Normal | Type: Review | Channel: All | Asset level: LP
```

Leave as **DRAFT** — do not assign, do not set to active. The task surfaces for review; no auto-execution.

## Hard rules

- Never post to Slack. This is a draft review loop only.
- Never modify any live LP, campaign, or ad based on this data.
- CPQL > $85 is a flag for review, not a pause trigger — pause decisions require full 14-day window and #approvals flow.
- If the Google Sheets API call fails, log the error to `agent_activity_log` and stop — do not create the Asana task without a valid Sheet link.

## Done means

Google Sheet tab written with last-7-day LP data. Asana draft task created with top-10 table and flags. BQ log entry written: `action=weekly_lp_review, role=cro_analysis`.
