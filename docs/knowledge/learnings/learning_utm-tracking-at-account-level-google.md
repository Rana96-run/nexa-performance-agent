---
name: learning_utm-tracking-at-account-level-google
description: "Google Ads UTM tracking is at account level — checking campaign-level for UTM suffix triggers false \"missing UTM\" and causes double UTM parameters"
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: Google Ads (both accounts) has UTM tracking at the customer (account) level via `customer.tracking_url_template` + `customer.final_url_suffix`. All campaigns inherit both. On 2026-05-20 the daily audit flagged 3 compliance campaigns as "missing UTM suffix" because campaign-level was empty. The fix applied `STANDARD_UTM_SUFFIX` at campaign level, causing duplicate UTMs in click URLs (utm_campaign twice). Reverted.

Outcome: Broken UTM double-counted campaign param; audit logic was wrong.

Pattern: Before flagging "missing UTM" — check `customer.final_url_suffix` AND `customer.tracking_url_template` at ACCOUNT level first. If either is set, campaigns inherit. Only set campaign-level `final_url_suffix` if account-level is unset OR a genuinely different tracking is needed. Microsoft Ads tracks at CAMPAIGN level — different from Google.

Applies to: Any UTM audit or compliance check on Google Ads campaigns.
