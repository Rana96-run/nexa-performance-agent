---
name: finding_tiktok-two-accounts-different-timezones
description: "TikTok Qoyod 2024 uses Asia/Riyadh but Qoyod 2025 uses Asia/Kuwait — inconsistent timezone, standardize both to Asia/Riyadh"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: After successful TikTok OAuth, the advertiser list API revealed two accounts: Qoyod 2024 (`7304642840767021057`) with `Asia/Riyadh` and Qoyod 2025 (`7565475813811093521`) with `Asia/Kuwait`. Both are UTC+3 so daily aggregates land on the same calendar day, but hour-of-day analytics will be off.

Source: Session d8436485.

Impact: Low impact for daily reporting; affects intraday hourly analysis.

Fix / How to handle: Standardize both accounts to `Asia/Riyadh` in TikTok UI. The architecture standard is UTC+3 / Asia/Riyadh for all user-facing times (`memory/01_architecture.md`).
