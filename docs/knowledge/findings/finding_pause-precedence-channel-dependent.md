---
name: finding_pause-precedence-channel-dependent
description: "Campaign pause must be preceded by surgical cleanup — Social: pause worst ads first; Search: pause worst keywords + LP review first"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Campaign-level pause is never the first action when a campaign hits pause threshold. The surgical surface depends on channel: Social (meta/snapchat/tiktok) → pause bad ADS first. Search (google_ads/microsoft_ads) → pause bad KEYWORDS first AND review the landing page. LP issues masquerade as ad/keyword problems.

Source: memory/08_pitfalls.md "Pause precedence — channel-dependent surgical cleanup".

Impact: Pausing a campaign before surgical cleanup removes all traffic, including from well-performing ads or keywords that could be salvaged.

Fix / How to handle: `campaign_health.py` routes by channel: Social → check ad candidates → downgrade to "drilldown" with top 5 worst ads. Search → check keyword candidates → downgrade to "drilldown" with top 5 worst keywords + LP review instructions (mandatory even if no keywords flagged). `qa/checks.py::check_pause_precedence` gates this at the Asana surface.
