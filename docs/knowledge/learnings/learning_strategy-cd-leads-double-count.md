---
name: learning_strategy-cd-leads-double-count
description: Strategy C/D ID-fallback joins in adset/ad performance views caused leads double-counting — removed 2026-06-09
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: `bq_writer.py` had Strategy C (adset-ID fallback) and D (campaign-ID fallback) re-joins to `hubspot_leads_module_daily`. These were added to handle cases where UTM names changed but IDs didn't.

Outcome: They caused double-counting — the fallback joins sprayed campaign-level leads across every adset/ad that shared a campaign_id ON TOP OF the existing UTM-name matches. Snapchat example: 172 true leads → 316 in the view.

Pattern: The upstream `utm_paid_attribution_daily` view already resolves HubSpot leads to the correct grain (date, channel, utm_campaign, utm_audience, utm_content). Joining again by ID creates fan-out. The upstream view is the single authoritative source — don't re-join below it.

Applies to: Any future attempt to add "fallback" ID-based joins to adset or ad performance views. The answer is always to fix the upstream attribution view, not add more joins downstream.

[[project_architecture_bq]]
