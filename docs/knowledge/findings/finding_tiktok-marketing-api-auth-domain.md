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

---

## 2026-06-29 — No refresh token; TIKTOK_REFRESH_TOKEN is not a missing-secret gap

**What was confirmed:**

Running `scripts/tiktok_oauth.py` under the current TikTok Developer app config returns a long-lived `access_token` but **no `refresh_token`** — the API response contains no `refresh_token` field and no expiry timestamp. This is consistent with the Marketing API perpetual-token design above.

**Collector and executor behaviour:**

- `collectors/tiktok_bq.py` operates on `TIKTOK_ACCESS_TOKEN` only. It does not read or require `TIKTOK_REFRESH_TOKEN`.
- `executors/tiktok.py` `_refresh_token()` checks for `TIKTOK_REFRESH_TOKEN` and, when the env var is absent, logs and falls back to the access token — no crash, no silent failure.

**Conclusion — do not flag as missing secret:**

`TIKTOK_REFRESH_TOKEN` is intentionally absent from `.env`, GitHub Secrets, and Railway. Do **not** flag it as a missing-secret gap in hygiene scans or env-var audits. The collector is fully functional without it.

If refresh-token resilience is ever needed, the TikTok app must be reconfigured for Standard Access with refresh-token issuance, then the OAuth flow re-run.

**2026-06-29 re-auth:** `TIKTOK_ACCESS_TOKEN` was re-authed fresh and propagated to `.env`, GitHub Secrets, and Railway.
