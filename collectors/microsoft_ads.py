"""
Microsoft Advertising (Bing Ads) — OAuth bootstrap helper.

Campaign-level performance data is now read from BigQuery via
`collectors.from_bq.read_campaigns("microsoft_ads", days=N)`. The 4×/day
writer in `collectors/microsoft_ads_bq.py` is the single source of truth.

This module exists only to host the one-time OAuth dance:
    python collectors/microsoft_ads.py auth
    # paste the refresh token into .env as MS_REFRESH_TOKEN

`CONTROL_PANEL.py` also calls `run_auth_flow()` directly when the token is
missing.
"""
import os
import urllib.parse
import requests
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("MS_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")

# 'common' tenant lets any Microsoft / work account sign in.
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
AUTH_URL  = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
SCOPE     = "https://ads.microsoft.com/msads.manage offline_access"


def run_auth_flow():
    """Print the auth URL, accept the redirect URL, exchange for tokens."""
    redirect_uri = os.getenv(
        "MS_REDIRECT_URI", "http://localhost:8080/microsoft/callback"
    )
    auth_url = (
        f"{AUTH_URL}"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&scope={urllib.parse.quote(SCOPE)}"
        f"&response_mode=query"
    )
    print("\n-- Microsoft Ads OAuth --")
    print("Open this URL in your browser and sign in with the Microsoft Ads account:\n")
    print(auth_url)
    print("\nAfter redirect, paste the full redirect URL here:")
    redirect = input("> ").strip()

    code = parse_qs(urlparse(redirect).query).get("code", [None])[0]
    if not code:
        print("No code found in URL. Make sure you pasted the full redirect URL.")
        return

    r = requests.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "redirect_uri":  redirect_uri,
        "scope":         SCOPE,
    })
    tokens = r.json()
    print("\n-- Tokens --")
    print(f"Access token:  {tokens.get('access_token', 'ERROR')[:40]}...")
    print(f"Refresh token: {tokens.get('refresh_token', 'MISSING')}")
    print("\nCopy the refresh token and add it to .env as:")
    print("MS_REFRESH_TOKEN=<paste here>")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        run_auth_flow()
    else:
        print(__doc__)
