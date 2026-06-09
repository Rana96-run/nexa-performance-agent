---
name: action_2026-06-08_tiktok-connected
description: "TikTok Marketing API connected with perpetual access token — both ad accounts authorized, 56 rows landed on first run"
metadata: 
  node_type: memory
  type: action
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was done: Fixed OAuth script to use correct domain (`business-api.tiktok.com`). Added `http://localhost:8080/tiktok/callback` to Advertiser redirect URIs in TikTok Developer Portal. Ran OAuth, minted perpetual 40-char access token. Verified both accounts: Qoyod 2024 (7304642840767021057, Asia/Riyadh) and Qoyod 2025 (7565475813811093521, Asia/Kuwait). 56 rows landed in campaigns_daily on first collector test.

Date: 2026-06-08

Trigger: TikTok collector was in codebase but no access token was set.

Expected outcome: TikTok campaign/adset/ad data flowing to BQ.

Actual outcome: Working. Adset/ads sub-collectors wired in reporting_scheduler.py. Token is perpetual — no refresh needed.

Follow-up: Standardize both TikTok accounts to Asia/Riyadh timezone in TikTok UI (Qoyod 2025 is currently Asia/Kuwait). Add health check calling TikTok `/oauth2/advertiser/get/` daily to detect token revocation early — full browser re-auth required since no refresh path exists.

[[finding_tiktok-marketing-api-auth-domain]]
[[finding_tiktok-two-accounts-different-timezones]]
