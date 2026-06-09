---
name: finding_snapchat-channel-key-map-wrong-label
description: "v_channel_key_map had 'Snapchat' but HubSpot stores 'Snapchat Ads' — 168 Snapchat leads silently dropped from dashboard"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `v_channel_key_map` mapped the Snapchat key to `'Snapchat'`. HubSpot/BQ stores `lead_qoyod_source = 'Snapchat Ads'`. The JOIN `l.qoyod_source = m.qoyod_source` failed on every Snapchat lead, silently dropping all 168 Snapchat leads. Dashboard showed 795 total leads; correct count was 963.

Source: Session 80e55918 — confirmed by comparing HubSpot API counts per source against BQ; math was exact: `795 + 168 = 963`.

Impact: Snapchat CPL/CPQL showed as infinite/blank (0 leads in denominator). Channel scorecard row showed zero leads. The issue had been silently present since the view was created.

Fix / How to handle: Always verify exact `qoyod_source` string values stored in `hubspot_leads_module_daily` by querying `SELECT DISTINCT lead_qoyod_source FROM hubspot_leads_module_daily` before configuring any channel mapping view. The correct value is `'Snapchat Ads'` (with space and "Ads"). Corrected in `collectors/views.py`.

[[finding_hubspot-qoyod-source-canonical-names]]
