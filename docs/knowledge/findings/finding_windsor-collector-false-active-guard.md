---
name: finding_windsor-collector-false-active-guard
description: Windsor returns 0 rows silently when API key is blank — would have set windsor_active=True and blocked all 6 direct collectors
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: A guard was added to `reporting_scheduler.py` to skip direct channel collectors when Windsor succeeded (`windsor_active = True`). Windsor returns 0 rows silently when `WINDSOR_API_KEY` is blank/unset (does not throw). This would have set `windsor_active = True` and blocked all 6 direct campaign-level collectors — Google Ads, Meta, Snapchat, TikTok, Microsoft Ads, LinkedIn — from running, causing total data loss.

Source: Session c78afcf1 — discovered while auditing the overlap guard logic.

Impact: Potential for complete data loss if the guard had shipped to production. All paid channel data would stop updating silently.

Fix / How to handle: The Windsor overlap guard was reverted. Windsor is not an active collector — `WINDSOR_API_KEY` was always blank. The correct pattern for any "did collector X succeed?" check: verify row count > 0, not absence of exception.
