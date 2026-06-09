---
name: finding_linkedin-analytics-fields-param-required
description: "LinkedIn adAnalytics silently omits all fields without explicit fields= param — costInLocalCurrency absent, all spend shows $0"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The LinkedIn `adAnalytics` endpoint silently omits any field not explicitly requested. Without `"fields": "costInLocalCurrency,impressions,clicks,..."` in the call, `costInLocalCurrency` is absent from every row → all spend appears as $0 in BQ. Account had $2,769 YTD real spend but BQ showed $0 for months.

Source: memory/08_pitfalls.md "LinkedIn: MUST pass fields= on adAnalytics".

Impact: All LinkedIn spend silently written as $0; CPQL and ROAS completely wrong for the channel.

Fix / How to handle: Always pass `"fields": "costInLocalCurrency,impressions,clicks,externalWebsiteConversions,dateRange,pivotValues"` on every `adAnalytics` call. In contrast, do NOT pass `fields=` on `adCampaignGroups` or `adCampaigns` — those are rejected without the Restli 2.0 header.
