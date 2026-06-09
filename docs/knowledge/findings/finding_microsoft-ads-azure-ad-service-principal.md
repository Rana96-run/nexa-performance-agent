---
name: finding_microsoft-ads-azure-ad-service-principal
description: "Microsoft Ads API has 3 distinct OAuth failure modes — AADSTS650052, PersonalIdentityMigratedToWork, AADSTS500200 — all require Global Admin fix"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Three distinct failure modes for Microsoft Ads OAuth:
1. `AADSTS650052` — Microsoft Advertising API service principal doesn't exist in the Azure AD tenant. Fix: run `New-MgServicePrincipal -AppId "d42ffc93-c136-491d-b4fd-6f18168c68fd"` as a Global Admin.
2. `PersonalIdentityMigratedToWork` — when a personal MSA (outlook.com) account has been migrated into an Azure AD work account by Microsoft, it's permanently blocked for API use via personal flow.
3. `AADSTS500200` — the Bing Ads account is locked to an Azure AD tenant; personal Microsoft accounts are refused even after invitation.

The fix: (1) Global Admin runs `New-MgServicePrincipal`, (2) OAuth with work `@qoyod.com` account using `/common/` endpoint, (3) invite work account as Super Admin in ads.microsoft.com.

Source: Session d8436485.

Impact: Microsoft Ads blocked for multiple sessions; data gap in campaigns_daily.

Fix / How to handle: Microsoft Ads requires a `qoyod.com` work account + service principal in the Azure AD tenant. The `New-MgServicePrincipal` command (Global Admin required, one-time) is the single unlock. Keep `MS_REFRESH_TOKEN` empty in Railway while account is paused — the collector's early-return guard fires in <5ms instead of failing in 30s. See `memory/02_credentials.md`.
