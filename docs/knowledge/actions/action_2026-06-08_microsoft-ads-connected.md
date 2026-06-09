---
name: action_2026-06-08_microsoft-ads-connected
description: "Microsoft Ads connected as 6th paid channel — Azure AD service principal unlock + 3 REST API bug fixes + YTD backfill 9,346 rows"
metadata: 
  node_type: memory
  type: action
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was done: (1) qoyod.com Global Admin ran `New-MgServicePrincipal -AppId "d42ffc93-c136-491d-b4fd-6f18168c68fd"` to provision Microsoft Advertising API in the Azure AD tenant. (2) OAuth flow ran with `@qoyod.com` work account using `/common/` endpoint. (3) Fixed 3 collector REST API bugs (wrong URL path, missing `Type` field, per-report status column names). (4) YTD backfill: 534 + 993 + 7,819 rows = 9,346 rows across campaign/adgroup/keyword grains.

Date: 2026-06-08

Trigger: Original auth was blocked by AADSTS650052 for multiple sessions.

Expected outcome: campaigns_daily and sub-grain tables populated for Microsoft Ads from Jan 2026.

Actual outcome: 119 days of campaign data, 119 days of adgroup/keyword data, ads YTD backfill completed. MS Ads now reports alongside Google, Meta, Snap, TikTok, LinkedIn.

Follow-up: Add 80-day calendar reminder for MS_REFRESH_TOKEN re-auth. Check Azure app → Certificates & secrets expiry. Two accounts: G1206XJR (rana.khalid@qoyod.com) and G145REZA (separate account).

[[finding_microsoft-ads-azure-ad-service-principal]]
[[learning_microsoft-ads-refresh-token-90-day-expiry]]
