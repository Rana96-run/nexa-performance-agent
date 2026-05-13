## How to read this tab

This tab shows **deal performance per HubSpot pipeline**, scoped to **paid attribution only**
(deals where `qoyod_source` IN: Google Ads, Meta Ads, Snapchat Ads, Tiktok Ads, Microsoft Ads, LinkedIn Ads).

### Two ROAS measures

We report two ROAS values because they answer different business questions:

**🟢 New Business ROAS** — *includes Sales Pipeline + Bookkeeping + Qflavours*
> "How much new acquisition + bookkeeping revenue did paid marketing drive in the period?"
> This is the conservative "marketing-driven new revenue" measure. Excludes renewals and non-core pipelines.
> **Matches our existing internal report.**

**🟡 All Paid ROAS** — *includes every pipeline*
> "How much total revenue did paid-attributed customers generate, including renewals?"
> Captures the full revenue impact of paid-acquired customers across their lifecycle,
> including renewals from previously paid-acquired accounts.

### Which pipelines count where

| Pipeline | New Business ROAS | All Paid ROAS |
|---|---|---|
| Sales Pipeline | ✅ | ✅ |
| Bookkeeping | ✅ | ✅ |
| Qflavours | ✅ | ✅ |
| Renewal Bookkeeping | ❌ | ✅ |
| Renewal | ❌ | ✅ |
| Partnerships Revenue | ❌ | ✅ |
| QoyodK | ❌ | ✅ |
| Qoyodk - Retention | ❌ | ✅ |
| SDR Offline Sales | ❌ | ✅ |
| Growth CS | ❌ | ✅ |
| renewal 1 | ❌ | ✅ |
| Partnerships | ❌ | ✅ |
| Unresponsive Leads Follow-up | ❌ | ✅ |
| Pos Orders | ❌ | ✅ |
| Enterprise Sales | ❌ | ✅ |

### Date logic
- **All deals** (Won / Open / Lost) counted by `createdate` (Riyadh, UTC+3)

This matches the deal's entry into the pipeline, not when it closed — so ROAS, pipeline counts, and amounts all answer *"what did marketing spend in this period generate as pipeline?"*
