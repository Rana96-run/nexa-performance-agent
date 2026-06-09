---
name: finding_tiktok-marketing-api-auth-domain
description: TikTok Marketing API OAuth uses business-api.tiktok.com — not business.tiktok.com; Marketing API tokens are perpetual (no expiry)
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: TikTok has 3 separate OAuth endpoints: `business-api.tiktok.com/portal/auth` (Marketing API — ads data), `business.tiktok.com/portal/auth` (Business Center UI access only), `tiktok.com/v2/auth/authorize/` (Login Kit for consumer apps). The original script used the middle one, which resulted in a redirect to a "not-found" page.

Also: TikTok Marketing API access tokens are **perpetual** (no expiry, no refresh needed) — different from Login Kit which has 24h access / 365d refresh.

Source: Session d8436485 — TikTok OAuth setup.

Impact: OAuth flow failed until the correct domain was used. Script docstring claiming "24h/365d" was wrong for Marketing API.

Fix / How to handle: Marketing API apps (19-digit numeric app_id format) must always use `business-api.tiktok.com/portal/auth`. There is no token refresh for Marketing API — if a token is revoked, full browser re-auth is required. Add health check calling `/oauth2/advertiser/get/` daily to detect revocation early.

[[action_tiktok-connected-perpetual-token]]
