---
name: finding_tiktok-snap-api-date-chunk-limits
description: TikTok stats API caps at 30 days per query; Meta IG organic caps at 30 days — both silently truncate longer windows
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: TikTok's stats API caps each query at 30 days. Meta's organic IG endpoint caps at 30 days (stricter than Facebook's 93-day cap). Both caused silent truncation — queries for longer windows returned partial data with no error.

Source: Session 98abfa4b — discovered during YTD backfill; without chunking, only 30 days of data appeared despite the query spanning 125 days.

Impact: Any backfill or historical pull without chunking silently returns incomplete data. For 125-day YTD backfills: TikTok needs 5 × 30-day chunks; Meta IG needs multiple 30-day chunks.

Fix / How to handle: Always use `_date_chunks(max_days=30)` for TikTok at all grains (campaign, adgroup, ad). Use 30-day chunks for Meta IG organic (not 90). The `_date_chunks()` helper in the TikTok collector is the canonical pattern.

[[finding_tiktok-api-rejects-campaign-id-at-adgroup]]
