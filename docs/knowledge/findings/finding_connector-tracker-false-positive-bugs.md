---
name: finding_connector-tracker-false-positive-bugs
description: "connector_tracker.py has 3 false-positive patterns — wrong channel labels, WHERE channel= on channel-less tables, BQ exception ≠ data outage"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Three bugs caused healthy connectors to be flagged BROKEN: (1) Wrong channel labels (`google` vs `google_ads`). (2) `hubspot_leads_module_daily`/`hubspot_deals_daily` have no `channel` column — `WHERE channel=` on them causes BQ 400. (3) A BQ query exception (rate limit/timeout) was indistinguishable from genuine data outage (`except Exception` returned `hours_old=9999` → BROKEN). Also: a "corrupt" deal amount was a phone number typed in the Amount field (966504406958 SAR = Saudi phone).

Source: memory/08_pitfalls.md "Connector Police" and "check_freshness — BQ query error".

Impact: Constant false-alarm RED alerts; team stops trusting health monitor.

Fix / How to handle: Split exception path (→ WARNING, not BROKEN) from zero-rows path (→ real BROKEN). `_STALE_HOURS` must be ≥72h. Channel-less tables gate the `WHERE channel=` filter on `table == "campaigns_daily"`. A deal amount >50x 90d median AND matching phone pattern (`_looks_like_phone`) → diagnose as "phone number in Amount field", not data corruption.
