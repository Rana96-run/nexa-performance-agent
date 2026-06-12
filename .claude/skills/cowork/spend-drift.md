---
name: spend-drift
description: Daily pre-loop sweep for three spend-pattern failures — scaling an underperformer (high CPQL AND rising spend), silent death (previously active campaign now near-zero spend), and launch wave (3+ campaigns first-spend in same window on same channel). Posts Slack alert + Asana task for each finding. Runs before the daily-loop so findings are in context for the digest.
schedule: "0 4 * * *"
timezone: Asia/Riyadh
agent: growth-analyst
connectors: [bigquery, slack, asana]
---

# /spend-drift — Daily Spend Pattern Anomaly Sweep

You are the **Growth Analyst** running the pre-loop spend drift detection. Your job is to catch three failure patterns before the daily-loop assembles the #approvals digest.

## What this skill does

1. Queries BigQuery for the three drift rules below
2. For each finding: posts a Slack alert to the notify channel + creates an Asana review task
3. If nothing found: posts nothing, creates nothing

## The three rules

### Rule 1 — Scaling an underperformer
Condition: 14-day CPQL > $140 AND week-over-week spend increased > 20%

```sql
WITH hs AS (
  SELECT date, lead_utm_campaign,
         SUM(leads_qualified) AS sqls
  FROM `{PROJECT}.{DATASET}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  GROUP BY date, lead_utm_campaign
),
spend AS (
  SELECT campaign_name, channel,
         SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) THEN spend END) AS spend_14d,
         SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL  7 DAY) THEN spend END) AS spend_7d,
         SUM(CASE WHEN date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
                              AND DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY) THEN spend END) AS spend_prior_7d
  FROM `{PROJECT}.{DATASET}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  GROUP BY campaign_name, channel
),
joined AS (
  SELECT sp.campaign_name, sp.channel,
         sp.spend_14d, sp.spend_7d, sp.spend_prior_7d,
         SUM(hs.sqls) AS sqls_14d,
         SAFE_DIVIDE(sp.spend_14d, NULLIF(SUM(hs.sqls), 0)) AS cpql_14d,
         SAFE_DIVIDE(sp.spend_7d - sp.spend_prior_7d, NULLIF(sp.spend_prior_7d, 0)) AS spend_wow_delta
  FROM spend sp
  LEFT JOIN hs ON LOWER(sp.campaign_name) = LOWER(hs.lead_utm_campaign)
  GROUP BY sp.campaign_name, sp.channel, sp.spend_14d, sp.spend_7d, sp.spend_prior_7d
)
SELECT * FROM joined
WHERE cpql_14d > 140 AND spend_wow_delta > 0.20
ORDER BY cpql_14d DESC
```

### Rule 2 — Silent death
Condition: had >$500 spend in prior 30 days AND last 7 days spend < 5% of that

```sql
WITH prior AS (
  SELECT campaign_name, channel,
         SUM(CASE WHEN date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 37 DAY)
                              AND DATE_SUB(CURRENT_DATE(), INTERVAL 8 DAY) THEN spend END) AS spend_30d,
         SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE(), INTERVAL  7 DAY) THEN spend END) AS spend_7d
  FROM `{PROJECT}.{DATASET}.campaigns_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 37 DAY)
  GROUP BY campaign_name, channel
)
SELECT * FROM prior
WHERE spend_30d > 500
  AND SAFE_DIVIDE(spend_7d, spend_30d) < 0.05
ORDER BY spend_30d DESC
```

### Rule 3 — Launch wave
Condition: 3+ campaigns with their first-ever spend appearing within the same 7-day window on the same channel

```sql
WITH first_spend AS (
  SELECT campaign_name, channel, MIN(date) AS first_date
  FROM `{PROJECT}.{DATASET}.campaigns_daily`
  WHERE spend > 0
  GROUP BY campaign_name, channel
)
SELECT channel, COUNT(*) AS new_campaigns,
       MIN(first_date) AS wave_start, MAX(first_date) AS wave_end,
       STRING_AGG(campaign_name, ', ' ORDER BY first_date LIMIT 5) AS sample_campaigns
FROM first_spend
WHERE first_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY channel
HAVING COUNT(*) >= 3
ORDER BY new_campaigns DESC
```

## Output per finding

### Slack alert (notify channel)
```
*Spend drift detected — {rule_name}*

{for scaling-underperformer:}
• {campaign_name} ({channel}): CPQL $X over 14d, spend ↑Y% WoW — budget increasing on a failing campaign

{for silent-death:}
• {campaign_name} ({channel}): $X spend in prior 30d, now $Y/week (Z%) — campaign may have died silently

{for launch-wave:}
• {channel}: {N} campaigns launched within 7 days — possible uncoordinated launch causing impression share splits

Review before today's #approvals digest.
```

### Asana task (per finding, not per rule)
```
SPEND DRIFT: {rule_name} — {campaign_name or channel}

Rule triggered: {rule description}
Window: {date_from} to {date_to}
Metric: {key metric and value}
Prior period: {comparison value}

RECOMMENDED ACTION:
{for scaling-underperformer: pause budget increase, reduce to prior week level until CPQL improves}
{for silent-death: check if intentionally paused or silently broken — verify campaign status in platform}
{for launch-wave: review if launches were coordinated — IS splits across N campaigns may dilute all}

Created: {date}
Due: {date}
Priority: High
Type: Review
Channel: {channel}
Asset level: campaign
Action: review → [Performance Lead]
```

## Hard rules

- Spend is always USD. Never label as SAR.
- CPQL threshold: $140 (2× the $70 acceptable zone — only flag clearly broken campaigns).
- Silent death threshold: >$500 prior 30d AND <5% last 7d (filters out intentional weekly pauses).
- Launch wave threshold: ≥3 first-spends same channel within 7 days.
- Do NOT post if no findings — silence is correct signal.
- Do NOT create tasks for campaigns that are confirmed paused by the team (check Asana for recent pause tasks on the campaign name).

## Done means

Each finding has a Slack alert posted to the notify channel AND an Asana review task created. No findings = no posts, no tasks.
