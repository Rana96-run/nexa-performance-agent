---
name: connector-health-check
description: Daily connector health check — queries connector_health_log for BROKEN connectors with 3+ consecutive failures, posts a Slack alert per broken connector, and creates an Asana task with the diagnosis and fix steps. Runs at 09:00 Riyadh so it catches overnight failures before the team starts work.
schedule: "0 6 * * *"
timezone: Asia/Riyadh
agent: project-coordinator
connectors: [bigquery, slack]
---

# /connector-health-check — Daily Connector Health Monitor

You are the **Project Coordinator** running the daily connector health check. You query BigQuery's `connector_health_log` for broken connectors and alert the team before they discover data gaps the hard way.

## What this skill does

1. Queries `connector_health_log` for connectors with 3+ consecutive BROKEN checks
2. For each broken connector: posts a Slack alert + creates an Asana task with diagnosis
3. Posts a clean "all clear" message if everything is healthy
4. Never posts per-connector detail to Slack — only summary + link to Asana

## BQ query — broken connectors

```sql
WITH recent_checks AS (
  SELECT
    connector_name,
    status,
    error_message,
    checked_at,
    ROW_NUMBER() OVER (PARTITION BY connector_name ORDER BY checked_at DESC) AS rn
  FROM `{PROJECT}.{DATASET}.connector_health_log`
  WHERE checked_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
),
consecutive_broken AS (
  SELECT connector_name, COUNT(*) AS broken_count, MAX(checked_at) AS last_checked,
         MAX(error_message) AS latest_error
  FROM recent_checks
  WHERE status = 'BROKEN'
    AND rn <= 5  -- check last 5 runs per connector
  GROUP BY connector_name
  HAVING COUNT(*) >= 3
)
SELECT cb.*, 
       (SELECT checked_at FROM recent_checks r2
        WHERE r2.connector_name = cb.connector_name AND r2.status != 'BROKEN'
        ORDER BY r2.checked_at DESC LIMIT 1) AS last_healthy_at
FROM consecutive_broken cb
ORDER BY broken_count DESC
```

## Slack message (one per broken connector)

Post to the notify channel (not #approvals — this is an operational alert, not an approval request):

```
*Connector down: {connector_name}*

{broken_count} consecutive failures — last healthy {time_since_healthy} ago
Latest error: `{latest_error}`

Asana task created with diagnosis + fix steps. See task for details.
```

If no connectors are broken, post one message:
```
✓ All connectors healthy — {N} checked, 0 failures
```

## Asana task (one per broken connector)

```
CONNECTOR DOWN: {connector_name} — {date}

STATUS: BROKEN — {broken_count} consecutive checks failed
Last healthy: {last_healthy_at} ({time_since} ago)
Latest error: {latest_error}

CONNECTOR DETAILS:
{connector_name} feeds into: [state what data this connector provides to BQ — e.g. "Google Ads spend, impressions, clicks → campaigns_daily" or "HubSpot leads → hubspot_leads_module_daily"]

IMPACT:
If {connector_name} is down, the following are stale in BQ:
{list the tables this connector feeds}

DIAGNOSIS STEPS:
1. Check Railway logs for the collector that writes from {connector_name}
   → go to https://nexa-web-production-6a6b.up.railway.app and check runtime logs
2. Check the OAuth token — many failures are expired tokens
   → Token location: Railway env vars → {connector_name}_ACCESS_TOKEN or similar
3. Check the platform status page for {connector_name} (outage may be on their side)
4. If token expired: refresh via `railway run python scripts/refresh_token.py --connector {connector_name}`
   or follow the auth flow documented in .claude/skills/README.md

FIX CHECKLIST:
- [ ] Token refreshed or root cause identified
- [ ] Connector re-run manually and returned OK status
- [ ] BQ table updated (check row count for today's date)
- [ ] connector_health_log shows HEALTHY on next check

Created: {date}
Due: {date} (same day — connectors blocked = stale data)
Priority: High
Type: Incident
Channel: {connector_name}
Asset level: connector
Action: fix → [Project Coordinator]
```

## Known connector → table mapping

Use this to fill in the impact section:
- `google_ads` → `campaigns_daily`, `ads_daily`, `keyword_view`, `search_term_view`
- `meta` → `campaigns_daily`, `ads_daily`
- `snapchat` → `campaigns_daily`, `ads_daily`
- `tiktok` → `campaigns_daily`, `ads_daily`
- `linkedin` → `campaigns_daily`, `ads_daily`
- `microsoft_ads` (Bing) → `campaigns_daily`, `ads_daily`, `keyword_view`
- `hubspot` → `hubspot_leads_module_daily`, `hubspot_deals_daily`

If the connector name doesn't match the above, use the connector name itself to infer.

## Hard rules

- Never post raw error stack traces to Slack. One line summary only. Full detail goes to Asana.
- Post the clean "all clear" only once per day — if this skill runs multiple times (re-run), only post if status changed since the last post.
- Never auto-fix anything. This skill diagnoses and alerts — humans fix.
- If `connector_health_log` table does not exist or returns an error, post: "connector_health_log unavailable — run health check manually."

## Done means

Each broken connector has a Slack alert posted AND an Asana task created. All-clear message posted if no connectors broken. One run = one outcome.
