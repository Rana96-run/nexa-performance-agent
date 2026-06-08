---
name: live-bq-and-cte
description: Never report without live BQ; pre-aggregate hubspot_leads_module_daily in a CTE before joining to spend, or CPQL fans out
metadata:
  type: critical
---

Never report a number without pulling live BQ. When joining leads to spend,
pre-aggregate `hubspot_leads_module_daily` in a CTE first (`SUM(leads_total)`,
`SUM(leads_qualified)` GROUP BY date, lead_utm_campaign), then LEFT JOIN on
`LOWER(campaign_name)=LOWER(lead_utm_campaign)`. Direct join fans out spend.

**Why:** stale recollection and spend fan-out are the two ways CPQL silently goes
wrong — and CPQL is the number every decision keys off.

**How to apply:** leads/SQLs from `hubspot_leads_module_daily` only; CPQL before
CPL; no streaming inserts; reconcile BQ↔HubSpot on a 7-day sample after any change.
