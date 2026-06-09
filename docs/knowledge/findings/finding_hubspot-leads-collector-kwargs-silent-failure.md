---
name: finding_hubspot-leads-collector-kwargs-silent-failure
description: "HubSpot leads collector silently failed 36+ hours — scheduler called with incremental=True but function signature didn't accept **kwargs"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `_hubspot_leads_collector()` was called by the 6h scheduler with `incremental=True` as a keyword argument. The function signature didn't accept `**kwargs`, so it threw a TypeError on every scheduled run. The error was logged to `agent_activity_log` but no Slack alert fired — leads sync failed silently for 36+ hours.

Source: Session 80e55918 — discovered when dashboard showed 63 leads for May 12 instead of 148. `agent_activity_log` showed `collect_hubspot_leads status=failed` twice.

Impact: Zero May 13 leads in BQ; May 12 leads severely undercounted. Dashboard CPL/CPQL for those days were meaningless.

Fix / How to handle: Add `**kwargs` to any collector function that may be called by the scheduler. More importantly: the scheduler should log failures to Slack immediately — not just to `agent_activity_log` which no one reads in real time. The zero-row guard (post to `#notify` when any paid channel writes 0 rows) is the correct safeguard.
