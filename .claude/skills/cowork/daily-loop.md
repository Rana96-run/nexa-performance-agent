---
name: daily-loop
description: Run the 8-step intelligence loop. Invoke at 08:00 Riyadh daily or on-demand for a full performance cycle. Outputs the nightly #approvals digest + Asana tasks.
schedule: "0 5 * * *"
timezone: Asia/Riyadh
agent: ai-orchestrator
connectors: [bigquery, slack, asana]
---

# /daily-loop — Nexa Daily Intelligence Loop

You are the AI Orchestrator running the 8-step Nexa daily intelligence loop. You manage, route, and gate. You do NOT run local scripts or CLI commands.

## Data access — MCP connectors only

All data comes from MCP connectors. Never use `railway run`. Never reference `D:\Nexa Performance Agent`.

- **BigQuery**: run SQL via the BigQuery MCP connector
- **Slack**: `slack_post_message`, `slack_get_channel_history`
- **Asana**: `create_tasks`, `get_my_tasks`, `update_tasks`, `add_comment`

---

## Step 1 — OBSERVE: yesterday's channel summary

```sql
SELECT
  channel,
  ROUND(SUM(spend), 0) AS spend,
  SUM(leads_total)     AS leads,
  SUM(qualified)       AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(leads_total)), 2) AS cpl,
  ROUND(SAFE_DIVIDE(
    SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
            OR leads_total = 0, spend, 0)),
    NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
                   OR leads_total = 0, qualified, 0)), 0)
  ), 2) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(qualified), SUM(leads_total)) * 100, 1) AS qual_pct,
  ROUND(SAFE_DIVIDE(SUM(revenue_won), SUM(spend)), 2) AS roas
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE date = DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
GROUP BY channel
ORDER BY spend DESC
```

## Step 2 — COMPARE: last 7d vs prior 7d per channel

```sql
WITH base AS (
  SELECT channel,
    CASE
      WHEN date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                    AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY) THEN 'B'
      WHEN date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
                    AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 8 DAY)  THEN 'A'
    END AS period,
    spend, leads_total, qualified, open_leads, revenue_won
  FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
)
SELECT channel, period,
  ROUND(SUM(spend), 0) AS spend,
  SUM(leads_total)     AS leads,
  SUM(qualified)       AS sqls,
  ROUND(SAFE_DIVIDE(
    SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
            OR leads_total = 0, spend, 0)),
    NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
                   OR leads_total = 0, qualified, 0)), 0)
  ), 1) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(revenue_won), SUM(spend)), 2) AS roas
FROM base WHERE period IS NOT NULL
GROUP BY channel, period
ORDER BY channel, period
```

Compute Δ% for spend, leads, CPQL. Flag: ✅ CPQL < $85 | ⚠️ $85–$130 | 🔴 > $130 or >20% regressed.

## Step 3 — INVESTIGATE: drill flagged channels

For each 🔴 channel:

```sql
SELECT
  campaign_name,
  ROUND(SUM(spend), 0) AS spend,
  SUM(leads_total)     AS leads,
  SUM(qualified)       AS sqls,
  ROUND(SAFE_DIVIDE(
    SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
            OR leads_total = 0, spend, 0)),
    NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
                   OR leads_total = 0, qualified, 0)), 0)
  ), 0) AS cpql,
  ROUND(SAFE_DIVIDE(SUM(qualified), SUM(leads_total)) * 100, 1) AS qual_pct
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE channel = '{flagged_channel}'
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
GROUP BY campaign_name ORDER BY spend DESC LIMIT 20
```

State root cause in 2 sentences.

## Step 4 — DECIDE: pause / scale / flag

KPI zones (campaign): scale < $85 | acceptable $85–$130 | warning $130–$160 | pause > $160. Min 14 days.

Check zero-conv ads + junk-lead ads:

```sql
SELECT
  v.ad_name, v.channel, v.campaign_name,
  ROUND(SUM(v.spend), 0) AS spend,
  SUM(v.leads_total)     AS hs_leads,
  ROUND(SAFE_DIVIDE(SUM(v.leads_disqualified), NULLIF(SUM(v.leads_total),0))*100,1) AS disq_pct,
  DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MIN(v.date), DAY) AS days_active
FROM `angular-axle-492812-q4.qoyod_marketing.v_ad_performance` v
WHERE v.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
GROUP BY v.ad_name, v.channel, v.campaign_name
HAVING
  (spend > 70 AND hs_leads = 0 AND days_active >= 7)
  OR (spend > 30 AND disq_pct >= 60 AND hs_leads >= 5 AND days_active >= 10)
ORDER BY spend DESC LIMIT 20
```

## Step 5 — GATE: post #approvals digest via Slack MCP

```
Nexa · {YYYY-MM-DD}  |  {DASHBOARD_URL}

PERFORMANCE  ({start} → {end} vs prior 7d)
{channel}   ${spend}  ·  {leads} leads  ·  ${cpql} CPQL  {✅/⚠️/🔴}  ({Δ}% CPQL)

ACTIONS  —  ✅ executes all  ·  ❌ skips all
↗  `{campaign}`   +{X}% budget  (${old} → ${new}/day)
⏸  `{ad_name}`    pause   (${cpql} CPQL · {N}d · ${spend})

REVIEW ONLY  (Asana tasks created)
⚡  {flag}  {campaign}  —  {asana_url}
```

Post via `slack_post_message` to `SLACK_CHANNEL_APPROVAL`.

## Step 6 — MONITOR: 7d and 14d action outcomes

```sql
SELECT action_type, target_name, target_id, channel, event_date, outcome
FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
WHERE DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), event_date, DAY) IN (7, 14)
  AND action_type IN ('pause', 'scale', 'create')
  AND outcome IS NULL
ORDER BY event_date DESC
```

Update each via Asana MCP `add_comment` with current performance vs pre-action baseline.

## Step 7 — LEARN

Notable outcomes → `add_comment` on the Asana task.

## Step 8 — FORECAST

```sql
SELECT
  channel,
  ROUND(SUM(spend) / 7 * 30, 0)    AS projected_month_spend,
  ROUND(SUM(leads_total) / 7 * 30)  AS projected_month_leads,
  ROUND(SAFE_DIVIDE(
    SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
            OR leads_total = 0, spend, 0)),
    NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
                   OR leads_total = 0, qualified, 0)), 0)
  ), 0) AS cpql_7d
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
GROUP BY channel ORDER BY projected_month_spend DESC
```

Append as a follow-up Slack message in the same thread.

---

## Hard rules

- CPQL before CPL. 14-day minimum for pause/scale.
- Leads from `paid_channel_daily` (pre-joined from `hubspot_leads_module_daily`).
- Never execute scale/pause/create without ✅ in #approvals.
- Spend always USD. Deal amounts already USD — never divide by 3.75.
- No `railway run`, no local paths, no CLI — MCP connectors only.

## Done means

#approvals digest posted via Slack MCP, Asana tasks created for all REVIEW ONLY items, monitor items updated.
