---
name: HubSpot deal amounts in BQ are USD (verified — do NOT divide)
description: Collector converts SAR to USD at write time; BQ amount_won/amount_total are USD; do not divide by 3.75 in dashboards or queries
type: project
originSessionId: 80e55918-48dd-4da3-b2d4-4cc3935be856
---

**`hubspot_deals_daily.amount_total`, `amount_won`, and `amount_lost` are USD.**
The collector (`collectors/hubspot_deals_bq.py`) calls `to_usd(amount, deal_currency_code)`
at write time, dividing SAR amounts by 3.75 (the peg in `config.USD_SAR_PEG`).
The original SAR values are preserved in `*_native` columns for audit.

**Verified directly from HubSpot API on 2026-05-09:**
- Deal `499825686757` ("مؤسسة عجوة نخلة")
- HubSpot raw `amount` = 12,255, `deal_currency_code` = `'SAR'`
- BQ `amount_won` = $3,268, `amount_won_native` = SAR 12,255
- Math: 12,255 ÷ 3.75 = 3,268 ✓
- Cross-channel total for Google Ads / Sales Pipeline / 04-10 → 05-09:
  HubSpot SUM(amount) = SAR 300,573, BQ `amount_won_native` = SAR 293,913 (98% match,
  4 deals missing in BQ — small backfill drift), BQ `amount_won` = $78,376.79.

**Use deal/revenue columns AS-IS:**
- Spend → USD (already converted at ad-platform collectors)
- Deal/revenue → USD (already converted at HubSpot collector)
- ROAS = revenue_won / spend → unitless

**Do NOT add `/ 3.75` anywhere downstream.**

Downstream views all inherit USD:
- `paid_channel_campaign_daily.deal_amount`
- `paid_channel_daily.deal_amount`
- `v_adset_performance.revenue_won`
- `v_ad_performance.revenue_won`
- `channel_roas_daily.amount_total` / `revenue_won`

**Why this got confused before (2026-05-08 → 2026-05-09):**
Hex dashboard numbers were compared against Funnel/Looker, which displays in SAR.
Hex's USD numbers looked ~3.75× smaller, so a "fix" was added to divide by 3.75
in dashboard SQL — but that was double-converting USD into a SAR-shaped number that
matched Funnel's SAR display by coincidence. Direct HubSpot API check proved the
collector was correct all along. The `/ 3.75` was reverted across all Hex SQL and
`analysers/campaign_health.py` on 2026-05-09.

**If you ever doubt this again:** run a single deal through the API and compare to
BQ's `amount_won` and `amount_won_native` — the math is deterministic.
