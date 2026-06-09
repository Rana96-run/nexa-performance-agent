---
name: learning_railway-redeploy-startup-catchup
description: Railway redeployment can miss nightly collector window — operational_scheduler startup must check for stale data and trigger immediate catch-up
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: Railway redeploys kill the running container. If a redeploy happens between the start of the nightly window (05:00 UTC = 08:00 KSA) and the next scheduled tick, that night's data collection is silently skipped. The dashboard then shows stale data until the next scheduled run (up to 24h later).

Outcome: After redeployments, `paid_channel_daily` was 1–2 days stale because the catch-up mechanism only existed in the freshness watcher, not the scheduler startup.

Pattern: The operational_scheduler startup should check if `paid_channel_daily` max_date is more than 1 day behind. If yes, run BQ refresh immediately in the background. This way redeployments self-recover within minutes instead of waiting 24h.

Applies to: Any Railway-hosted scheduler with a nightly window; any future scheduled job that must not miss a tick.
