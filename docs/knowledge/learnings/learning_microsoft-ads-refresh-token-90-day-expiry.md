---
name: learning_microsoft-ads-refresh-token-90-day-expiry
description: Microsoft Ads refresh tokens expire after 90 days of inactivity — add calendar reminder; other platforms are perpetual
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: Google Ads, Snapchat, TikTok (Marketing API), and HubSpot tokens are effectively perpetual (revoked only by explicit rotation or app suspension). Microsoft Ads `msads.manage` refresh tokens expire after 90 days of inactivity, or when the user changes their password. The `MS_CLIENT_SECRET` (the Azure app credential) also has its own separate expiry date set in Azure portal → Certificates & secrets.

Outcome: The second Microsoft Ads account (`MS_REFRESH_TOKEN_2`) expired and caused 400 errors in health checks.

Pattern: (1) Add a calendar reminder for 80-day Microsoft Ads token re-auth. (2) Check Azure portal → App registrations → Certificates & secrets for the client secret expiry date. (3) The health_check.py `check_microsoft_ads()` should report per-account pass/fail (`1/2 OK`) rather than failing the whole check when one token expires.

Applies to: Microsoft Ads collector, health_check.py, any future OAuth token with a documented expiry.
