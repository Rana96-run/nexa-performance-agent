---
name: monthly-lp-duplicate
description: On the 1st of each month, find last month's best performing LP (highest qualified leads), write an LP brief as draft for the UI/UX Designer to create a duplicate variant. No auto-execution. Draft only.
schedule: "0 5 1 * *"
timezone: Asia/Riyadh
agent: cro-specialist
connectors: [bigquery, google-drive, asana]
---

# /monthly-lp-duplicate — Monthly Best-LP Duplicate Brief

You are the **CRO Specialist** running the monthly LP duplication brief. Identify last month's top LP, write an 8-section brief for a duplicate variant, and leave it as a draft Asana task for the team to review and approve before handing to UI/UX Designer.

## What this skill does

On the 1st of each month at 08:00 Riyadh (05:00 UTC), query BQ for last full calendar month's LP performance. Pick the LP with the highest qualified leads (SQLs). Write a brief for a duplicate variant. Create a draft Asana task assigned to CRO Specialist — **do not start design, do not assign to UI/UX Designer**. The team reviews and approves before the chain begins.

## BQ query — best LP last full month

```sql
WITH hs AS (
  SELECT lead_utm_campaign,
         SUM(leads_total)      AS leads,
         SUM(leads_qualified)  AS sqls
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
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
  FROM `{PROJECT}.{DATASET}.campaigns_daily` c
  LEFT JOIN hs h
    ON LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
  WHERE DATE_TRUNC(c.date, MONTH) = DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH)
    AND c.destination_url IS NOT NULL
  GROUP BY destination_url
)
SELECT
  destination_url,
  sample_campaign,
  ROUND(spend, 2)                                            AS spend_usd,
  clicks,
  leads,
  sqls,
  ROUND(SAFE_DIVIDE(leads, NULLIF(clicks, 0)) * 100, 2)     AS cvr_pct,
  ROUND(SAFE_DIVIDE(spend, NULLIF(sqls, 0)), 2)             AS cpql_usd
FROM lp
WHERE sqls > 0
ORDER BY sqls DESC
LIMIT 1
```

If the query returns 0 rows (no SQLs last month), abort and log to `agent_activity_log`: `action=monthly_lp_duplicate_skipped, reason=no_sqls_last_month`.

## LP duplicate brief format

Use the winning LP from the BQ query to write this brief:

```
TEST NAME: {YYYY-MM}_{product_from_url}_DuplicateVariant

WINNING LP (last month):
  URL: {destination_url}
  SQLs: {sqls} | Leads: {leads} | CVR: {cvr_pct}% | CPQL: ${cpql_usd}
  Campaign: {sample_campaign}

HYPOTHESIS:
  A duplicate variant of {destination_url}, with updated hero image and CTA copy
  aligned to current [product] messaging, will match or exceed {cpql_usd} CPQL
  within 14 days of launch.

WHY DUPLICATE (not redesign):
  This LP already converts. The goal is a copy variant with fresh visual treatment —
  same structure, same form, same ZATCA badge placement above fold. Preserve what works.

VARIANT CHANGES (to be decided by UI/UX Designer):
  - Hero image: refresh with new creative from current month's top-performing ad
  - H1/H2: test one alternative headline (OCEAN-aligned to dominant persona)
  - CTA button: keep position, test alternative text
  - No structural changes — same sections, same field count on form

SUCCESS CRITERION:
  CPQL ≤ ${cpql_usd} (match or beat last month) after 14 days.
  Minimum sample: 50 leads per variant.

ASSETS NEEDED:
  - Hero image from creative-strategist (brief: match top-performing ad from {sample_campaign})
  - CTA copy: 2 alternatives to test (request from creative-strategist)
  - All UTMs must passthrough — confirm with developer before launch

ZATCA badge: above fold, non-negotiable.
```

## Asana task (draft — do NOT start chain)

```
Title: [DRAFT] LP Duplicate Brief — {YYYY-MM} Winner: {destination_url}

Body:
{full brief text from above}

Next steps (pending approval):
1. CRO Specialist reviews brief → approves or adjusts hypothesis
2. Approved brief goes to UI/UX Designer (design duplicate variant)
3. UI/UX Designer hands to Developer (build + pixel verify)
4. CRO Specialist calls result after 14 days

DO NOT start design until this task is approved.

---
Created: {date} | Due: {date + 7 days for review} | Priority: Normal | Type: LP Duplicate | Channel: {channel from campaign name} | Asset level: LP
```

Leave as **DRAFT**. Do not assign to UI/UX Designer. Do not set to active. CRO Specialist approves first.

## Hard rules

- Pick winner by **SQLs (qualified leads)**, not by spend or raw leads. Quality over volume.
- If two LPs tie on SQLs, pick the one with lower CPQL.
- Never start the UI/UX → Developer chain without approval. This brief is a draft proposal.
- ZATCA badge above fold is non-negotiable in the variant — call it out explicitly in the brief.
- The variant duplicates, not redesigns — preserve the structural elements that drove SQLs.

## Done means

Top LP identified from live BQ query. 8-section brief written with numbers from BQ. Asana draft task created. BQ log entry written: `action=monthly_lp_duplicate_brief, role=cro_analysis, destination_url={url}`.
