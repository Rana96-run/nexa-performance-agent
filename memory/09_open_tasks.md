# Open Tasks — Prioritized Work Queue

Ordered by dependency + user priority. Check off as done; append new items at
the bottom of the relevant section.

## P0 — Unblocks everything else

- [ ] **Run YouTube OAuth** — `python scripts/youtube_oauth.py`. Writes
  `YT_REFRESH_TOKEN` + `YT_CHANNEL_ID` to `.env` (slots empty today).
- [ ] **Get Funnel.io read API token** — ask Amar for workspace API token
  + account_id + project_id. Fill `FUNNEL_API_TOKEN/ACCOUNT_ID/PROJECT_ID`.

## P1 — PMax sector campaigns (DONE — 2026-05-13)

All 5 sector campaigns created via API. Amar enabled 3 preferred campaigns,
paused the 5 sector campaigns. Audience signals added manually in UI.

Campaign IDs (customer 5753494964):
- Services: 23834877561 → ag/6712034766 (52 assets)
- Technology: 23844719995 → ag/6712034769 (53 assets, 26 search themes)
- Real Estate: 23835216687 → ag/6712037109 (52 assets, 28 search themes)
- Retail: 23845053748 → ag/6712036947 (50 assets, 19 search themes)
- WP: 23840470733 → ag/6712057318 (51 assets, 42 search themes)
- Retail: 23845053748 → ag/6712036947 (50 assets, 19 search themes)
- WP: 23840470733 → ag/6712057318 (51 assets, 42 search themes)

## P1 — Attribution depth (DONE 2026-05-13)

- [x] **Creative type tagging** — `creative_type STRING` added to `ads_daily` schema.
  Meta: `_creative_type_lookup()` fetches `creative{object_type}` per account.
  TikTok: `ad_format` captured in `_list_ads()` and mapped.
  Snap: `type` field captured in `_list_ads()` and mapped.
  Google/Microsoft: NULL (no creative type at ad grain).
  Values: image | video | carousel | collection | story | other

## P2 — LinkedIn campaign cloning (DONE 2026-05-13)

- [x] `list_campaign_creatives(campaign_id)` — lists all creatives in an ad set
- [x] `clone_campaign_creatives(source, target)` — copies reference URN + lead gen form
- [x] `create_full_campaign(..., clone_from_campaign_id=...)` — optional clone param
- [x] `scripts/linkedin_oauth.py` — added `rw_organization_admin` scope
- [ ] **Re-mint LinkedIn token** — run `python scripts/linkedin_oauth.py` to get
  token with new scope before using clone_campaign_creatives()

## P1 — Funnel.io (blocked on token)

- [ ] Ask Amar: workspace API token + account_id + project_id
- [ ] Once token lands: baseline snapshot, dim/metric list, reconcile vs BQ
- [ ] Map `channel_unified` → our `CHANNEL_MAP` in `collectors/views.py`

## P3 — Nice-to-have

- [ ] Weekly email digest via Gmail SMTP (creds set)
- [ ] A/B test tracker view (same utm_audience, different utm_content)
- [ ] SEMrush integration for keyword / competitor view (API key set)
- [ ] Snapchat organic (doubtful — no public page metrics API)

---

## Done this session (2026-05-13)

- [x] **Railway dual-project fix** — found two `nexa-performance-agent` projects (trial + pro)
  both auto-deploying from GitHub. Deleted the trial personal workspace project. Canonical
  project: `57f124d0` in Marketing Workspace. Documented in `memory/08_pitfalls.md`.
- [x] **PMax ads tab fix** — added `AND LOWER(utm_campaign) NOT LIKE '%pmax%'` to Google Ads
  `3_ads.sql` to remove PMax asset group names that were appearing as ad names with 0 leads.
- [x] **TikTok/Meta ID-based attribution (Strategy C/D)** — added new matching layers to
  `v_adset_performance` and `v_ad_performance` for when UTM names break:
  - Strategy C: adset-ID fallback via `lead_ad_group_id` (future Meta use)
  - Strategy D (new): TikTok campaign-ID fallback via `lead_campaign_id_sync` →
    `adsets_daily.campaign_id`. Confirmed `lead_campaign_id_sync` matches `campaigns_daily.campaign_id`
    exactly for TikTok leads (e.g. `1863074553592178`). `campaign_id` / `ad_group_id` / `ad_id`
    are NULL for both TikTok and Meta as of 2026-05-13.
  - New BQ columns: `lead_campaign_id_sync`, `lead_campaign_id`, `lead_ad_group_id`, `lead_ad_id`
    in both `hubspot_leads_individual` and `hubspot_leads_module_daily`.
  - `create_views()` updated: auto-drops TABLE before recreating as VIEW (prevents lock).
  - Cursor sync (`mirror`) running to backfill IDs for all 2026 leads.

## Done this session (2026-05-12)

- [x] **Snap concurrent API** — replaced sequential per-ad calls with
  ThreadPoolExecutor(8 workers). Added 429 retry with linear backoff in `_snap_get`.
  Speed: hours → ~5 min for 1,000 ads.
- [x] **Microsoft utm_audience attribution** — 3-layer fix:
  1. Collector now parses `{_adgroup}` custom param key (not `audience`) for utm_audience
  2. `v_adset_performance` platform CTE: `COALESCE(utm_audience, adset_name)` (was `adset_name` only)
  3. `v_ad_performance` platform CTE: `COALESCE(utm_content, ad_name)` (was `ad_name` only)
  Verified: `Bing_AR_Brand_Keywords` spend=1365, leads=194, sqls=104 ✓
- [x] **Microsoft adset rename fix** — "Cloud Accounting" → "Bing_Cloud_Accounting" rename
  caused BQ history mismatch with HubSpot. Fix: YTD backfill (132 days, 1,045 rows).
  Microsoft API returns current name for all historical dates → all rows updated.
  Views rematerialized. Arabic adsets now join correctly.
- [x] **Microsoft ads YTD backfill** — 132 days for ads level (running/complete).
- [x] **PMax sector campaigns created** — `scripts/clone_pmax_sectors.py` updated with
  atomic `GoogleAdsService.mutate()` batch (asset_group + all assets in one call).
  Fixed: LONG_HEADLINE capped at 5, undersized logos (32×32) filtered out,
  LOGO/BUSINESS_NAME pulled from campaign-level assets and merged into batch.
  All 5 campaigns created with full asset groups + search themes copied.
- [x] **Memory/skill cleanup** — `09_open_tasks.md` condensed; auto-refresh skill added.

---

## Archived sessions (condensed)

**2026-05-11:** Full HubSpot mirror sync (no cursor drift), Snapchat channel
mismatch fix, Riyadh date bucketing fix, BQ view materialization (6 heavy views
→ physical tables rebuilt every 6h), qual/disq rate formula fixed.

**2026-05-10:** HubSpot deals dual-pass fix, 2025 full backfill (110K deals),
SDR/Partnerships stale row fix, Eid seasonality confirmed as root cause of
mid-March dip.

**2026-05-06-07:** All YTD sub-level backfills (TikTok, Meta, Google, Snap ads/adsets),
keyword policy extended (competitors, language mismatch), Snap 142K rows, Hex
auto-refresh wired, ROAS close-date fix.

**2026-05-04-05:** HubSpot backfills, LP performance analysis + Hex cell, landing
page CPQL comparison (HubSpot LP $127 vs WP LP $713), Channel Deep Dive / Leads
Funnel / Insights & Recommendations Hex cells, no-UTM row in all campaign tables,
PMax asset-group collector.

**2026-05-03:** Slack cleanup, per-channel Asana assignees, Hex as canonical
dashboard, deep IS recommendations in keyword audit.

**Earlier:** Campaign naming enforcement, LinkedIn/TikTok/Snap collectors, OAuth
helpers, 6h reporting scheduler, meta organic collector, memory playbook.
