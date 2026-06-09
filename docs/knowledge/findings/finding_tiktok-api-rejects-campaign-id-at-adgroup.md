---
name: finding_tiktok-api-rejects-campaign-id-at-adgroup
description: TikTok stats API returns error 40002 when campaign_id is used as a dimension at adgroup or ad level
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: TikTok's stats API returns error 40002 when `campaign_id` is included as a dimension in adgroup-level or ad-level reports. Valid dimensions at those levels are only `adgroup_id`/`ad_id` + `stat_time_day`. Parent IDs are not valid filter dimensions at child grain levels.

Source: Session 98abfa4b — TikTok adgroup and ad collectors returned 0 rows after being built; error 40002 confirmed the cause.

Impact: TikTok adgroup and ad level data was writing 0 rows silently. All adset and ad grain analysis for TikTok was missing.

Fix / How to handle: Fetch a metadata dict (`_list_adgroups()` / `_list_ads()`) per account first, then look up `campaign_id` from that metadata after the stats call. Never include parent IDs as stats dimensions at child levels in TikTok API calls.

[[finding_tiktok-snap-api-date-chunk-limits]]
