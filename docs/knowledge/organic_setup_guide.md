# Organic Channels Setup Guide

Everything you need to do on each platform to unblock the Meta-organic, YouTube,
and LinkedIn collectors. Collectors are already built and wired into the 6h
scheduler — they no-op silently until these creds land in `.env`.

---

## 1. Meta Organic (Facebook Page + Instagram Business)

**Goal:** drop 3 values into `.env`
```
META_PAGE_ACCESS_TOKEN=<long-lived page token>
META_FB_PAGE_ID=<numeric page id>
META_IG_BUSINESS_ID=<numeric ig business id>
```

### Steps

1. **Graph API Explorer** → https://developers.facebook.com/tools/explorer
   - Select your existing Qoyod app (the one already used for Meta Ads)
   - User Token dropdown → **Get User Access Token**
   - Tick these permissions:
     - `pages_read_engagement`
     - `pages_show_list`
     - `read_insights`
     - `instagram_basic`
     - `instagram_manage_insights`
     - `business_management`
   - Click **Generate Access Token** → approve in popup
   - Copy the token shown at the top.

2. **Find your Page ID.**
   In Graph API Explorer, run:
   ```
   GET /me/accounts
   ```
   You'll see a list of pages you manage. Copy the `id` for Qoyod (Arabic + English
   pages are separate Page IDs — pick the one you actually use; we can do both
   later by duplicating the config).

3. **Find your IG Business Account ID.**
   Run:
   ```
   GET /{PAGE_ID}?fields=instagram_business_account
   ```
   You get back `{"instagram_business_account": {"id": "1784xxxxxxxxxxx"}}` → that's
   `META_IG_BUSINESS_ID`.

4. **Exchange short-lived → long-lived (60-day) token.**
   In a browser or curl:
   ```
   https://graph.facebook.com/v21.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={APP_ID}
     &client_secret={APP_SECRET}
     &fb_exchange_token={SHORT_LIVED_USER_TOKEN}
   ```
   You'll get a 60-day user token. Then call:
   ```
   GET /{PAGE_ID}?fields=access_token&access_token={LONG_LIVED_USER_TOKEN}
   ```
   The page `access_token` returned here is **permanent** (never expires as long
   as you stay admin). That's `META_PAGE_ACCESS_TOKEN`.

5. Paste all three into `.env`. Done.

**Test:**
```bash
python -c "from collectors import meta_organic_bq; meta_organic_bq.collect_and_write(days=3)"
```

---

## 2. YouTube Organic (Data API v3 + Analytics API)

**Goal:** drop 4 values into `.env`
```
YT_CLIENT_ID=<oauth client id>.apps.googleusercontent.com
YT_CLIENT_SECRET=<oauth client secret>
YT_REFRESH_TOKEN=<refresh token>
YT_CHANNEL_ID=UC...
```

### Steps

1. **Google Cloud Console** → https://console.cloud.google.com/apis/library
   - You said YouTube Data API v3 is already enabled. Also enable:
     - **YouTube Analytics API**
     - **YouTube Reporting API** (optional, for historical bulk)

2. **Create OAuth Client ID** (if not already).
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Download JSON → copy `client_id` and `client_secret`.

3. **Grant consent + get refresh token.** Easiest way:
   ```bash
   pip install google-auth-oauthlib
   ```
   Then in a python shell:
   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow
   flow = InstalledAppFlow.from_client_config(
     {"installed": {
        "client_id": "YOUR_ID",
        "client_secret": "YOUR_SECRET",
        "redirect_uris": ["http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
     }},
     scopes=[
       "https://www.googleapis.com/auth/yt-analytics.readonly",
       "https://www.googleapis.com/auth/youtube.readonly",
     ])
   creds = flow.run_local_server(port=0)
   print("refresh_token:", creds.refresh_token)
   ```
   A browser opens → sign in with the Google account that owns the Qoyod YouTube
   channel → approve → copy the printed refresh token.

4. **Find your Channel ID.**
   Go to https://studio.youtube.com → Settings → Channel → Advanced → "Channel ID"
   (starts with `UC...`). Or run:
   ```python
   import requests
   r = requests.get("https://www.googleapis.com/youtube/v3/channels",
     params={"part":"id","mine":"true"},
     headers={"Authorization": f"Bearer {creds.token}"})
   print(r.json())
   ```

5. Paste all four into `.env`.

**Test:**
```bash
python -c "from collectors import youtube_bq; youtube_bq.collect_and_write(days=7)"
```

---

## 3. LinkedIn (Page organic + Ads)

Hardest of the three — LinkedIn requires app verification for Marketing APIs.

**Goal:** drop into `.env`
```
LI_ACCESS_TOKEN=<oauth token>
LI_ORGANIZATION_URN=urn:li:organization:<numeric id>
LI_AD_ACCOUNT_URN=urn:li:sponsoredAccount:<numeric id>   # optional
```

### Steps

1. **Create a LinkedIn app.** https://www.linkedin.com/developers/apps
   - Company Page: link to the Qoyod LinkedIn Page (you must be a Page admin)
   - App name: "Qoyod Performance Agent"

2. **Request product access.** In the app → Products tab, request:
   - **Community Management API** (page analytics, organic stats) — usually
     auto-approved if you're verified as a Page admin.
   - **Marketing Developer Platform** (required for `r_ads` / `r_ads_reporting`)
     — needs LinkedIn review, takes 3–7 business days.
   - **Sign In with LinkedIn using OpenID Connect** (needed for OAuth flow)

3. **Get the Organization URN (Page ID).**
   - Go to your LinkedIn Page admin → URL looks like
     `linkedin.com/company/12345678/admin/` — the `12345678` is your org ID.
   - `LI_ORGANIZATION_URN = urn:li:organization:12345678`

4. **OAuth flow to get access token.**
   - In the app → Auth tab, add redirect URL `http://localhost:8080/callback`
   - Request scopes:
     - `r_organization_social` (read org posts)
     - `rw_organization_admin` (page analytics)
     - `r_ads` (ads, if approved)
     - `r_ads_reporting`
   - Use the authorization code flow:
     ```
     https://www.linkedin.com/oauth/v2/authorization
       ?response_type=code
       &client_id={CLIENT_ID}
       &redirect_uri=http://localhost:8080/callback
       &scope=r_organization_social rw_organization_admin r_ads r_ads_reporting
     ```
   - Sign in → you get redirected to `http://localhost:8080/callback?code=XXX`
   - Exchange the code for a token:
     ```
     POST https://www.linkedin.com/oauth/v2/accessToken
       grant_type=authorization_code
       code={CODE}
       redirect_uri=http://localhost:8080/callback
       client_id={CLIENT_ID}
       client_secret={CLIENT_SECRET}
     ```
   - Copy `access_token` from response → `LI_ACCESS_TOKEN`.
   - **Note:** LinkedIn tokens expire in 60 days. We can add auto-refresh later.

5. **Find Ad Account URN** (if you run LinkedIn Ads).
   - LinkedIn Campaign Manager → top-right → account dropdown. The URL contains
     the numeric ID: `business.linkedin.com/marketing-solutions/cm/accounts/506XXXXXX`
   - `LI_AD_ACCOUNT_URN = urn:li:sponsoredAccount:506XXXXXX`

6. Paste into `.env`.

**Test:**
```bash
python -c "from collectors import linkedin_bq; linkedin_bq.collect_and_write(days=7)"
```

---

## Summary: Which block today vs. later

| Platform | Blocker | ETA |
|---|---|---|
| Meta Organic | You generate token (5 min in Graph Explorer) | Today |
| YouTube | You run the OAuth snippet once | Today |
| LinkedIn Organic | Page admin + Community Management API (auto) | Today–tomorrow |
| LinkedIn Ads | Marketing Developer Platform approval | 3–7 days |

All three collectors **skip silently** if their creds aren't set, so the 6h
scheduler can safely run even while you're collecting tokens.
