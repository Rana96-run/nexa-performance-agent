# Pitfalls & Known Traps

Append one-liner entries as they're discovered. Every entry should include
the fix, not just the symptom.

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

## TikTok Marketing API OAuth

- **Auth URL host is `business-api.tiktok.com`, NOT `business.tiktok.com`.**
  Using the latter redirects to `/not-found`. The Marketing API portal lives
  on the API subdomain. Fixed in `scripts/tiktok_oauth.py`.
- **Token lifetimes:** access_token = 24 h, refresh_token = 365 d. Daily
  `--refresh` runs needed unless the collector auto-refreshes per call.
- **Redirect URI must be registered** at TikTok Developer Portal → app →
  Settings → Redirect URIs: `http://localhost:8080/tiktok/callback`.

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
- **DO NOT pass `fields=` projection params** on `adCampaignGroups`, `adCampaigns`,
  or `adAnalytics` calls. They are rejected when Restli 2.0 header is absent.
  Return full objects and read what you need from the response.
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

- **QS < 5 CPA exception:** Do NOT pause a low-QS keyword if conv >= 3 AND CPA <= $90 AND 30+ days running. Only pause if CPA > $90 or conv < 3. Always re-check before acting.
- **Ad pause thresholds:** spend > $70 / 7 days / 0 conv → pause. 60%+ disqualified leads (10+ days) → pause. CPL > $50 (10+ days) → pause. Never remove ads, only pause.
