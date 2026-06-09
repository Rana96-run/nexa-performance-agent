---
name: finding_pmax-custom-params-not-set-in-clone
description: PMax campaign clone script set tracking template placeholders but never wrote their values — all PMax UTMs were blank strings
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `scripts/clone_pmax_sectors.py` set a tracking template with `{_campaign}` and `{_assetgroup}` placeholders but never called the API to set those custom parameters at the campaign and asset group levels. Every PMax click rendered UTM params as empty strings — `utm_audience=` and `utm_campaign=` were blank — making adset-level HubSpot attribution completely dead for all 5 PMax sector campaigns.

Source: Session 80e55918 — confirmed by querying ad data: ads with spend had 0 lead matches while non-spending ads had leads; placeholder values in URLs were the root cause.

Impact: All PMax sector campaign leads came into HubSpot with no `utm_audience` and no `utm_campaign`. They could not be joined back to the right asset group. Lead attribution at adset grain was dead for these campaigns.

Fix / How to handle: The clone script now sets `campaign_criterion_url_custom_parameter` for `_campaign` at campaign level, and the same for `_assetgroup` at asset group level, as part of the creation flow. Always verify tracking template custom params are actually written, not just referenced.
