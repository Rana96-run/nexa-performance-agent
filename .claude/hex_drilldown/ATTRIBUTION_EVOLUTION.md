# Attribution Evolution — From Funnel-Style Fragmentation to ID-First Reporting

> **TL;DR** — We rebuilt how paid channel attribution flows from HubSpot → BigQuery → dashboards. Renamed campaigns now consolidate into one row, duplicate names separate correctly, phantom-paid leads get auto-recovered, and Google campaign attribution went from **1% → 77%** via gclid resolution.

---

## What changed and why

### Problem 1 — Renamed campaigns split into 2 rows

**Before:** A campaign renamed mid-month produced two rows in dashboards — one with old leads + spend, another with new leads + spend. "Funnel-style" fragmentation.

**Now:** All breakdown views join on `campaign_id` / `adset_id` / `ad_id` first; the name is just a display label. Renames consolidate into one row showing the latest name with full historical data.

---

### Problem 2 — Duplicate-named campaigns merged incorrectly

**Before:** Two different Snapchat campaigns with identical names appeared as a single inflated row (spend + leads doubled but appeared as "one" campaign).

**Now:** `GROUP BY campaign_id` separates them into 2 distinct rows with their own metrics. Verified on the duplicate Snapchat `iPhone_Instantform` campaigns — each now shows its own performance.

---

### Problem 3 — Cross-channel UTM cookie leak

**Before:** A Snapchat Instantform lead with a stale Google UTM cookie got classified as Google Ads. ~382 leads/month misattributed across channels.

**Now:** Snap / Meta / TikTok Instantform leads route by `lead_campaign_id_sync` (the platform's own ID) regardless of UTM cookies. Cookie leak no longer affects channel attribution.

---

### Problem 4 — Phantom-paid leads in Direct / Organic

**Before:** Google ad clicks where the gclid fired late (HubSpot pixel lag) or where the user returned via Direct/Organic after the original click → ~58 Google leads/month classified as Direct Traffic. ~32 Meta leads similar.

**Now:** HubSpot workflow re-enrolls contacts on `hs_google_click_id` and `hs_facebook_click_id` property changes. Reclassifies on the fly. Goal locks paid attribution from being overwritten. **~90 phantom-paid leads/month recovered.**

---

### Problem 5 — Wide deal columns at every grain

**Before:** Campaign / adset / ad breakdown tables showed `deals_won`, `revenue_won`, `roas` (all pipelines) plus `new_biz_*` versions side-by-side. Cluttered, hard to focus on what matters for ad decisions.

**Now:** Breakdown views show only `new_biz_*` (the metric that matters for ad performance: Sales Pipeline + Bookkeeping + Qflavours). Overview/scorecard pages still show both — all-pipeline AND new_biz side-by-side.

---

### Problem 6 — Google campaign attribution depended on UTM tags surviving

**Before:** When `utm_campaign` was stripped or missing, the lead landed in the `__none__` bucket. Google Ads campaign-level attribution coverage was effectively **1%** for app-direct signups.

**Now:** The `gclid_attribution` BQ table refreshes daily from Google Ads `click_view` API for the last 30 days. Any gclid present on a HubSpot contact resolves to its specific campaign / ad_group / ad. **Google ID-based attribution: 1% → 77%.**

---

### Problem 7 — Microsoft/Bing leads had no click_id signal

**Before:** Microsoft Ads leads with empty UTM were stuck in Direct/Organic; `msclkid` wasn't carried through.

**Now:** Microsoft Final URL Suffix appends `campaign_id` / `ad_group_id` / `ad_id` to every Bing click. HubSpot captures these via URL parameter capture. Lead Module calculated properties auto-sync.

---

### Problem 8 — Manual daily enrollment to fix misattributed leads

**Before:** Marketing-ops team manually re-enrolled contacts in HubSpot workflows daily to fix wrong `qoyod_source` values.

**Now:** Workflow has 2 re-enrollment triggers (`hs_google_click_id`, `hs_facebook_click_id`) plus a goal lock-in for the 7 paid values. Automatic reclassification within 6h of click ID firing. Manual work tapers to spot-check.

---

### Problem 9 — Renamed/duplicate-named ads fragmented at ad-level

**Before:** Ad-level dashboard showed renamed creatives as separate rows or merged different ads with the same name into one bucket.

**Now:** All breakdown tables `GROUP BY ad_id` (or `adset_id` / `campaign_id`) with `MAX(name)` for display. Latest name shown, all historical metrics aggregated.

---

### Problem 10 — Deal attribution stuck on UTM names

**Before:** Deal-to-campaign attribution used UTM names only. Failed when ads were renamed between lead creation and deal close.

**Now:** Deal Module has 3 new sync properties — `deal_campaign_id_sync`, `deal_adgroup_id_sync`, `deal_ad_id_sync` — that mirror from the contact. YTD backfilled (15,431 deals). All 3 views (`paid_channel_campaign_daily`, `v_adset_performance`, `v_ad_performance`) join deals by ID first with name as fallback.

---

## Coverage today

| Channel | ID-attribution coverage | How it resolves |
|---|---|---|
| Snapchat Ads | ~100% | Native Instantform integration syncs `lead_campaign_id_sync` |
| Meta Ads | ~96% | Same native sync |
| TikTok Ads | ~100% | Same native sync |
| Google Ads | **77%** | Gclid → click_view API resolver (rolling 30-day window) |
| Microsoft Ads | Growing (URL Suffix newly enabled) | hsa_* params → contact properties → lead sync |
| LinkedIn Ads | Low volume | UTM name match |

---

## Architecture at a glance

```
Ad click on platform
        ↓
URL params + auto-tagged click IDs (gclid / fbclid / msclkid / tiktok_id)
        ↓
HubSpot contact captures URL params + click IDs
        ↓
Workflow re-enrollment fires when click IDs change → re-classifies qoyod_source
        ↓
Lead Module calculated properties mirror from Contact (auto)
        ↓
BQ leads mirror (every 6h) pulls latest qoyod_source + sync IDs
        ↓
BQ views (paid_channel_campaign_daily, v_adset_performance, v_ad_performance)
   ID-first join: campaign_id / adset_id / ad_id matches platform spend rows
   Name-fallback for channels without sync IDs (LinkedIn, Twitter)
        ↓
Hex dashboards — campaign attribution at every grain
```

---

## What's still ahead

- **gclid resolution to dashboards** — gclid_attribution is built but not yet wired into `paid_channel_campaign_daily`. Currently exposed via `v_lead_attribution` for ad-hoc queries. ~3% of Google leads (with empty UTM but populated gclid) would gain campaign-level attribution if wired in.
- **Microsoft Ads URL Suffix data flowing** — recently enabled; coverage will grow as new traffic accumulates.
- **First vs. last-touch attribution model** — currently using first-paid-wins via workflow goal. Switch to last-touch is a 1-line workflow change if business model changes.
