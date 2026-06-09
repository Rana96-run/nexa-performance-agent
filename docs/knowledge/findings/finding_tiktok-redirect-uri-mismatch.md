---
name: finding_tiktok-redirect-uri-mismatch
description: "TikTok app had existing redirect URI qoyod.com/tiktok/callback — local OAuth script used different path, auth rejected"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: TikTok Developer Portal had `https://app.qoyod.com/tiktok/callback` registered as the Advertiser redirect URI. The local OAuth script used `http://localhost:8080/tiktok/callback`. TikTok rejected the auth attempt with "redirect URI mismatch". TikTok has two separate redirect URI fields (Advertiser = Marketing API, TikTok account holder = organic/content) — only the Advertiser field needed updating.

Source: Session d8436485.

Impact: OAuth blocked until redirect URI was added.

Fix / How to handle: Add localhost to the Advertiser redirect URLs list in TikTok Developer Portal. Keep the production URL (`https://app.qoyod.com/tiktok/callback`) — multiple URLs are allowed. For local OAuth scripts always use `http` (no SSL), no trailing slash.
