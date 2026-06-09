---
name: finding_multi-account-collector-pool-before-upsert
description: "Multi-account collectors must pool all rows before upsert — per-account upsert wipes the other account's rows for shared key_fields"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `collectors/microsoft_ads_bq.py` looped over accounts and called `upsert_rows()` once per account. Since `key_fields=["date","channel","campaign_id"]` shares `channel='microsoft_ads'` across both accounts, account-2's DELETE-then-INSERT wiped account-1's rows for every overlapping (date, channel) partition. Account 188176729 appeared dormant in BQ even though the API returned real spend.

Source: memory/08_pitfalls.md "Multi-account collectors: pool rows before upsert".

Impact: Silent data loss — entire account's spend missing from BQ; dashboards showed wrong channel totals.

Fix / How to handle: Pool rows from ALL accounts into a single `all_rows: list[dict] = []`, then call `upsert_rows()` ONCE at the end. Apply to all functions within the collector. General rule: any collector iterating over multiple accounts/sub-channels that share `key_fields` MUST aggregate before upserting once.
