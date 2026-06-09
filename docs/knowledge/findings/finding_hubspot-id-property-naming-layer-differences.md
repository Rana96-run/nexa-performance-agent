---
name: finding_hubspot-id-property-naming-layer-differences
description: "Ad ID property names differ across HubSpot Contact vs Lead Module vs BQ — adgroup is ONE WORD in Lead Module, underscore in Contact"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The ad-group level has 4+ different property names across the stack. HubSpot Contact uses `ad_group_id` (underscore), HubSpot Lead Module uses `lead_adgroup_id_sync` (adgroup as ONE word, no underscore), BQ uses `adset_id`. Using the wrong property on the wrong object returns 400 from HubSpot's API.

Source: memory/08_pitfalls.md "ID property naming — different at every layer".

Impact: HubSpot Search API returns 400 on wrong property name; silent NULL joins in BQ.

Fix / How to handle: Correct mappings by layer:
- Contact: `ad_group_id`, `campaign_id`, `ad_id`
- Lead Module: `lead_adgroup_id_sync`, `lead_campaign_id_sync`, `lead_ad_id_sync`
- Deal: `deal_adgroup_id_sync`, `deal_campaign_id_sync`, `deal_ad_id_sync`
- BQ: `adset_id`, `campaign_id`, `ad_id`

Always match the property name to the object layer before writing API queries.
