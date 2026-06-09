---
name: finding_campaigns-daily-leads-violation
description: campaigns_daily.leads is channel-reported conversions (page views for traffic campaigns) — NEVER a real lead count
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `campaigns_daily.leads` is ingested verbatim from the ad channel. For WebsiteTraffic-objective campaigns, channels count page views as conversions. Example: Bing_WebsiteTraffic_Search_AR_Generic showed 1,157 "leads" at $1.48 CPL; real HubSpot count was 31 leads, CPQL $190 — worst campaign, should pause. This violation has been caught multiple times across sessions.

Source: CRITICAL_KPI_RULES.md Rule 1; memory/08_pitfalls.md "NEVER use campaigns_daily.leads".

Impact: Leads, CPL, CPQL all wrong. Decisions based on it result in scaling campaigns that should be paused.

Fix / How to handle: All leads/SQLs must come from `hubspot_leads_module_daily`. Pre-aggregate in a CTE first (`SUM(leads_total)`, `SUM(leads_qualified)` GROUP BY date, lead_utm_campaign), then LEFT JOIN on `LOWER(campaign_name)=LOWER(lead_utm_campaign)`. `campaigns_daily` may only supply spend/clicks/impressions/IS. Self-check: scan any new SQL for `SELECT .* leads .* FROM .* campaigns_daily` before running.
