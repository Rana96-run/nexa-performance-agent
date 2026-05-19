# Pitfalls & Known Traps

Append one-liner entries as they're discovered. Every entry should include
the fix, not just the symptom.

## Pause precedence — channel-dependent surgical cleanup runs before campaign-pause

- **Rule (confirmed 2026-05-17):** A campaign hitting the pause threshold
  (CPL > $50 / CPQL > 3× warning for 7+ days) is NEVER auto-paused at the
  campaign level until surgical cleanup has happened first. The surgical
  surface is CHANNEL-DEPENDENT:
  - **Social** (meta, snapchat, tiktok): pause bad ADS first. The ad IS
    the targeting decision; one bad creative can poison the average.
  - **Search** (google_ads, microsoft_ads): pause bad KEYWORDS first AND
    review the landing page. The keyword IS the targeting decision; ad-
    level pause on search channels is the WRONG first step. LP issues
    (broken form, slow load, intent mismatch) masquerade as ad/keyword
    problems and require manual verification.
- **Ad-level pause rules — SOCIAL ONLY** (mirrored in `scripts/bulk_ads.py`
  AND `analysers/campaign_health.py::_campaigns_with_ad_pause_candidates`).
  Helper hard-filters to `channel IN ('meta', 'snapchat', 'tiktok')`:
  - `zero_conv`: spend > $70, 7+ days, 0 platform conversions
  - `high_cpl`:  CPL > $50, 10+ days (`AD_CPL_PAUSE` in config.py)
  - `junk_lead`: 10+ days, hs_leads ≥ 5, disq_rate ≥ 60%
- **Keyword-level pause rules — SEARCH ONLY** (mirrored in
  `executors/keyword_policy.py` AND
  `analysers/campaign_health.py::_campaigns_with_keyword_pause_candidates`).
  Helper hard-filters to `channel IN ('google_ads', 'microsoft_ads')`:
  - `zero_conv`: spend > $35, 14+ days, 0 conversions
  - `high_cpl`:  CPL > $80, 14+ days, 1+ conversions
- **LP review (mandatory on search before campaign-pause):** For any search
  campaign hitting pause-zone, the team manually visits the destination LP
  to verify load speed, form submission, and keyword-intent alignment. The
  QA gate enforces this — campaign-pause on a search channel is blocked
  even with no flagged keywords, mandating LP review.
- **Enforcement (defense in depth):**
  1. `campaign_health.py` pre-fetches BOTH ad-level + keyword-level
     candidates per campaign before the action loop. When action would be
     "pause", it routes by channel:
     - Social → check ad candidates → downgrade to "drilldown" with top 5
       worst ads listed
     - Search → check keyword candidates → downgrade to "drilldown" with
       top 5 worst keywords + LP review instructions (even if no keywords
       flagged, LP review is mandatory)
  2. `qa/checks.py::check_pause_precedence` (wired into `verify_asana`)
     is channel-aware: looks up the campaign's channel from BQ, then
     checks the right candidate type. Blocks any unauthorized campaign-
     pause Asana task. Search-channel tasks are blocked even with no
     flagged keywords because LP review can't be detected automatically.
- **Why both layers:** even if a future analyser/human bypasses the
  analyser's downgrade and submits a campaign-pause task directly, the
  gate blocks it at the Asana surface. Single source of truth lives in
  `_campaigns_with_ad_pause_candidates()` (social) and
  `_campaigns_with_keyword_pause_candidates()` (search).

## Activity dashboard: parallel BQ futures silently overwritten by sequential re-runs

- **Symptom (2026-05-16):** `reports/app.py` had a `ThreadPoolExecutor(14)` block that
  ran all 14 SQL queries in parallel, but cold-load latency was still 12–20s and
  results were sometimes stale.
- **Root cause:** Seven downstream code blocks (`user_sql`, `intel_sql`, `ts_sql`,
  `exec_sql`, `fu_sql`, `new_ads_sql`, `hc_sql`/`fresh_sql`) redefined the same SQL
  strings and re-ran `bq.query().result()` **sequentially after the parallel block**,
  overwriting the fast parallel results with slow serial ones. The parallel block was
  doing real work; it was just wasted.
- **Fix:** Deleted all 7 duplicate sequential blocks (–352 lines). All 14 queries now
  come exclusively from the `ThreadPoolExecutor` futures. Cold load: ~2s. Commit: `34af5fb`.
- **Rule:** After adding a parallel executor, grep for any re-use of the same SQL
  variable names or `bq.query()` calls below the executor block — they will silently
  overwrite the parallel results.

## Railway domain: nexa-web-production-6a6b, NOT nexa-performance-agent

- **Symptom (2026-05-15):** Dashboard link returned Railway 404.
- **Root cause:** Memory had `nexa-performance-agent.up.railway.app` which was the
  trial personal-account project (deleted). The live Pro project auto-assigned domain
  is `nexa-web-production-6a6b.up.railway.app`.
- **Fix:** Run `railway variables` to read `ACTIVITY_DASHBOARD_URL` directly from the
  live project — that is always the canonical URL. Commit: `c280ac9`.
- **Rule:** Never hard-code Railway URLs in memory — always verify with `railway variables`.

## Multi-account collectors: pool rows before upsert (NEVER upsert per-account)

**Symptom (2026-05-15):** Microsoft Ads account 188176729 appeared dormant since
April 24 in BQ even though the API returned real spend for May 10-14. Yesterday's
(May 14) spend of $981.54 was completely missing for that account.

**Root cause:** `collectors/microsoft_ads_bq.py` looped `for acc in accs:` and
called `upsert_rows(...)` once per account. `upsert_rows` derives its DELETE
scope from `key_fields`. Since `key_fields=["date","channel","campaign_id"]`
shares `channel='microsoft_ads'` across both accounts, account-2's
DELETE-then-INSERT wiped account-1's rows for every overlapping (date, channel)
partition before re-inserting only its own data.

**Fix:** Pool rows from ALL accounts into a single `all_rows: list[dict] = []`,
then call `upsert_rows()` ONCE at the end of the function. Applied to all 4
functions: `collect_and_write`, `collect_adsets_and_write`,
`collect_keywords_and_write`, `collect_ads_and_write`.

**General rule:** Any collector that iterates over multiple accounts/sub-channels
that share `key_fields` MUST aggregate rows across the iteration and upsert
once. Per-iteration upserts on overlapping scopes cause silent data loss.

## UTM param → ad hierarchy level (must memorise)

| Ad-platform level | HubSpot UTM property        |
|-------------------|-----------------------------|
| Campaign          | `lead_utm_campaign`         |
| Ad Set / Ad Group | `lead_utm_audience`  ← NOT `lead_utm_medium` |
| Ad                | `lead_utm_content`          |
| Keyword           | `lead_utm_term`             |
| Source/channel    | `lead_utm_source`           |
| Channel-type      | `lead_utm_medium`  (cpc / paid_social — NOT an adset name) |

`lead_utm_medium` never carries the adset name. Adset name lives in
`lead_utm_audience`. `v_adset_performance` Strategy B already joins on
`lead_utm_audience` correctly. Date discovered: 2026-05-13.

## ID property naming — different at every layer (DO NOT confuse)

The platform ad-group level has 4+ different names across our stack. Whenever
you write code or SQL touching IDs, match the name to the layer EXACTLY:

| Layer                              | Property / column name        | Notes                                       |
|------------------------------------|-------------------------------|---------------------------------------------|
| HubSpot **Contact** (0-1)          | `ad_group_id`                 | underscore between "ad" and "group"         |
| HubSpot **Contact** (0-1)          | `campaign_id`                 | populated by URL parameter capture (hsa_*)  |
| HubSpot **Contact** (0-1)          | `ad_id`                       | custom property — needs explicit URL capture|
| HubSpot **Lead Module** (0-136)    | `lead_adgroup_id_sync`        | "adgroup" as ONE word, NO underscore        |
| HubSpot **Lead Module** (0-136)    | `lead_campaign_id_sync`       | calculated property — mirrors contact       |
| HubSpot **Lead Module** (0-136)    | `lead_ad_id_sync`             | calculated property — mirrors contact       |
| HubSpot **Deal** (0-3)             | `deal_adgroup_id_sync`        | "adgroup" as ONE word, NO underscore        |
| HubSpot **Deal** (0-3)             | `deal_campaign_id_sync`       | calculated from contact                     |
| HubSpot **Deal** (0-3)             | `deal_ad_id_sync`             | calculated from contact                     |
| BigQuery `adsets_daily` table      | `adset_id`                    | Meta/TikTok/Snap term (Google = ad_group)   |
| BigQuery `ads_daily` table         | `ad_id`                       | universal                                   |
| BigQuery `campaigns_daily` table   | `campaign_id`                 | universal                                   |
| BigQuery `v_adset_performance` view| `adset_id`                    | exposed for dashboards (= adgroup_id sync)  |
| BigQuery `v_ad_performance` view   | `ad_id`, `adset_id`, `campaign_id` | exposed for dashboards               |

Critical mappings when joining:
- HubSpot **Contact** `ad_group_id` ≡ HubSpot **Lead** `lead_adgroup_id_sync` ≡ BQ `adset_id`
  (calculated property syncs contact → lead automatically; same ID value)
- HubSpot **Contact** `campaign_id`  ≡ HubSpot **Lead** `lead_campaign_id_sync` ≡ BQ `campaign_id`
- HubSpot **Contact** `ad_id`        ≡ HubSpot **Lead** `lead_ad_id_sync`       ≡ BQ `ad_id`

The collector and view code already uses these consistently. The trap is when
WRITING new queries against HubSpot's Search API — `ad_group_id` (Contact)
vs `lead_adgroup_id_sync` (Lead Module) IS different and HubSpot's API
returns 400 if you use the wrong one on the wrong object.

Date discovered: 2026-05-14.

## Deals sync — parallel runs duplicate the table

- **Symptom:** `hubspot_deals_daily` ends up with 1.5–2x more rows than HubSpot
  for the same window. Per-bucket counts show 2+ rows with `updated_at`
  timestamps seconds apart.
- **Cause:** Two `collect_and_write()` calls running near-simultaneously
  (e.g., I run a manual backfill while the 6h scheduler also triggers).
  The DELETE-before-INSERT in `upsert_rows()` is not transactional with the
  load job — each run's DELETE fires before either's INSERT, so both runs
  insert their full row set and neither's DELETE catches the other.
- **Fix when it happens:** TRUNCATE the table, run a single fresh YTD
  backfill (`railway run python -m collectors.hubspot_deals_bq`), verify
  dedupe with `COUNT(*)` vs `COUNT(DISTINCT full_key)` — should equal 1.00x.
- **Prevent:** Never run a manual deals sync without first checking
  scheduler logs for an in-progress run. If unsure, wait 6h between runs.
  Date discovered: 2026-05-13.

## BigQuery

- **Streaming buffer blocks DELETE for 90 min.** Rows inserted via streaming
  `insert_rows_json()` sit in a buffer invisible to DELETE/UPDATE. Fix:
  always use `load_table_from_file(BytesIO(ndjson))` — load jobs land in
  the partition instantly and are free. See `collectors/bq_writer.py`.
- **Query-too-large (>1MB).** DELETE with 1000s of key tuples in OR chains
  overflows. Fix: group by `date`, then `WHERE date=@d AND scope IN UNNEST(@sv)`.
- **Partition pruning requires a literal or param.** Don't do
  `WHERE date >= CURRENT_DATE() - INTERVAL 7 DAY` in a view definition; use
  it in queries, or pass params.
- **`upsert_rows` scope-field DELETE causes silent ghost-row accumulation.** When
  `key_fields=[date, scope_field, ...]`, the DELETE only removes rows where
  `scope_field IN (values present in the new build)`. If a lead's source changes
  between builds, the old row (old_source, same date) is NEVER deleted and
  accumulates. Fix: for tables rebuilt entirely per date (like
  `hubspot_leads_module_daily`), use `key_fields=["date"]` only — DELETE wipes
  the whole date partition before re-inserting. Found 2026-05-11: 60,156 rows /
  186,384 leads (5x inflated) vs correct 12,326 rows / ~26k leads. Repair:
  `DELETE WHERE TRUE` + `_rebuild_daily_buckets` for all 131 dates. Fixed by
  changing `_rebuild_daily_buckets` key_fields to `["date"]`.

## HubSpot deal amounts in BQ are correctly USD — verified 2026-05-09

- **`hubspot_deals_daily.amount_total` and `amount_won` ARE USD** (the collector's
  `to_usd()` works correctly). `amount_*_native` columns hold the original SAR.
- Verified by direct API check on 2026-05-09: deal `499825686757`
  ("مؤسسة عجوة نخلة"), HubSpot raw `amount`=12255, `deal_currency_code='SAR'`,
  BQ `amount_won`=$3268, `amount_won_native`=12255 SAR. Math: 12255/3.75=3268 ✓.
- A previous "rule" instructing to divide by 3.75 in dashboards was based on an
  incorrect comparison against Funnel/Looker (which displays SAR). It was
  reverted across all Hex SQL and `analysers/campaign_health.py` on 2026-05-09.
- **Use BQ deal/revenue columns as-is. Do NOT divide by 3.75.** Spend is USD,
  deal/revenue is USD, ROAS is unitless.
- The `_native` columns remain available for users who explicitly want SAR.

## Channel name mismatch: `microsoft` vs `microsoft_ads`

- **`v_channel_key_map` originally used `microsoft`** as the paid_channel
  key, but every collector writes `channel='microsoft_ads'` to the daily
  tables. Result: any Hex tile that joined via `v_channel_key_map`
  silently dropped Microsoft Ads (no error, just blank). Fixed in
  `collectors/views.py` on 2026-05-06 by changing `microsoft` →
  `microsoft_ads` in both the CASE branches and the UNNEST list. Run
  `python -c "from collectors.views import refresh_all_views; refresh_all_views()"`
  to push the view update to BQ.
- **Future-proofing:** the channel name in `v_channel_key_map` MUST equal
  `campaigns_daily.channel` (collector output) exactly. If you add a new
  channel, write it the same way in both places.

## bq_writer schema vs live BQ schema drift

- **`ADS_DAILY_SCHEMA` (and other TABLES schemas) in `collectors/bq_writer.py`
  must match the live BQ table.** When they don't, load jobs fail with
  cryptic `"No such field: <name>"` even though the field exists in the
  destination table.
- **Why:** Even with `ALLOW_FIELD_ADDITION`, BQ validates each input row
  against the **supplied** schema, not the destination's. The flag only
  allows the destination to GROW; rows can't carry fields the supplied
  schema lacks.
- **Fix when adding new collectors:** before writing rows with a new field
  (e.g. `cpl`, `frequency`), verify the field exists in
  `bq_writer.<TABLE>_SCHEMA`. If not, add it. Specifically `cpl` was added
  to `ADS_DAILY_SCHEMA` on 2026-05-06 to fix MS Ads `collect_ads_and_write`.

## TikTok Marketing API OAuth

- **Auth URL host is `business-api.tiktok.com`, NOT `business.tiktok.com`.**
  Using the latter redirects to `/not-found`. The Marketing API portal lives
  on the API subdomain. Fixed in `scripts/tiktok_oauth.py`.
- **Token lifetimes:** access_token = 24 h, refresh_token = 365 d. Daily
  `--refresh` runs needed unless the collector auto-refreshes per call.
- **Redirect URI must be registered** at TikTok Developer Portal → app →
  Settings → Redirect URIs: `http://localhost:8080/tiktok/callback`.

## Microsoft Ads REST Reporting API (May 2026)

- **Correct endpoint:** `https://reporting.api.bingads.microsoft.com/Reporting/v13/GenerateReport/Submit`
  (not `/api/advertiser/reporting/v13/...` — that path doesn't exist).
  Polling: `/Reporting/v13/GenerateReport/Poll`.
- **`ReportRequest` body must include `Type` field** as REST discriminator,
  e.g. `"Type": "CampaignPerformanceReportRequest"`. Without it, API returns
  `400 NullRequest "request message is null"` even though the JSON is valid.
- **`Scope.AccountIds` must be a flat int list,** not the SOAP-style
  `{"long":[id]}` wrapper. Wrong format = same NullRequest error.
- **Column name differences vs SOAP API:**
  - AdGroupPerformanceReport: use `Status` (NOT `AdGroupStatus`)
  - KeywordPerformanceReport: use `BidMatchType` (NOT `MatchType`)
  Both fail at submit time with cryptic "Invalid JSON at position N. Path: $.Columns[X]".
- **`AADSTS650052` resolution:** qoyod.com Azure AD tenant didn't have the
  Microsoft Advertising service principal. Fixed by Global Admin running:
  `New-MgServicePrincipal -AppId "d42ffc93-c136-491d-b4fd-6f18168c68fd"`.
  Once SP exists, work account OAuth on `/common/` works. Tenant ID:
  `8b6fc4da-1c24-432f-b089-2355d22f028d`.

## Microsoft Ads OAuth

- **Work accounts (Azure AD) are blocked.** Signing in with `@qoyod.com`
  (work account) returns `AADSTS650052` (no service principal in tenant)
  or `AADSTS65002` (first-party preauthorization required). Microsoft only
  preauthorizes their own apps + approved partners — there is no admin-
  consent workaround for customer-registered apps.
- **Fix: use a personal Microsoft account.** Rana already has a personal
  MS account using `rana.khalid@qoyod.com` (separate identity from the
  work account — Microsoft allows both with the same email). The OAuth
  picker shows both; pick "Personal account – Created by you".
- **Endpoint must be `/consumers/`** in `scripts/microsoft_oauth.py` —
  `/common/` lets Azure route to the work account and fail. The script
  is hard-coded to consumers.
- **Redirect URI must match Azure exactly.** Registered:
  `http://localhost:8080/ms-ads/callback` (not `/microsoft/callback`).

## HubSpot

- **10,000-result hard cap on Search API.** After `after=10000` returns 400.
  Fix: walk N-day windows (we use 7-day windows), reset `after` per window.
- **Lead module is object `0-136`**, separate from Contacts. Use
  `/crm/v3/objects/0-136/search`, not `/contacts/search`.
- **READ-ONLY.** Never PATCH/DELETE/CREATE HubSpot objects without explicit
  user approval in Slack. User reminded this multiple times.
- **Canonical `lead_qoyod_source` internal names (verified 2026-05-11 from HubSpot property editor):**
  ```
  Google Ads       Microsoft Ads    Meta Ads
  Snapchat Ads     Tiktok Ads       LinkedIn Ads
  ```
  `Tiktok Ads` has a lowercase 'i' — NOT `TikTok Ads`. All BQ channel_maps,
  `QOYOD_SOURCE_TO_CHANNEL` in `channel_inference.py`, and the views in
  `collectors/views.py` must use these exact strings. Any mismatch causes
  leads to silently drop from dashboard joins.
- **`HUBSPOT_ACCESS_TOKEN` is NOT in the local `.env` — it lives on Railway.**
  Any local CLI run (`python -m collectors.hubspot_leads_bq mirror`) MUST use
  `railway run python -m collectors.hubspot_leads_bq mirror`. Without `railway run`
  the token is `None`, every HubSpot API call returns 401, and the failure
  happens inside `_load_pipelines()` at startup before any data is fetched.
  Confirmed 2026-05-11.
- **Unicode arrows crash `print()` on Windows** — `→` (`→`) maps to
  `undefined` under `cp1252` (Windows default console encoding). Replace with
  `->` in any `print()` or `f-string` that is not inside a `sys.stdout.reconfigure`
  block. Symptom: `UnicodeEncodeError: 'charmap' codec can't encode character '→'`
  before any work is done.

## Meta — November 2025 deprecations

Tested and confirmed:
- ❌ `page_impressions` — use `page_impressions_unique` (reach)
- ❌ `page_fans` — use `page_follows`
- ❌ `page_fan_adds` — use `page_daily_follows_unique`
- ❌ `page_impressions_organic` / `page_impressions_paid` — gone
- ✅ `page_post_engagements` — still works
- ✅ `page_views_total` — still works
- ✅ `page_daily_follows` — still works

IG insights:
- ❌ `impressions` — gone; use `reach` as the closest daily metric
- ✅ `reach` — true daily time-series (period=day)
- ⚠️ `profile_views`, `website_clicks`, `accounts_engaged`,
  `total_interactions` — require `metric_type=total_value` and can't be mixed
  in the same call with day-series metrics. Fetch separately; attribute the
  aggregate to the end_date row.

## Snapchat

- ❌ `conversion_lead` field does NOT exist (we assumed it did)
- ❌ `total_conversions` also rejected by most accounts
- ✅ Safe set: `impressions, swipes, spend, conversion_sign_ups`
- Spend is in **micro-currency** (divide by 1,000,000)
- ❌ `currency`, `spend_native`, `currency_native` are NOT in `campaigns_daily`
  schema. Do NOT include them in snap_bq.py rows — BQ returns 400 BadRequest.
  Snap always converts to USD before writing; native fields were removed.

## Google Ads

- **Customer ID must have NO dashes** in API calls. `_customer_ids()` strips.
- `login_customer_id` is the MCC, not the child account.
- PMax campaigns have **no ad groups**; they have **asset groups**. Requires
  a different query (`asset_group` resource).
- Cost in **micros** (`cost_micros / 1_000_000`).
- **Keyword policy is centralised in `executors/keyword_policy.py`.** Don't
  duplicate ALWAYS_NEGATIVE / BRAND_ONLY / NEVER_NEGATIVE patterns into other
  files — import from the policy module. قيود/qoyod variants are BRAND_ONLY
  (only allowed in campaigns whose name contains `Brand`). Always-negative
  terms (login / مجاني / دورة / تحميل / قرض / تمويل / وظيفة + EN equivalents)
  are dropped from `add_kw` even if they converted, and direct-executed as
  EXACT negatives when they appear with 0-conv spend.
- **Arabic "قيود" is ambiguous.** It can mean either the company name "Qoyod"
  OR the accounting noun "journal entries". The policy module disambiguates by
  checking for accounting modifiers (`محاسبية` / `المحاسبة` / `يومية` /
  `اليومية`). Terms like `قيود محاسبية` and `قيود المحاسبة` are FEATURE
  keywords (treat as normal); only standalone `قيود`, `برنامج قيود`, `نظام قيود`,
  `qoyod` etc. are brand-only. If you ever see one of those feature-noun
  combinations flagged as a brand violation, the disambiguation list needs
  another modifier added.
- **Competitor patterns must be distinct, not common Arabic words.** Wafeq
  (`وافق` = also "agreed") and Manager.io / Al-Ostaz (`الاستاذ` = also "the
  teacher/Mr.") are common false-positive risks. Use only the specific
  spellings that don't collide with everyday Arabic: `wafeq`, `وافيق`,
  `الاستاذ المحاسبي` (full phrase), not the bare ambiguous form.
- **Removing a negative keyword is safe — re-adding is the risk.** Removing
  `qoyod` or competitor names as negatives just re-opens those queries to
  match in the right campaign. The audit `scripts/audit_active_negatives.py`
  direct-executes removals (no approval) because it can't make money go
  somewhere it shouldn't. ADDING negatives still requires the patterns to
  pass the policy check first.
- **Search-term audit produces 4 buckets, not 2.** Old pattern was add_kw +
  add_neg. New pattern: add_kw, add_neg (regular wasted), auto_neg
  (always-negative direct-execute), pause_watch (brand/competitor/lang —
  flag for human, never auto-execute either way). Don't conflate auto_neg
  with pause_watch — auto_neg fires immediately, pause_watch surfaces an
  Asana task and waits.
- **Keyword cadence: WEEKLY for adds + pauses, DAILY for negatives.** New
  keyword expansion task and `audit_and_pause_nonconverting_keywords` only
  fire on Sunday Riyadh (`weekday() == 6`). Negatives still direct-execute
  daily. Override for testing: `FORCE_WEEKLY_KEYWORDS=1`. Helpers:
  `_is_weekly_keyword_day()` exists in BOTH `analysers/google_ads_audit.py`
  and `analysers/google_ads_audit_tasks.py` — change them in lockstep if the
  weekday convention ever changes.
- **30-keyword-per-adgroup cap.** Before proposing additions,
  `filter_kw_against_adgroup_cap` queries existing enabled keyword counts
  per ad group and only keeps `(30 - existing)` highest-conv candidates per
  group. Dropped candidates carry a `drop_reason` for the Asana task body.
  This is enforced at audit time, not at execution time — `bulk_keywords.py
  add` doesn't re-check (yet).
- **QS<5 + lost-IS>80% combo.** Existing keywords matching this combo with
  zero historical spend (180-day window) → **DELETE**; with spend → **PAUSE**.
  GAQL note: `metrics.search_rank_lost_impression_share` IS available on
  `keyword_view` (despite docs being unclear). Aggregating in Python because
  GAQL with `segments.date` filter returns daily rows; we sum cost and take
  the latest QS / max lost-IS across the window.
- **CSV writer with variable-shape rows.** When `audit_active_keywords.py`
  emits both pattern violations and QS+IS-lost violations in one CSV, rows
  have different keys. Use the union of all keys + `extrasaction='ignore'`
  on `csv.DictWriter` so it doesn't crash on the first short row.
- **`change_status.resource_change_operation` is NOT a valid GAQL field**
  in v23 (despite some older docs/examples). To estimate keyword age, use
  first-impression date via `keyword_view` + `metrics.impressions > 0`
  with a 365-day window. That's what `keyword_policy.keyword_first_impression_dates`
  does. Newly-added keywords without any impressions return empty → treat
  as age 0 → age guard skips them (safe default).
- **Age guard: 10 days minimum.** `MIN_KEYWORD_AGE_DAYS = 10` in config.
  Performance-based pause (Rule A: spend>$80/0-conv) and the QS+IS-lost rule
  both check `keyword_first_impression_dates()` first. ALWAYS-NEGATIVE
  bypass — login/دورة/تحميل etc. are policy violations, not performance
  decisions, so they get paused immediately at any age.
- **Sunday is `weekday() == 6`.** The Saudi work week starts Sunday, so
  Sunday Riyadh runs the keyword auto-fix and Monday Riyadh posts the
  weekly summary. The summary reads Sunday's BQ activity log entry
  (`role='keyword_approval'`, `action='weekly_autofix'`) within a 36-hour
  window so timezone slop doesn't drop it.
- **Keywords NEVER post to Slack.** Expansion candidates → Asana only.
  Negatives → direct-execute silently. The old Slack-approval workflow
  (`post_keyword_approval` / `pending_keyword_approvals.json` /
  `check_and_execute_pending`) was removed in 2026-05. If a re-introduction
  is ever proposed: don't.

## Windows / Python 3.14 / Console encoding

- Arabic page names crash `print()` on Windows console (cp1252). Fix at
  script top:
  ```python
  try: sys.stdout.reconfigure(encoding="utf-8")
  except Exception: pass
  ```

## Replit

- **Don't overwrite root `.replit`** — it runs the agent (`main.py daily`).
  Put dashboard `.replit` in `dashboard/` if deploying as separate repl.
- **Service account JSON on Replit:** use
  `GOOGLE_APPLICATION_CREDENTIALS_JSON` secret (paste the JSON string),
  NOT `GOOGLE_APPLICATION_CREDENTIALS` (which expects a file path that
  doesn't exist on Replit).

## LinkedIn

- **Access tokens: 60 days. Refresh tokens: 365 days.** Use
  `scripts/linkedin_refresh.py --write-env` weekly. Silent expiry = silent
  collector failure (returns 0 rows, no exception).
- **Header `LinkedIn-Version: 202502`** required on every call (bump ~twice/year).
  Versions 202410 and 202504 are retired → 426 NONEXISTENT_VERSION.
- **DO NOT send `X-Restli-Protocol-Version: 2.0.0` with v202502.** This header
  causes 400 "Projected field not present in schema CampaignGroupV4/CampaignV8/
  AdAnalyticsV6" on every endpoint. Remove it entirely — v202502 works correctly
  without it.
- **DO NOT pass `fields=` projection params** on `adCampaignGroups` or `adCampaigns`.
  They are rejected when the Restli 2.0 header is absent. Return full objects and
  read what you need from the response.
- **MUST pass `fields=` on `adAnalytics`.** Unlike the metadata endpoints, the
  analytics endpoint silently omits any field you don't explicitly request. Without
  `"fields": "costInLocalCurrency,impressions,clicks,externalWebsiteConversions,dateRange,pivotValues"`,
  `costInLocalCurrency` is absent from every row → all spend appears as $0 in BQ.
  Verified 2026-05-10: account had $2,769 YTD real spend but BQ showed $0 until
  the `fields` param was added. Fixed in `_fetch_analytics()` in `collectors/linkedin_bq.py`.
- **Campaigns must use the account-scoped URL:**
  `/rest/adAccounts/{acct_id}/adCampaigns` — NOT `/rest/adCampaigns`.
  The global endpoint needs `search.account.values[0]` param which conflicts
  with removing the Restli 2.0 header. Account-scoped URL needs only `q=search`.
- **`adAnalytics` has pivot-explosion limits.** Requesting `pivot=CREATIVE`
  with wide date range paginates slowly — keep windows ≤ 7 days.
- **Lead Gen Forms bypass UTMs.** Leads from LinkedIn native forms land in
  HubSpot with `qoyod_source='LinkedIn'` but `utm_campaign=NULL`. They'll
  bucket into `__no_utm__`. Real fix: pull `/rest/leadFormResponses` and
  join by `form_id → campaign_id`.
- **Campaign names aren't on `adAnalytics`.** Must bulk-fetch via account-scoped
  `/rest/adAccounts/{acct_id}/adCampaigns` and join.

## Snapchat (extended)

- **DAY granularity rejects end_time in the future.** Always cap `end = date.today() - timedelta(days=1)`. Passing `date.today()` means `end_exclusive = tomorrow` which Snap rejects. Applies to both `collect_and_write` and `collect_adsets_and_write`.
- **Access token expires after 30 min — per-account refresh is NOT enough for large accounts.** 1,000 ads × 5 date-chunks = 5,000 API calls → can take 1–4 hours. Even a per-account refresh at loop start expires mid-account. Fix: track `token_refreshed_at = time.monotonic()` and renew with `token = _refresh_access_token()` whenever `time.monotonic() - token_refreshed_at > 1500` (25 min) inside the per-ad/per-adset inner loop. Applies to `collect_ads_and_write` and `collect_adsets_and_write`.
- **`ZoneInfo("UTC")` crashes on Windows** when the `tzdata` package is absent from the system timezone database. Fix: `if not tz_name or tz_name.upper() == "UTC": tz = timezone.utc` — use `timezone.utc` directly rather than `ZoneInfo("UTC")`.
- **Conversion fields are per-account.** Safe across every account:
  `conversion_sign_ups`. Others (`conversion_purchases`, `conversion_add_cart`,
  `conversion_start_checkout`, `conversion_save`, `conversion_subscribe`,
  `conversion_app_installs`) only work if configured on the Pixel. Collector
  now requests the broad set and falls back to `SNAP_STATS_FIELDS_SAFE` on 400.
- **Native currency is per-account; reporting is USD.** `_get_account()`
  detects each ad account's native currency and `collectors/currency.py`
  converts to USD via the SAR peg (`config.USD_SAR_PEG = 3.75`). Native
  values are preserved as `spend_native` / `currency_native`. If a new
  non-SAR/non-USD currency appears, add it to `PEG_RATES_TO_USD` in
  `currency.py` (and document the source — peg vs FX rate).
- **No adset/ad grain yet.** Dashboard can't drill below campaign.
  See `09_open_tasks.md`.

## Railway deployment

- **`logs/` and `cache/` are gitignored** — Python modules inside them won't
  deploy. Fix: change `.gitignore` to `logs/*.log` and `cache/*.json` so the
  `.py` module files are tracked.
- **`ALLOW_FIELD_ADDITION` in BQ load jobs needs `autodetect=True` or
  explicit schema fields** — without it, extra fields cause 400 BadRequest.
- **HubSpot webhook signature** used `hmac.new()` which doesn't exist in
  Python stdlib. `_verify_signature` now returns `True` (open endpoint).
- **Zapier webhook secret** in `.env` as inline comment was parsed as the
  value. Fixed by removing the check entirely (`_verify(): return True`).
- **Railway healthcheck on `/reports/latest`** causes rollback loops when
  `latest.html` doesn't exist on a fresh container. Removed healthcheck from
  `railway.toml`. Health is now checked via `/health`.

## Google Drive reports

- Reports (`latest.html`) are uploaded after every render. Flask falls back
  to Drive if local file is missing (new container after deploy).
- Requires: Drive API enabled in GCP + service account shared on folder
  with **Editor** access. See `memory/10_google_drive.md`.
- `GDRIVE_REPORTS_FOLDER_ID` env var (optional — defaults to `GDRIVE_FOLDER_ID`).

## Slack noise

- **Heartbeats**: `send_heartbeat()` only posts on `status='failed'`.
  Success/started statuses log to console only.
- **HubSpot webhook**: deal/lead handlers are log-only. Weekly agent run
  posts the aggregate channel summary — no per-event messages.

## OAuth (general)

- **Meta page tokens from long-lived user tokens are permanent** — don't
  bother refreshing. Use `scripts/meta_organic_setup.py` to derive.
- **Google refresh tokens** perpetual unless revoked in account settings.

## Campaign naming convention

- **Naming convention applies to NEW campaigns only.** Existing campaigns have
  varied legacy names that must be parsed as-is. Never reject or rename an
  existing campaign that doesn't match `{Channel}_{Type}_{Language}_{Product}_{Audience}`.
  The convention enforcer (`executors/naming.py`) is for campaign creation only.

## Leads & qualified leads terminology

- **Never use "SQLs" or "MQLs".** Those refer to the contact lifecycle stage
  stored in `hubspot_leads_daily` which is NOT used and never written to.
- The only valid source for lead counts and qualified lead counts is
  `hubspot_leads_module_daily` (`leads_total`, `leads_qualified`).
- A "qualified lead" = `leads_qualified` from the HubSpot Lead Module (object
  `0-136`). CPQL = spend / qualified leads. Never compute CPQL from
  contact-stage data.

## BQ column names (verified 2026-05-15)

- **`paid_channel_daily`**: columns are `leads_total` (not `leads`) and `qualified`
  (not `sqls`). Writing `leads` or `sqls` in SQL returns "Did you mean roas?".
- **`agent_activity_log`**: timestamp column is `ts` (not `created_at`).
- **`ARRAY_AGG ORDER BY … NULLS LAST` unsupported in BQ.** Replace with
  `ORDER BY COALESCE(nullable_col, 99999) ASC`.
- **`health_check.py` freshness threshold must be ≥ 3 days** (not > 1). Before
  08:00 Riyadh the nightly collector hasn't run so data is legitimately 2 days
  old. Threshold < 3 produces a nightly false-positive.

## Railway — single canonical project

- **Live project:** `nexa-performance-agent` in **Marketing Workspace** (Pro),
  ID `57f124d0-e254-4420-89f7-75baab4e6126`, service `85ed1a2a`.
- Personal-account project (`1b3ee05a`) **deleted** as of 2026-05-15.
- Always verify with `railway status` before deploying — must show
  `nexa-performance-agent / production / nexa-web`.

## Landing page A/B test

- **Test start date: 2026-05-04.** HubSpot LP (`campaigns.qoyod.com`) has been live ~1 year. WordPress LP (`lp.qoyod.com`) launched for testing starting this date.
- **Never compare LP types using data before 2026-05-04.** Historical data is biased — HubSpot LP has 1 year of optimization, WordPress LP had no volume. All CPL/CPQL comparisons must use `week_start >= '2026-05-04'` as the filter.
- **Minimum test window: 2 weeks** before drawing conclusions. Check back ~2026-05-18 for a meaningful read.
- `v_lp_weekly_summary` and `v_lp_performance_weekly` views are set up and collecting from today. The Hex LP cell should always filter `week_start >= '2026-05-04'`.

## UTM → BQ field mapping (universal across all channels)

Every platform's data is stored with the following UTM-aligned field names.
Never use platform-specific names directly in BQ schemas or views.

| UTM param     | BQ field name  | Platform examples                             |
|---------------|----------------|-----------------------------------------------|
| utm_source    | channel        | "google_ads", "meta", "snapchat", "tiktok"    |
| utm_campaign  | campaign_name  | Campaign / Campaign Group (LinkedIn)           |
| utm_audience  | adset_name     | Ad Set / Ad Group / Ad Squad / Campaign (LI)  |
| utm_content   | ad_name        | Ad / Creative                                 |
| utm_term      | keyword_text   | Keyword (Google, Microsoft Ads)               |
| utm_medium    | placement      | Placement / Form name                         |
| utm_keyword   | keyword_text   | Same as utm_term — platform call it this way  |

LinkedIn-specific: Campaign Group = utm_campaign (stored as `campaign_id`),
Campaign = utm_audience (stored as `adset_id`). The campaign collector writes
at group level for campaigns_daily; adsets collector remaps campaign→adset.

## TikTok

- **Adgroup/ad-grain API error 40002: "dimension campaign_id does not match data_level AUCTION_ADGROUP"** — TikTok API rejects `campaign_id` as a dimension when `data_level=AUCTION_ADGROUP` or `AUCTION_AD`. Fix: remove `campaign_id` from the `dimensions[]` list for adgroup/ad calls and instead look it up via `/adgroup/get/` or `/ad/get/` metadata call. Fixed in `tiktok_bq.py`.
- **30-day query window cap for `stat_time_day`** — TikTok returns `"max time span is 30 days when use stat_time_day"` if `start_date` to `end_date` span >30 days. Fix: wrap `_get_report()` in `_date_chunks(max_days=30)`. Applies at all levels: AUCTION_CAMPAIGN, AUCTION_ADGROUP, AUCTION_AD.
- **`qoyod_source` is stored as `'Tiktok Ads'`** (lowercase 'i' — not
  `'TikTok'` and not `'TikTok Ads'`). `v_channel_key_map` in `collectors/views.py`
  must use `WHEN 'tiktok' THEN 'Tiktok Ads'` or the BQ join in
  `channel_roas_daily` will silently produce 0 TikTok rows.
- **Deep Funnel Optimization in UI:** Instant Form → scroll down → toggle
  "Deep Funnel Optimization" → select CRM pixel → choose "Initiate Checkout"
  as the further optimization event. API equivalent: `optimization_goal="CONVERT"`,
  `pixel_id=TIKTOK_CRM_PIXEL`, `conversion_event="INITIATE_CHECKOUT"`.
- **TikTok access token** expires in 24 hours; refresh token in 365 days.
  Run `python scripts/tiktok_oauth.py --refresh` daily (or via Railway cron).

## BigQuery — campaigns_daily schema

- **`campaign_group_name` does NOT exist in `campaigns_daily`.**  Use
  `campaign_name` for all channels including LinkedIn. The BQ table only has:
  `channel`, `campaign_id`, `campaign_name`, `date`, `spend`, `impressions`,
  `clicks`, `leads`, and channel-specific columns. Any JOIN or GROUP BY on
  `campaign_group_name` will fail silently (column not found).

- **Spend is USD, not SAR.** `campaigns_daily.spend` is always stored in USD regardless of channel. Never label spend figures as SAR in Slack messages, dashboards, or reports. Google Ads cost_micros and Snap spend are divided by 1,000,000 to get USD before BQ write.

- **Never remove a keyword with any spend history.** Only delete keywords with all-time spend = $0. Low QS or poor performance = fix (ad copy / LP) or pause, never remove. Negatives can always be added freely.

- **QS < 5 converting-keyword exception:** Do NOT pause a low-QS + high-lost-IS keyword if conv > 4 AND $10 ≤ CPA ≤ $70. Keyword is delivering real leads despite poor quality score. Guard enforced in `scan_active_keywords()` before flagging. Pause only if conv ≤ 4 OR CPA outside that range.
- **Zero-active-keyword guard:** Never pause the last enabled keyword in an ad group — campaign goes dark silently. `scan_active_keywords()` counts enabled keywords per ad group before flagging and skips sole keywords with a console warning.
- **Ad pause thresholds:** spend > $70 / 7 days / 0 conv → pause. 60%+ disqualified leads (10+ days) → pause. CPL > $50 (10+ days) → pause. Never remove ads, only pause.

## HubSpot deals collector — dual-pass architecture (2026-05-10)

- **2-day incremental window missed long-cycle deals.** A deal created Jan 15 and won Apr 20 would never
  be reprocessed by a 2-day createdate window — BQ showed 721 won deals for Sales Pipeline while HubSpot
  showed 789. Fix: extended to 30-day createdate lookback + a separate closedate pass that covers all won
  deals regardless of when they were created.
- **Closedate pass must run in ALL modes, not just incremental.** Backfills with `--start-date` also need
  the closedate pass; deals closed in the window but created before it are otherwise missed.
- **Do NOT infer `qoyod_source` from UTMs.** Calling `resolve_channel()` on utm fields would inflate counts
  by ~15–20% vs HubSpot's explicit `deal_qoyod_source` filter. Use explicit source only:
  `explicit_src = p.get("deal_qoyod_source") or ""; src_label = explicit_src if (explicit_src and explicit_src != "Other") else "Other"`.
- **Stale rows survive when upsert key changes.** If inference is turned off, old rows with `qoyod_source='Google Ads'`
  (inferred) survive alongside new rows with `qoyod_source='Other'` because the upsert key changed. Fix:
  DELETE the affected pipelines explicitly (`DELETE WHERE pipeline IN (...)`) before re-running backfill.
  SDR Offline Sales and Partnerships Revenue were affected (847 rows deleted 2026-05-10).
- **`seen_ids` deduplication is mandatory.** Deals found in both createdate pass (because they were recently
  created AND won) and closedate pass must be deduplicated with a `seen_ids: set[str]`. Without it, double
  rows inflate counts further.

## Leads gap — Eid Al-Fitr seasonality (2026-05-10)

- **Mid-March 2026 lead dip is NOT a data collection gap.** Week of Mar-16 and Mar-23 show ~950–1,000
  leads vs ~2,000 either side. This is Eid Al-Fitr 2026 (holiday falls Mar 20–22 with extended business
  closure). All sources dropped together — Google went from ~110/day to ~8–22/day, Snapchat from ~50 to
  ~8–22/day. Date coverage is complete (no missing dates in BQ). When reviewing 90-day trends, annotate
  this dip as Eid rather than a reporting issue.

## HubSpot collector

- **Incremental lookback must be 30 days, not 2.** A lead created Apr 22 but qualified May 4 is never
  reprocessed with a 2-day window → BQ stays at 0 qualified while HubSpot UI shows Qualified.
  Fix: `INCREMENTAL_LOOKBACK_DAYS = 30` (still filters by `hs_createdate`, not `hs_lastmodifieddate`).
- **`hubspot_lists.py` must never be deleted.** It creates `LIST_won_deals_lookalike_seed` and
  `LIST_existing_customers_exclude` — used for Meta Custom Audiences and LinkedIn Matched Audiences.
  Was deleted in a dead-code audit; user demanded restore. It is not dead code.

## BQ views — join traps

- **`paid_channel_campaign_daily` join must use `LOWER()` on both sides.** Case-sensitive `=` between
  `campaign_name` (platform, mixed-case) and HubSpot `lead_utm_campaign` (often lower-case) silently
  produces 0 leads in every dashboard cell. Root cause of "correct in direct query, wrong in Slack."
  Always use `LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)`.
- **Snapchat `qoyod_source` is `'Snapchat Ads'` — NOT `'Snapchat'`.** `v_channel_key_map` must use
  `WHEN 'snapchat' THEN 'Snapchat Ads'` or all Snapchat leads are silently dropped in HubSpot joins.
  Confirmed 2026-05-09: BQ had 168 Snapchat leads stored as `'Snapchat Ads'`; the old `'Snapchat'`
  mapping caused Hex to show 795 leads instead of 963 for the 7-day window — all Snapchat leads invisible.
  Fixed in `collectors/views.py` line 27. Previous pitfall entry had this backwards — disregard any note saying `'Snapchat'` is correct.

## Railway deployment (extended)

- **Duplicate Railway project across personal + team workspace = double deployments.**
  Both `rana96-run's Projects` (trial, ID `1b3ee05a`) and `Marketing Workspace` (pro, ID `57f124d0`)
  had `nexa-performance-agent` connected to the same GitHub repo. Every git push triggered two
  Railway deployments, causing double cron runs, doubled API calls (Meta/Snap/TikTok/HubSpot),
  and Snapchat 429 storms. Fix (2026-05-13): deleted the service and project from the trial
  personal workspace via Railway dashboard. The canonical project is `57f124d0` in Marketing Workspace.
  Local `railway` CLI must always link to Marketing Workspace: `railway project link -p "nexa-performance-agent" -w "Marketing Workspace"`.

- **`/tmp` is wiped on every redeploy.** `pending_approvals.json` (and any ephemeral state written to
  `/tmp`) is lost on each deploy. If the team pushes code between the 03:00 nightly approval post and
  morning reaction, the approval metadata is gone. Always write persistent state to BQ or the repo
  volume — never `/tmp`.
- **Teardown must be ON.** With Teardown OFF, old and new deployments overlap during transitions →
  two instances of the scheduler run simultaneously → double Slack posts + double Asana tasks.
  Set `teardown = true` in `railway.toml` AND enable Teardown in the Railway UI deploy tab.
- **gunicorn `--workers 1` is mandatory.** Multiple workers each spawn their own `operational_scheduler`
  thread → N duplicate nightly runs. Always: `gunicorn app_server:app --workers 1 --threads 4`.
- **Activity log CSV is ephemeral.** `logs/activity_log.csv` was wiped on every redeploy. All activity
  logging writes directly to BQ `agent_activity_log` via `log_activity_async()`. No CSV intermediary.
- **Canonical domain is `nexa-web-production-6a6b.up.railway.app`.** Confirmed 2026-05-15 via
  `railway variables` — the `ACTIVITY_DASHBOARD_URL` env var inside the service itself points to
  this domain. `nexa-performance-agent.up.railway.app` is NOT provisioned (returns Railway 404).
  `nexa-web-production-c859.up.railway.app` is the deleted personal-project domain. Use `6a6b`.

## Slack

- **Slack event body must be read ONCE before signature check.** `request.get_data()` called after
  `request.get_json()` returns an empty body — HMAC computed on empty bytes → always 403. Fix: call
  `raw = request.get_data()` first, parse JSON from those bytes, pass same `raw` to HMAC check.
  Also: handle `url_verification` challenge BEFORE signature check (Slack sends it unconfigured).
- **Slack MCP returns `invalid_auth` from scheduled/unattended tasks.** The MCP uses an OAuth session
  that doesn't exist in headless contexts. Fall back to direct Slack API with `SLACK_BOT_TOKEN`
  (`xoxb-` prefix) for all automated/Railway calls.

## Asana task format

- **Always write explicit date ranges in task titles and bodies.** Write `YYYY-MM-DD to YYYY-MM-DD`
  (never "last 14 days"). This lets the team open HubSpot and filter the exact same window to verify
  numbers. `date_from`/`date_to` must always be present in every finding dict.

## Adspirer MCP

- **Adspirer does not support Snapchat or Microsoft Ads.** Standard plan: 1 account per platform.
  Snap and MS must use direct API executors (`executors/snapchat.py`, `executors/microsoft_ads.py`).
  Adspirer is for interactive on-demand execution in Claude Code sessions — the Railway agent cannot
  use it (no browser OAuth).

## Hex API

- **Cannot use `updatePublishedResults: true` AND `inputParams` together.** Hex API v1 returns
  `"Cannot update app results if specifying custom input parameters"` (400) if both are set.
  You must choose one: update published results (with notebook's saved defaults) OR run with
  custom params (results not published). Workaround: set the date input's **default value** to a
  relative "Today" in the Hex UI — then API triggers with `updatePublishedResults: true` will
  always publish today's data without needing inputParams.
- **Date input default must be relative ("Today"), not absolute ("2026-05-02").** If a date
  parameter's default is an absolute date, every API-triggered run publishes that frozen date
  forever. Fix: open the notebook, click the date input cell, change its default from a specific
  date to the relative "Today" option. Then republish. This is a one-time UI fix — cannot be
  done via API.

## Looker Studio

- **No public API — all report building is manual.** BQ views can be created via code, but the
  Looker Studio layer above them (charts, data sources, filters, scorecards) requires manual UI work
  at lookerstudio.google.com. Hex is the canonical automated dashboard.

## TikTok lead attribution — correct HubSpot property for campaign ID

- **`campaign_id` / `ad_group_id` / `ad_id` on the Lead Module (0-136) are NULL for TikTok.**
  These properties exist but are never populated by HubSpot's native TikTok integration.
- **`lead_campaign_id_sync` IS populated** with the TikTok campaign ID (e.g. `1863074553592178`).
  It matches `campaigns_daily.campaign_id` exactly. This is the correct property for ID-based
  campaign matching (Strategy D in v_adset_performance / v_ad_performance).
- **No adset-ID or ad-ID equivalent exists** for TikTok on the Lead Module. `lead_campaign_id_sync`
  is campaign-grain only. If multiple adsets belong to the same campaign, the ID fallback spreads
  campaign-level leads to all adsets (graceful degradation — better than 0).
- **Meta native `campaign_id` etc. are also NULL** in practice as of 2026-05-13. Kept in the
  collector for future use if Meta's integration starts populating them.
- Established 2026-05-13 via `scripts/_check_tiktok_lead.py` deep-probe of HubSpot API.

## BQ views silently become TABLE after materialisation

- **`CREATE OR REPLACE VIEW` fails with "is currently a TABLE"** when a BQ view has previously
  been materialised (e.g. by an ETL process, or `bq_writer.py bootstrap`). The fix is to DELETE
  the table first, then run `CREATE OR REPLACE VIEW`. `create_views()` in `bq_writer.py` now
  auto-detects `table_type == "TABLE"` and drops before recreating.
- Views affected: `utm_paid_attribution_daily`, `v_adset_performance`, `v_ad_performance`
  were found as TABLE in production. Now recreated as VIEWs (2026-05-13).
- To fix manually: `python -m scripts._fix_views` or re-run the `create_views()` function.

## Freshness checks

- **Don't trust `updated_at` for freshness.** A collector that runs successfully but fetches
  zero rows still updates table metadata. Use `MAX(date)` per channel against
  `CURRENT_DATE('Asia/Riyadh')` instead. Helper: `scripts/check_freshness.py`.
- **Microsoft Ads (and LinkedIn) "Success + null ReportDownloadUrl" = no activity, NOT a bug.**
  When a Bing Ads account has zero spend/clicks/impressions in the queried window, the API
  returns `ReportRequestStatus.Status='Success'` with `ReportDownloadUrl=null`. The collector
  reads this as "no rows to write" and exits silently. This causes `MAX(date)` to lag, which
  looks like a stale collector — but the underlying integration is healthy. Verified
  2026-05-09: Microsoft Ads stopped on 2026-04-24 after campaigns were paused.
  Always sanity-check against the platform UI before declaring a collector broken.
  The MS collector now logs this case explicitly.
- **LinkedIn data stopped Feb 2026 due to missing `fields=` param, NOT zero activity.**
  The `adAnalytics` call omitted `fields`, so `costInLocalCurrency` was silently missing.
  All rows were written with spend=$0, causing the upsert to look unchanged and BQ freshness
  to lag. Real spend ($2,769 YTD) was recovered by adding the `fields` param. Fixed
  2026-05-10. See LinkedIn section above for the correct `fields` value.

## campaign_health.py — two lead fan-out bugs (found 2026-05-18)

**Bug 1 — campaigns_daily duplicate rows multiply HubSpot leads.**
Channels affected: Snapchat (2 rows/date), Microsoft Ads (up to 2 rows/date).
Symptom: `hs_leads` in audit tasks 2× what HubSpot shows.
Fix: `campaign_health.py` now pre-aggregates `campaigns_daily` in a `cd` CTE
(`GROUP BY date, channel, campaign_name`) before joining to HS. Applied 2026-05-18
in commit fb4f274.

**Bug 2 — shared campaign names across channels blend leads from the wrong channel.**
Affected: Bing campaigns named identically to Google ones (e.g. `Search_AR_Brand_v2`
exists in both `google_ads` and `microsoft_ads` in campaigns_daily). Filtering
campaigns_daily by channel is correct, but HS leads were not filtered by channel →
Bing CPQL used Google-sourced leads → fake CPQL of $23 when truth was $145+.
Fix: `hs` CTE now includes `qoyod_source` mapped to channel slug. JOIN condition
adds `hs.hs_channel = c.channel`. Orphan Bing campaigns now correctly show 0 leads.
Two wrong PENDING APPROVAL scale tasks flagged [DO NOT APPROVE] in Asana 2026-05-18.

**Prevention:** Any SQL JOINing `campaigns_daily c` to `hubspot_leads_module_daily h`
must:
1. Pre-agg cd: `SELECT date, channel, campaign_name, SUM(spend) … GROUP BY date, channel, campaign_name`
2. Pre-agg hs: include `qoyod_source`, map to channel, join on channel too.
Neither side alone is enough — both must be 1:1 and channel-aligned.
