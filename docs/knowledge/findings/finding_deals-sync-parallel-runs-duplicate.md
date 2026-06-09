---
name: finding_deals-sync-parallel-runs-duplicate
description: "Two parallel deals collector runs both fire DELETE before either INSERT — results in 1.5-2x duplicate rows, inflated ROAS"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Two `collect_and_write()` calls running near-simultaneously each fired DELETE before either's INSERT completed, so both inserted full row sets — resulting in 1.5–2x more rows than HubSpot for the same window.

Source: memory/08_pitfalls.md "Deals sync — parallel runs duplicate the table".

Impact: `hubspot_deals_daily` shows 2x rows; ROAS and deal amounts inflated in all downstream views.

Fix / How to handle: Never run a manual deals sync without first checking scheduler logs for an in-progress run. If contaminated: TRUNCATE the table, run a single fresh YTD backfill, verify with `COUNT(*) vs COUNT(DISTINCT full_key)` = 1.00x.

[[finding_parallel-deals-sync-duplication]]
