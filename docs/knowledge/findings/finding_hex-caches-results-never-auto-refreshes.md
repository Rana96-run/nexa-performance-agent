---
name: finding_hex-caches-results-never-auto-refreshes
description: "Hex caches query results from last notebook run — never auto-refreshes, dashboards drift stale even when BQ is current"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Hex caches query results from the last notebook run. When a published app loads, it shows the cached snapshot — not live BQ data. The reporting_scheduler refreshed BQ every 6h but never triggered a Hex re-run, so dashboards drifted further stale with every pass. Hex was showing May 12 = 63 leads when BQ had 148; after manual re-run Hex showed correct numbers.

Source: Session 98abfa4b.

Impact: Dashboard users saw hours-old or days-old data even when BQ was fully current. Made it impossible to trust "live" dashboard numbers without manual intervention.

Fix / How to handle: After every BQ refresh pass, programmatically trigger a Hex notebook re-run via the Hex API. Both notebooks (Performance + Activity) must be triggered. This is now wired into `reporting_scheduler.py` at the end of every refresh. The Hex project IDs must be UUIDs (not URL slugs) — get them via the Hex API.
