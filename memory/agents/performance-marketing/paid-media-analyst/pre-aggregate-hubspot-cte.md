---
name: pre-aggregate-hubspot-cte
description: Pre-aggregate hubspot_leads_module_daily in a CTE before joining to campaigns_daily, else spend fans out and CPQL is wrong
metadata:
  type: critical
---

Never JOIN `campaigns_daily` directly to `hubspot_leads_module_daily`. Multiple
HubSpot rows per (date, campaign) multiply spend by the match count → inflated
spend → wrong CPL/CPQL. Always pre-aggregate HubSpot in a CTE first
(`SUM(leads_total)`, `SUM(leads_qualified)` GROUP BY date, lead_utm_campaign),
then LEFT JOIN on `LOWER(campaign_name)=LOWER(lead_utm_campaign)`.

**Why:** spend fan-out is invisible in totals but corrupts per-campaign CPQL,
which is the number every decision keys off.

**How to apply:** use the CTE template in the playbook. Leads/SQLs come ONLY from
`hubspot_leads_module_daily` — never `campaigns_daily.leads`.
