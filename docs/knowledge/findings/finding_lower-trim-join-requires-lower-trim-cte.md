---
name: finding_lower-trim-join-requires-lower-trim-cte
description: A LOWER(TRIM) join demands a LOWER(TRIM)-grouped CTE on the right side — raw casing on the CTE causes fan-out even before downstream views
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `utm_paid_attribution_daily.spend_campaign` grouped by RAW `campaign_name`, but the leads joins matched on `LOWER(TRIM(...))`. Snapchat runs two casing variants of the same campaign name — the two raw spend rows both matched one HubSpot lead bucket, doubling the leads count at the upstream source (148→172) before any downstream view touched it.

Source: memory/14_learning_patterns.md 2026-06-09 Snapchat root-cause entry.

Impact: Snapchat leads over-counted 1.16x in `utm_paid_attribution_daily` itself. Fixing only downstream views couldn't resolve it.

Fix / How to handle: Whenever a CTE is the right side of a `LOWER(TRIM())` join, that CTE MUST pre-group by the same `LOWER(TRIM())` key. Grouping by raw casing fans the left side. Apply to any campaign/audience/content key feeding a case-insensitive join.

[[finding_per-channel-recon-not-org-total]]
