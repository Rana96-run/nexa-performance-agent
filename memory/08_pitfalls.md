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
