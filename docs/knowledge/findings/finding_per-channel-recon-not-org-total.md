---
name: finding_per-channel-recon-not-org-total
description: "Org-wide reconciliation total is worthless — Google Ads dominates and masks 2x over-counts on Meta, Snapchat, TikTok; always reconcile per-channel"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: After a fan-out fix, the 14-day aggregate reconciliation passed (1585 ≤ HubSpot 1843) but per-channel it was still 2x wrong. Google Ads is the largest and clean channel — it dominated the total and masked 2x over-counts on Meta, Snapchat, TikTok, Microsoft. Only when per-channel recon ran did the real issue surface.

Source: 14_learning_patterns.md 2026-06-09 entry; 08_pitfalls.md per-channel recon section.

Impact: False "done" declaration on a fan-out fix; wrong CPQL data in dashboards for weeks.

Fix / How to handle: The bar for "reconciliation passed" is ratio ≤ 1.05 on EVERY paid channel (google/meta/snapchat/tiktok/microsoft_ads) separately — not just the org total. Use: map qoyod_source→channel slug, sum `leads_total` per channel from `hubspot_leads_module_daily`, compare to per-channel `SUM(leads)` from the view for the SAME window.
