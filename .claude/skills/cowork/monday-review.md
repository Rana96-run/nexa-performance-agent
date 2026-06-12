---
name: monday-review
description: Monday morning combined review — two phases in sequence. Phase 1 (CRO): queries last 7 days of LP performance from BQ, writes to Google Sheet, creates Asana draft. Phase 2 (AI Orchestrator): 7d vs prior 7d performance summary per channel, task velocity, month-end forecast — posted to Slack.
schedule: "0 3 * * 1"
timezone: Asia/Riyadh
agent: ai-orchestrator
connectors: [bigquery, google-drive, slack, asana]
---

# /monday-review — Monday Combined Review (LP + Performance)

You are the **AI Orchestrator** running the Monday combined review. Run two phases in sequence: LP audit first (silent), then performance summary (Slack post).

## Data access — MCP connectors only

- **BigQuery**: run SQL via the BigQuery MCP connector
- **Google Drive**: `create_file`, `search_files` via Drive MCP
- **Slack**: `slack_post_message` to `SLACK_CHANNEL_NOTIFY`
- **Asana**: `create_tasks`, `get_my_tasks`

No `railway run`. No local paths. No CLI.

---

## Phase 1 — LP Audit (CRO Specialist role)

### Step 1 — BQ query: LP performance last 7 days

```sql
WITH hs AS (
  SELECT lead_utm_campaign,
         SUM(leads_total)      AS leads,
         SUM(leads_qualified)  AS sqls
  FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
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
  FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily` c
  LEFT JOIN hs h
    ON LOWER(c.campaign_name) = LOWER(h.lead_utm_campaign)
  WHERE c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
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

### Step 2 — Write to Google Sheet

Sheet ID: `120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg`
Tab name: `LP-{YYYY-MM-DD}` (today's date). Overwrite if tab exists.

Columns: destination_url | sample_campaign | spend_usd | clicks | impressions | leads | sqls | cvr_pct | cpql_usd

Sort: leads DESC.

### Step 3 — Create Asana LP draft task

```
Title: LP Weekly Review — {YYYY-MM-DD}

Weekly LP performance for the 7 days ending {date}.

| LP URL | Leads | SQLs | CVR% | CPQL |
|--------|-------|------|------|------|
[top 10 rows from BQ]

Full data: {Google Sheet link}

Flags:
- CPQL > $85: [list or "none"]
- CVR% < 1%: [list or "none"]
- 0 leads this week: [list or "none"]

Action: CRO Specialist to review and update test backlog.

---
Created: {date} | Due: {date+3d} | Priority: Normal | Type: Review | Channel: All | Asset level: LP
```

Leave as **DRAFT**. No Slack post for this phase.

---

## Phase 2 — Performance Summary (AI Orchestrator role)

### Step 4 — BQ query: 7d vs prior 7d per channel

```sql
SELECT
  channel,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
           THEN spend END)       AS spend_curr,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
            AND date < DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
           THEN spend END)       AS spend_prior,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
           THEN leads_total END) AS leads_curr,
  SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
           THEN qualified END)   AS sqls_curr,
  ROUND(SAFE_DIVIDE(
    SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
             THEN spend END),
    NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                    THEN qualified END), 0)
  ), 0) AS cpql_curr,
  ROUND(SAFE_DIVIDE(
    SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
              AND date < DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
             THEN spend END),
    NULLIF(SUM(CASE WHEN date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
                    AND date < DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                    THEN qualified END), 0)
  ), 0) AS cpql_prior
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
GROUP BY channel
ORDER BY spend_curr DESC
```

Flag each channel: ✅ CPQL < $85 | ⚠️ $85–$130 | 🔴 > $130.

### Step 5 — Task velocity from Asana

From Asana: count tasks created this week vs completed. Flag if completion rate < 70% OR any approval pending > 48h.

### Step 6 — Month-end forecast

```sql
SELECT
  channel,
  ROUND(SUM(spend) / 7 * 30, 0)    AS projected_month_spend,
  ROUND(SUM(leads_total) / 7 * 30)  AS projected_month_leads,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)), 0) AS cpql_7d
FROM `angular-axle-492812-q4.qoyod_marketing.paid_channel_daily`
WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
GROUP BY channel
ORDER BY projected_month_spend DESC
```

### Step 7 — Post to Slack

Post to `SLACK_CHANNEL_NOTIFY`:

```
*Nexa Weekly Review — {Mon date} to {Sun date}*  |  {DASHBOARD_URL}

PERFORMANCE vs PRIOR WEEK
| Channel | Spend | Leads | CPQL | Δ CPQL |
{rows — ✅ <$85 | ⚠️ $85–$130 | 🔴 >$130}

TASK VELOCITY: {N} created / {N} completed  ·  Approval backlog: {N} items
MONTH-END FORECAST: ${spend_proj} spend · {leads_proj} leads · ${cpql_proj} CPQL

LP REVIEW: Sheet updated — {sheet_link}
```

Escalate to Asana task if: any channel CPQL > $130, or any approval pending > 48h.

---

## Hard rules

- LP phase runs first. Slack post only after both phases complete.
- CPQL before CPL. 7d vs prior 7d always.
- Leads from `hubspot_leads_module_daily` via `paid_channel_daily` (pre-joined, pre-aggregated).
- Never execute pause/scale from this task — analysis and review only.
- No `railway run`, no local paths, no CLI — MCP connectors only.

## Done means

LP Google Sheet tab written + Asana LP draft created. Performance summary posted to Slack. Any escalation flags routed to Asana.
