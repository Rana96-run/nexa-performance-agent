---
name: finding_google-ads-use-account-id-from-bq
description: "Google Ads multi-account: always use account_id from BQ row to build resource names — config customer_id is only one of the two child accounts"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: `GOOGLE_ADS_CONFIG["customer_id"]` is one child account ID (1513020554), NOT the MCC. Campaigns in the second child account (5753494964) get `RESOURCE_NOT_FOUND` when building resource names with the config CID. Second bug: `add_negative_keywords` returns a list, not int.

Source: memory/08_pitfalls.md "Google Ads multi-account: always use account_id from BQ".

Impact: Keyword actions silently fail on all campaigns in the second child account.

Fix / How to handle: Query `SELECT campaign_name, campaign_id, account_id FROM campaigns_daily` and use `account_id` (not config) to build resource names: `customers/{child_cid}/campaigns/{row.campaign_id}`. Guard return type: `n = result if isinstance(result, int) else len(result)`. Account 5753494964 holds ImpressionShare_Invoice + E-invoice_Test; account 1513020554 holds ZATCAPhase2 + Brand.
