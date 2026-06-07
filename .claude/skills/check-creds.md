# Skill — Check credentials state

Use when Amar asks "is X connected?" / "why is Y empty?" / before adding a
new integration.

## One-shot check

```python
import os
from dotenv import load_dotenv; load_dotenv()

SOURCES = {
  "google_ads":   ["GOOGLE_ADS_DEVELOPER_TOKEN","GOOGLE_ADS_CLIENT_ID","GOOGLE_ADS_CLIENT_SECRET","GOOGLE_ADS_REFRESH_TOKEN","GOOGLE_ADS_LOGIN_CUSTOMER_ID","GOOGLE_ADS_CUSTOMER_IDS"],
  "meta":         ["META_ACCESS_TOKEN","META_AD_ACCOUNT_1"],
  "meta_organic": ["META_PAGE_ACCESS_TOKEN","META_FB_PAGE_ID","META_IG_BUSINESS_ID"],
  "snapchat":     ["SNAPCHAT_CLIENT_ID","SNAPCHAT_CLIENT_SECRET","SNAPCHAT_REFRESH_TOKEN","SNAPCHAT_AD_ACCOUNT_2024","SNAPCHAT_AD_ACCOUNT_2025"],
  "linkedin":     ["LI_ACCESS_TOKEN","LI_ORGANIZATION_URN"],   # not LI_ORG_URN
  "youtube":      ["YT_CLIENT_ID","YT_CLIENT_SECRET","YT_REFRESH_TOKEN","YT_CHANNEL_ID"],
  "hubspot":      ["HUBSPOT_ACCESS_TOKEN"],
  "bigquery":     ["BQ_PROJECT_ID","BQ_DATASET","BQ_LOCATION"],
  "slack":        ["SLACK_BOT_TOKEN","SLACK_SIGNING_SECRET"],
}
for name, keys in SOURCES.items():
    missing = [k for k in keys if not os.getenv(k)]
    print(f"{name:14s}  {'OK' if not missing else 'MISSING: '+','.join(missing)}")
```

Save as `scripts/check_creds.py` once (idempotent — Amar can run any time).

## Also check

- `memory/02_credentials.md` — authoritative table of who's connected
- Replit Secrets (if running on Replit) may differ from local `.env`

## Token-lifetime reminders

- **LinkedIn** access token: **60 days** → needs refresh helper (open task)
- **Meta page token** (derived from long-lived user token): **permanent**
- **Google refresh tokens**: **permanent** unless revoked
- **HubSpot Private App token**: **permanent**
- **Snapchat**: refresh-token flow, handled inside `snap_bq.py` per-run
