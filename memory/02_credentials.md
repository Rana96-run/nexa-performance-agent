# Credentials & Integration State

All secrets live in `.env` (gitignored). When adding a new integration, add the
keys here BEFORE coding so we never chase "is it connected?" again.

## State table

| Platform | Paid | Organic | Token expiry | Notes |
|---|---|---|---|---|
| Google Ads | ✅ connected (2 accts) | n/a | refresh token (perpetual) | MCC + 2 child accounts, YTD working |
| Meta (FB+IG) | ✅ connected (2 accts) | ✅ connected | Page token: permanent | Nov 2025 deprecated many metrics — see 08 |
| Snapchat | ✅ connected (2 accts) | n/a | refresh token (perpetual) | Only `conversion_sign_ups` pulled; `conversion_lead` / `total_conversions` invalid |
| HubSpot | ✅ read-only | ✅ read-only | Private app token (perpetual) | NEVER write to HubSpot |
| TikTok | ✅ connected (2 accts) | n/a | access_token perpetual | Both Qoyod 2024 (`7304642840767021057`) and Qoyod 2025 (`7565475813811093521`) authorized via app `7635928165407260689`. Token does NOT expire. No refresh flow needed. Re-run `scripts/tiktok_oauth.py` only if app secret rotates. **TZ note: 2025 acct is Asia/Kuwait — should be Asia/Riyadh for consistency.** |
| Microsoft Ads | ✅ connected (2 accts, always-on) | n/a | refresh token (perpetual) | **Both accounts run on every collector cycle, same as Google/Meta/Snap/TikTok.** Primary: account `188176729` (G1206XJR), Customer `254476670`, confidential client via `MS_REFRESH_TOKEN` (auth on `/common/` endpoint). Secondary: account `MS_ACCOUNT_ID_2=187231519`, Customer `MS_CUSTOMER_ID_2`, public client (device_code) via `MS_REFRESH_TOKEN_2` (`public_client=True`). Collector iterates BOTH via `_accounts()` in `collectors/microsoft_ads_bq.py` and pools rows into a single upsert per grain (campaigns/adsets/keywords/ads) — never per-account (see `08_pitfalls.md` multi-account upsert trap). REST Reporting API at `https://reporting.api.bingads.microsoft.com/Reporting/v13/GenerateReport/Submit`. |
| LinkedIn organic | ✅ connected | — | **60 days** | OAuth completed 2026-06-20; tokens rotated to .env, Railway, GitHub Secrets. Next expiry ~2026-08-19. Run `scripts/linkedin_refresh.py` before then. |
| LinkedIn Ads | ✅ connected | n/a | 60 days | Same token as organic. Analytics confirmed working (Jan-Feb 2026 data visible). No spend Jun 14-20 — 7-day backfill returned 0 rows correctly. `adCreatives` endpoint returns 426 NONEXISTENT_VERSION for all tested versions — ads-level data blocked until LinkedIn fixes API versioning. |
| YouTube | n/a | ⏳ app scaffold, OAuth pending | refresh token (perpetual) | Env slots empty — run `scripts/youtube_oauth.py` to fill |
| GA4 | linked to BQ | linked to BQ | n/a | `analytics_517912363.events_*` tables; `GA4_PROPERTY_ID=517912363` |
| SEMrush | n/a | ✅ API key | perpetual | `SEMRUSH_API_KEY` set |
| Canva | n/a (creative) | ✅ connected | access 4h / refresh 120d | Used by Creative external agent; not called from repo |
| Miro | n/a | ✅ connected | access token | `MIRO_BOARD_ID=uXjVGgfpUqw=` for system diagram |
| SMTP (Gmail) | — | ✅ sending | app-password | `rana.khalid@qoyod.com` via `smtp.gmail.com:587` |
| Funnel.io | **learn-only** | — | — | Read-only posture — do NOT push to Funnel. Webhook recorded but not called. Read API token pending. See `memory/12_funnel_io.md` |

## .env key map

```
# BigQuery
BQ_PROJECT_ID=angular-axle-492812-q4
BQ_DATASET=qoyod_marketing
BQ_LOCATION=europe-west1
GOOGLE_APPLICATION_CREDENTIALS=./bigquery-key.json    # local path
GOOGLE_APPLICATION_CREDENTIALS_JSON=<paste>           # Replit secret

# Google Ads
GOOGLE_ADS_DEVELOPER_TOKEN / CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN
GOOGLE_ADS_CUSTOMER_IDS=151-302-0554,575-349-4964  # child accts (Qoyod New, Auto Cloud)
GOOGLE_ADS_LOGIN_CUSTOMER_ID=5789762982             # MCC, no dashes

# Meta paid
META_ACCESS_TOKEN=<perpetual user token>
META_AD_ACCOUNT_1=act_1366192231206913  # قيود
META_AD_ACCOUNT_2=act_835030860363827   # Qoyod

# Meta organic (PERMANENT page token)
META_APP_ID=506000922536697
META_APP_SECRET=<redacted>
META_FB_PAGE_ID=1331104100252779
META_IG_BUSINESS_ID=17841403066920736
META_PAGE_ACCESS_TOKEN=<perpetual>

# Snapchat  (collectors use SNAPCHAT_* prefix, NOT SNAP_*)
SNAPCHAT_CLIENT_ID=0ef9983d-b615-42fb-9f9f-543cbad8de21
SNAPCHAT_CLIENT_SECRET / REFRESH_TOKEN / ACCESS_TOKEN
SNAPCHAT_REDIRECT_URI=<registered>
SNAPCHAT_AD_ACCOUNT_2024=d1fe4f2b-...
SNAPCHAT_AD_ACCOUNT_2025=df8e5c13-...
SNAPCHAT_PIXEL=<set but currently unused>
SNAPCHAT_CAPI_TOKEN=<set but currently unused — no CAPI sendback built>

# HubSpot
HUBSPOT_ACCESS_TOKEN=<private app>

# LinkedIn  (connected — 60-day token clock started)
LI_CLIENT_ID=78zn55gkwpx2pt
LI_CLIENT_SECRET=<redacted>
LI_REDIRECT_URI=http://localhost:8080/callback
LI_ACCESS_TOKEN=<set; 60-day expiry>
LI_ORGANIZATION_URN=<set>       # collector reads this exact key
LI_AD_ACCOUNT_URN=<set>         # enables paid LinkedIn insights

# YouTube (OAuth scaffolding present; run scripts/youtube_oauth.py to fill)
YT_CLIENT_ID=
YT_CLIENT_SECRET=
YT_REFRESH_TOKEN=
YT_CHANNEL_ID=

# Microsoft Ads (app registered; still needs OAuth for refresh token)
MS_DEVELOPER_TOKEN=<set>
MS_CLIENT_ID / MS_CLIENT_SECRET / MS_TENANT_ID / MS_OBJECT_ID=<set>
MS_ACCOUNT_ID=188176729            # primary (work acct, confidential client)
MS_CUSTOMER_ID=254476670
MS_REFRESH_TOKEN=<set>              # /common/ endpoint, public_client=False
MS_ACCOUNT_ID_2=187231519           # secondary (personal acct, public client)
MS_CUSTOMER_ID_2=<set>
MS_REFRESH_TOKEN_2=<set>            # device_code, public_client=True
MS_REDIRECT_URI=http://localhost:8080/ms-ads/callback

# TikTok (account IDs + pixels present; access token pending app approval)
TIKTOK_AD_ACCOUNT_2024=7304642840767021057
TIKTOK_AD_ACCOUNT_2025=7565475813811093521
TIKTOK_PIXEL_2024 / TIKTOK_CRM_PIXEL=<set>

# GA4 / SEMrush / Canva / Miro / SMTP — all set, see .env for values

# Funnel.io — LEARN-ONLY (see memory/12_funnel_io.md)
# Posture: we do not push to Funnel. Read-only, to understand the
# existing custom dims / metrics / Looker boards before designing ours.
FUNNEL_WEBHOOK_URL=<set but NOT called from code>
FUNNEL_WEBHOOK_TOKEN=<set but NOT called from code>
FUNNEL_API_TOKEN=           # pending (workspace read API)
FUNNEL_ACCOUNT_ID=          # pending
FUNNEL_PROJECT_ID=          # pending
FUNNEL_BQ_DATASET=          # pending — is the export enabled?
FUNNEL_LOOKER_REPORT_ID=    # pending — canonical Looker board URL
```

## Token lifetime rules of thumb

- **Google (Ads + YT)**: refresh tokens perpetual unless user revokes
- **Meta user tokens**: 60 days. Meta **page** tokens derived from long-lived
  user tokens are **permanent**. Always use page tokens for org-level APIs.
- **Snapchat**: refresh token perpetual
- **HubSpot private app**: perpetual
- **LinkedIn**: access token 60 days, refresh token 365 days. **Will need
  auto-refresh helper** before first expiry.

## OAuth redirect URLs currently registered

| Platform | Redirect URL |
|---|---|
| Snapchat | `https://app.qoyod.com/snapchat/callback` (prod) |
| LinkedIn | `http://localhost:8080/callback` (add to app Auth tab) |
| YouTube | `http://localhost` (auto-chosen by `run_local_server`) |

## Helper scripts

| Script | Purpose |
|---|---|
| `scripts/meta_organic_setup.py` | Short-lived user token → permanent page token |
| `scripts/linkedin_oauth.py` | LinkedIn OAuth; `orgs` subcommand lists org URNs |
| `scripts/youtube_oauth.py` | YouTube OAuth; prints refresh_token + channel_id |
| `scripts/snap_oauth.py` | Already-used Snap OAuth flow |
| `scripts/linkedin_refresh.py` | Refresh LI access token via refresh_token grant; `--write-env` persists back |
| `scripts/microsoft_oauth.py` | Mint MS Ads refresh token (uses `/consumers/` endpoint — personal MS account only) |

## Rules

- **HubSpot is read-only.** All collector code uses GET + POST-search only.
  Never PATCH/DELETE/CREATE objects without explicit user approval in Slack.
- **Never commit `.env`** — verify `.gitignore` excludes it.
- **Never skip the `{{load_dotenv()}}` call** in a collector — several have
  their own `load_dotenv()` for Replit/cron contexts where the parent shell
  didn't load it.
