---
name: finding_parallel-deals-sync-duplication
description: Two HubSpot deals syncs running ~1 minute apart caused 1.84x row duplication — DELETE/INSERT races on overlapping date ranges
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Two deals syncs ran ~1 minute apart (manual run overlapped with the 6h scheduler). Each sync's DELETE statement didn't catch the other's INSERT cleanly, resulting in ~1.84× duplicate rows for the overlapping date range. The deduplication check initially passed because it was done with a partial key.

Source: Session 80e55918 — confirmed by BQ→HubSpot reconciliation showing 1.84× factor before truncate + rebuild.

Impact: `hubspot_deals_daily` had duplicate rows. All downstream views (`paid_channel_daily`, `v_adset_performance`, etc.) inherited the duplication. ROAS and deal metrics were ~1.84× inflated.

Fix / How to handle: Never run the deals collector manually while the scheduler is running (or vice versa). Use a collector mutex or process lock. When duplication is suspected: truncate `hubspot_deals_daily` and run a clean YTD rebuild as a single process. Always reconcile BQ vs HubSpot API (7-day sample) after any rebuild — do not declare done without running the reconciliation yourself.

[[finding_deals-sync-parallel-runs-duplicate]]
