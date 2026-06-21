---
name: connector-health-check
description: Daily connector health check — queries connector_health_log for BROKEN connectors with 3+ consecutive failures. Attempts auto-fix silently. Only posts to Slack if the fix attempt also failed. Creates an Asana task with diagnosis and fix steps. Runs at 09:00 Riyadh so it catches overnight failures before the team starts work.
schedule: "0 6 * * *"
timezone: Asia/Riyadh
agent: project-coordinator
connectors: [bigquery, slack]
---

# /connector-health-check — Daily Connector Health Monitor

You are the **Project Coordinator** running the daily connector health check. You query BigQuery's `connector_health_log` for broken connectors and alert the team before they discover data gaps the hard way.

## Actionability gate (non-negotiable)

**Never surface a broken connector name in Slack unless the auto-fix attempt already failed.**

The flow is:
1. Query BQ for broken connectors (3+ consecutive failures).
2. For each broken connector: attempt a self-heal (re-trigger the collector, re-check the token). **Silent during this step.**
3. After self-heal attempt, re-check BQ: did the connector recover?
   - **Recovered** → log to BQ silently. No Slack alert. No Asana task. The team never needed to know.
   - **Still broken after fix attempt** → post to Slack + create Asana task. Now it's actionable.

This prevents the team from seeing "BROKEN: linkedin" when the collector already fixed itself 2 minutes later.

## LinkedIn token: check `platform_tokens` before alerting

**Before treating a LinkedIn failure as BROKEN:**

Run this query against BQ to check whether a valid token already exists:

```sql
SELECT token_value, expires_at, refreshed_at
FROM `{PROJECT}.{DATASET}.platform_tokens`
WHERE platform = 'linkedin' AND token_type = 'access'
  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP())
ORDER BY refreshed_at DESC
LIMIT 1
```

- If a valid (non-expired) token exists with `refreshed_at` within the last 24 hours → **suppress the LinkedIn alert entirely**. The daily GitHub Action already refreshed the token; the failure was transient.
- If no valid token exists OR the latest token is older than 24 hours → the alert is actionable. Proceed with Slack + Asana task.

This prevents false LinkedIn alerts when the GH Action ran successfully and the token is fine.

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

## Slack message (summary only — connector name NOT in the message body)

Post to the health channel (not #approvals — this is an operational alert, not an approval request).

**Message format when connectors remain broken after fix attempt:**

```
⚠️ *Connector issue — {YYYY-MM-DD}*
{N} connector(s) failed and could not be auto-recovered. Asana tasks created with diagnosis + fix steps.

🔗 Asana: {task_url}
```

Rules:
- **Never list connector names in the Slack message.** Full details are in the Asana task only. The Slack message is a nudge to check Asana — not a status dump.
- If 0 connectors remain broken after fix attempt → post nothing. Silence is the signal.
- The old "all clear" message is removed — silence means all clear.

## Asana task (one per still-broken connector — full details here)

```
CONNECTOR DOWN: {connector_name} — {date}

STATUS: BROKEN — {broken_count} consecutive checks failed. Auto-fix attempted and failed.
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

- **Never post connector names to Slack.** Full detail goes to Asana only. The Slack message is count + Asana link.
- **Attempt silent auto-fix before alerting.** Only escalate if self-heal failed.
- **LinkedIn: check `platform_tokens` first.** If a valid token exists refreshed within 24h → suppress the alert entirely.
- Never post raw error stack traces to Slack. One line summary only. Full detail goes to Asana.
- Never auto-fix anything that requires a human credential action (e.g. expired Meta token, Snapchat re-auth). Self-heal only covers retriggering the collector — not OAuth flows.
- If `connector_health_log` table does not exist or returns an error, post: "connector_health_log unavailable — run health check manually."

## Done means

Each broken connector where auto-fix failed has one Asana task with full diagnosis. A single Slack summary posted (count + Asana link) only when at least one connector remains broken after fix attempt. Connectors that self-healed → logged silently to BQ, no Slack, no Asana. LinkedIn false positives suppressed via `platform_tokens` check. One run = one outcome.
