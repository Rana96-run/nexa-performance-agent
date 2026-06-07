# Skill — Run an OAuth helper

Use when a collector is skipping because tokens are missing, or when a new
integration is being hooked up for the first time.

## Helpers shipped in this repo

| Source | Script | What it produces |
|---|---|---|
| LinkedIn | `scripts/linkedin_oauth.py` | `LI_ACCESS_TOKEN` (60-day) |
| LinkedIn orgs | `python scripts/linkedin_oauth.py orgs` | `LI_ORGANIZATION_URN` (+ optional `LI_AD_ACCOUNT_URN`) |
| YouTube | `scripts/youtube_oauth.py` | `YT_REFRESH_TOKEN`, `YT_CHANNEL_ID` |
| Meta organic | `scripts/meta_organic_setup.py` | Permanent `META_PAGE_ACCESS_TOKEN`, `META_FB_PAGE_ID`, `META_IG_BUSINESS_ID` |
| Snapchat | (built into `snap_bq.py`) | Auto-refresh per run |
| Google Ads | Requires one-time manual refresh-token via Google OAuth Playground; then stored in `.env` |

## Redirect URIs to register in each provider

- LinkedIn app: `http://localhost:8080`
- YouTube / Google: `http://localhost:8080`
- Meta: the short-lived token is generated in Graph API Explorer, no redirect
  needed for the exchange script

## After any OAuth

1. Paste outputs into `.env` (locally) AND Replit Secrets (if deployed)
2. Run the collector with a small lookback first:
   `python collectors/<name>_bq.py 3`
3. Confirm rows in BQ with `bq-verify` skill
4. Update `memory/02_credentials.md` to mark the source connected

## Pitfalls

- Windows console + Arabic page names → crash. All OAuth scripts already
  set `sys.stdout.reconfigure(encoding="utf-8")`.
- LinkedIn tokens expire every 60 days — add a calendar reminder until
  the auto-refresh helper is built (see `09_open_tasks.md`).
- Meta page tokens derived from a long-lived user token are permanent —
  **don't** re-run `meta_organic_setup.py` unless the user token was
  rotated.
