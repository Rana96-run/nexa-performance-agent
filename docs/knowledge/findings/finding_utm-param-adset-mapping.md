---
name: finding_utm-param-adset-mapping
description: utm_medium carries cpc/paid_social — it is NOT the adset name; adset name lives in utm_audience (lead_utm_audience in HubSpot)
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `lead_utm_medium` was mistakenly used as the adset name in join logic. `utm_medium` carries cpc/paid_social — it is NOT an adset name. The adset name lives in `lead_utm_audience`.

Source: memory/08_pitfalls.md "UTM param → ad hierarchy level".

Impact: Ad set-level joins produce no results when joining on `lead_utm_medium` instead of `lead_utm_audience`.

Fix / How to handle: Correct mapping:
- Campaign = `lead_utm_campaign`
- Ad Set / Ad Group = `lead_utm_audience`
- Ad = `lead_utm_content`
- Keyword = `lead_utm_term`
- Source/channel = `lead_utm_source`
- Channel-type = `lead_utm_medium` (cpc/paid_social only)

`v_adset_performance` Strategy B already joins on `lead_utm_audience` correctly.
