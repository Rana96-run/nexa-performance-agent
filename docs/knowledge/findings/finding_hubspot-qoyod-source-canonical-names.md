---
name: finding_hubspot-qoyod-source-canonical-names
description: "HubSpot lead_qoyod_source exact canonical strings — Tiktok lowercase 'i', Snapchat and Meta include 'Ads' suffix"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `Tiktok Ads` has a lowercase 'i' — NOT `TikTok Ads`. Any mismatch in BQ channel_maps, `QOYOD_SOURCE_TO_CHANNEL` in `channel_inference.py`, or `collectors/views.py` causes leads to silently drop from dashboard joins.

Source: memory/08_pitfalls.md "HubSpot: Canonical lead_qoyod_source internal names".

Impact: All TikTok leads silently invisible in dashboard joins if spelled `TikTok Ads`.

Fix / How to handle: Exact canonical strings (copy-paste exactly):
- `Google Ads`
- `Microsoft Ads`
- `Meta Ads`
- `Snapchat Ads` (not `Snapchat`)
- `Tiktok Ads` (lowercase 'i')
- `LinkedIn Ads`

Use these exact strings everywhere — BQ views, Python channel maps, and any new channel integration.

[[finding_snapchat-channel-key-map-wrong-label]]
