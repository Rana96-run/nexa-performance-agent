# channel label mismatch: campaigns_daily vs leads utm_source

When joining spend (`campaigns_daily.channel`) to leads (`hubspot_leads_module_daily.lead_utm_source`)
on channel for a by-channel CPQL comparison, the two sides use DIFFERENT tokens:

- `campaigns_daily.channel`: `google_ads`, `microsoft_ads`, `meta`, `snapchat`, `tiktok`
- `lead_utm_source`: `google`, `bing`, `meta`/`facebook`/`instagram`, `snapchat`, `tiktok`

A naive `LOWER(channel)=LOWER(lead_utm_source)` join SPLITS each paid channel into two
rows (spend with null leads + leads with null spend) → CPQL is uncomputable. Normalize
BOTH sides through the same CASE map (google_ads|google->google, microsoft_ads|bing->bing,
facebook|instagram->meta) before the FULL OUTER JOIN on (period, channel).

Also: leads-side utm_source has a long organic/AI tail (chatgpt.com, perplexity, direct,
hs_email, *.com referrers, '(none)'). These have no spend and are NOT paid channels — keep
them visible but only the 5 paid channels carry a CPQL.

Established 2026-06-08 during the 7d-vs-prior-7d period comparison.
