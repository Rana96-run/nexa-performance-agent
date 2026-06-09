---
name: learning_channel-label-mismatch-join
description: campaigns_daily.channel and lead_utm_source use different tokens — normalize both sides through a CASE map before joining for CPQL
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: Joining spend (`campaigns_daily.channel`) to leads (`hubspot_leads_module_daily.lead_utm_source`) on a naive LOWER() equality splits each paid channel into two rows (spend with null leads + leads with null spend) → CPQL uncomputable. The two sides use different tokens: `campaigns_daily`: `google_ads`, `microsoft_ads`, `meta`, `snapchat`, `tiktok`. `lead_utm_source`: `google`, `bing`, `meta`/`facebook`/`instagram`, `snapchat`, `tiktok`.

Outcome: All CPQL values became NULL/uncomputable for Google and Microsoft until the map was applied.

Pattern: Normalize BOTH sides through the same CASE map (google_ads|google→google, microsoft_ads|bing→bing, facebook|instagram→meta) before the FULL OUTER JOIN on (period, channel). Also: leads-side utm_source has a long organic/AI tail (chatgpt.com, perplexity, direct) — keep them visible but only the 5 paid channels carry a CPQL.

Applies to: Any by-channel CPQL comparison joining spend to leads on the channel dimension.
