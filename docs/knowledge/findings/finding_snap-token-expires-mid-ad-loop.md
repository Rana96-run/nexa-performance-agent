---
name: finding_snap-token-expires-mid-ad-loop
description: Snapchat OAuth tokens expire after 30 minutes — silently fail mid-loop when processing 1000+ ads
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Snapchat access tokens have a 30-minute lifetime. Account 1 has 1,000 ads × 5 date chunks = 5,000 API calls, which takes 1–4 hours. Refreshing the token once per account (outer loop) meant the token expired mid-processing, causing silent API failures for hundreds of ads.

Source: Session 98abfa4b — confirmed by per-account token refresh failing; full backfill returning partial data.

Impact: Snapchat ad-level data for account 2 (136 ads) was always failing due to expired token. Account 1 returned partial data non-deterministically.

Fix / How to handle: Use `time.monotonic()` inside the inner ad loop to track wall-clock elapsed time, and refresh the token proactively every 25 minutes. The refresh must be scoped to the inner loop, not any outer loop boundary. `time.monotonic()` is preferred over `datetime.now()` — unaffected by NTP adjustments or DST transitions.
