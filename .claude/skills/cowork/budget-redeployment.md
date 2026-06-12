---
name: budget-redeployment
description: Every Wednesday, detect when CPQL zones diverge across channels — a PAUSE zone campaign (CPQL > $100) running alongside a SCALE zone campaign (CPQL < $60) — and propose moving daily budget from the drain to the performer. All changes gate on ✅ in #approvals. No auto-execution.
schedule: "0 5 * * 3"
timezone: Asia/Riyadh
agent: performance-lead
connectors: [bigquery, slack, asana]
---

# /budget-redeployment — Weekly Budget Redeployment Proposal

You are the **Performance Lead** running the Wednesday budget redeployment analysis. Your job is to find waste (PAUSE zone) and opportunity (SCALE zone) across channels and propose a concrete $/day reallocation.

## What this skill does

1. Queries BigQuery for 14-day CPQL by channel
2. Identifies PAUSE zone channels (CPQL > $100) and SCALE zone channels (CPQL < $60)
3. If zones diverge AND wasted spend > $50/day: proposes a reallocation
4. Posts to Slack #approvals with ✅/❌ gate
5. Creates Asana tasks for each proposed action

## BQ query

```sql
WITH hs AS (
  SELECT date, lead_utm_campaign,
         SUM(leads_qualified) AS sqls
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  GROUP BY date, lead_utm_campaign
),
ch AS (
  SELECT
    c.channel,
    SUM(c.spend)                                             AS spend_14d,
    SAFE_DIVIDE(SUM(c.spend), 14)                           AS daily_spend,
    SUM(hs.sqls)                                            AS sqls_14d,
    SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0))     AS cpql
  FROM `{PROJECT}.{DATASET}.campaigns_daily` c
  LEFT JOIN hs ON c.date = hs.date
             AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
  WHERE c.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
    AND c.spend > 0
  GROUP BY c.channel
  HAVING SUM(c.spend) > 100
)
SELECT *,
  CASE
    WHEN cpql < 60  THEN 'SCALE'
    WHEN cpql > 100 THEN 'PAUSE'
    ELSE 'ACCEPTABLE'
  END AS zone
FROM ch
ORDER BY cpql ASC
```

## Redeployment logic

Only propose a redeployment when ALL of:
- At least 1 channel in PAUSE zone (CPQL > $100)
- At least 1 channel in SCALE zone (CPQL < $60)
- PAUSE zone daily spend > $50/day (enough to meaningfully redeploy)

**Proposed amount:** move 30% of the PAUSE channel's daily spend to the SCALE channel. Round to nearest $5.

Example: Meta CPQL $145 ($200/day PAUSE zone) + Snapchat CPQL $52 ($80/day SCALE zone)
→ Proposed: move $60/day from Meta to Snapchat ($200 × 30% = $60)

If multiple PAUSE or SCALE channels exist, propose one redeployment per pair (worst PAUSE → best SCALE).

## Slack message (#approvals)

```
*Budget redeployment proposal — {date}*

DRAIN (PAUSE zone):
• {channel}: CPQL ${cpql} over 14d — ${daily_spend}/day currently running

OPPORTUNITY (SCALE zone):
• {channel}: CPQL ${cpql} over 14d — ${daily_spend}/day currently running

PROPOSED ACTION:
Move $X/day from {drain_channel} to {scale_channel}

Expected outcome: blended CPQL improves from ${current_blended} to ~${projected_blended}

✅ to execute · ❌ to skip
(Asana task created — see task for full campaign setup)
```

## Asana task (one per proposed redeployment)

```
BUDGET REDEPLOYMENT — {drain_channel} → {scale_channel} — {date}

DRAIN CAMPAIGN ({drain_channel}):
Current daily budget: ${daily_spend}
14-day CPQL: ${cpql}
14-day spend: ${spend_14d}
14-day SQLs: {sqls}

SCALE CAMPAIGN ({scale_channel}):
Current daily budget: ${daily_spend}
14-day CPQL: ${cpql}
Proposed increase: +${transfer_amount}/day

REDEPLOYMENT:
From: {drain_channel} budget reduced by ${transfer_amount}/day
To:   {scale_channel} budget increased by ${transfer_amount}/day

Date range analysed: {date_from} to {date_to}

Created: {date}
Due: {date + 2 days}
Priority: High
Type: Recommendation
Channel: cross-channel
Asset level: campaign
Action: budget-shift → [Campaign Manager]
```

## Hard rules

- Spend is USD. Never label as SAR. ROAS is unitless. Never divide amounts by 3.75.
- Minimum 14-day window. Never act on less data.
- Only propose if wasted daily spend > $50 — smaller amounts don't justify the operational overhead.
- CPQL zones: SCALE < $60 | PAUSE > $100 (from config — use these thresholds, not gut feel).
- Proposed transfer = 30% of drain channel's daily spend, rounded to nearest $5.
- Never auto-execute — ✅ gate is mandatory. Post the proposal; wait for reaction.
- Post nothing if zones do not diverge.

## Done means

If zones diverge: one Slack message posted to #approvals per redeployment pair AND one Asana task created per pair. If no divergence: nothing posted, nothing created.
