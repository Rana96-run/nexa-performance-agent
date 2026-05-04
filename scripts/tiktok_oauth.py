"""
scripts/tiktok_oauth.py
=======================
TikTok Marketing API OAuth 2.0 flow — gets a fresh access_token + refresh_token.

Modes
-----
  python scripts/tiktok_oauth.py            # full browser OAuth (first time)
  python scripts/tiktok_oauth.py --refresh  # use saved refresh_token (no browser)

Full OAuth flow:
  1. Opens the TikTok authorization URL in your browser
  2. Starts a local server on port 8080 to catch the callback
  3. Exchanges the auth_code for access_token + refresh_token
  4. Writes both to .env  (TIKTOK_ACCESS_TOKEN, TIKTOK_REFRESH_TOKEN)
  5. Updates Railway environment variables automatically

Pre-requisite (one-time):
  In TikTok Developer Portal → your app → Settings → Redirect URIs,
  add:  http://localhost:8080/tiktok/callback

Token lifetimes:
  access_token   — 24 hours
  refresh_token  — 365 days (use --refresh to renew before expiry)
"""
from __future__ import annotations

import os
import sys
import json
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv, set_key

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
load_dotenv(override=True)

APP_ID       = os.getenv("TIKTOK_APP_ID", "")
APP_SECRET   = os.getenv("TIKTOK_APP_SECRET", "")
REDIRECT_URI = "http://localhost:8080/tiktok/callback"
ENV_PATH     = ".env"

BASE = "https://business-api.tiktok.com/open_api/v1.3"

_code: str | None = None
_done = threading.Event()


# ─── Local callback server ─────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _code
        if self.path.startswith("/tiktok/callback"):
            params = parse_qs(urlparse(self.path).query)
            _code = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>TikTok authorized. You can close this tab.</h2>")
            _done.set()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


# ─── Token exchange ─────────────────────────────────────────────────────────────

def _exchange(auth_code: str) -> dict:
    r = requests.post(
        f"{BASE}/oauth2/access_token/",
        json={"app_id": APP_ID, "secret": APP_SECRET, "auth_code": auth_code},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(f"TikTok API error {body.get('code')}: {body.get('message')}")
    return body.get("data", {})


def _refresh(refresh_token: str) -> dict:
    r = requests.post(
        f"{BASE}/oauth2/refresh_token/",
        json={"app_id": APP_ID, "secret": APP_SECRET, "refresh_token": refresh_token},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 0:
        raise RuntimeError(f"TikTok refresh error {body.get('code')}: {body.get('message')}")
    return body.get("data", {})


# ─── Save & validate ─────────────────────────────────────────────────────────

def _save(data: dict):
    access  = data.get("access_token", "")
    refresh = data.get("refresh_token", "")
    expires = data.get("access_token_expire_in", "?")
    scope   = data.get("scope", "")

    if not access:
        raise ValueError("No access_token in response")

    set_key(ENV_PATH, "TIKTOK_ACCESS_TOKEN",  access)
    if refresh:
        set_key(ENV_PATH, "TIKTOK_REFRESH_TOKEN", refresh)

    print(f"\n  access_token  ({len(access)} chars): {access[:40]}...")
    if refresh:
        print(f"  refresh_token ({len(refresh)} chars): {refresh[:40]}...")
    print(f"  expires_in:   {expires}s  |  scope: {scope}")

    # Update Railway
    _push_to_railway(access, refresh)

    # Validate
    _validate(access)


def _push_to_railway(access: str, refresh: str):
    """Update Railway env vars using the CLI."""
    try:
        vars_to_set = [f"TIKTOK_ACCESS_TOKEN={access}"]
        if refresh:
            vars_to_set.append(f"TIKTOK_REFRESH_TOKEN={refresh}")
        subprocess.run(
            ["railway", "variables", "--set"] + vars_to_set,
            check=True, capture_output=True,
        )
        print("  Railway env vars updated.")
    except Exception as e:
        print(f"  [warn] Railway update failed (update manually): {e}")


def _validate(access: str):
    """Quick call to confirm the token works."""
    r = requests.get(
        f"{BASE}/advertiser/info/",
        headers={"Access-Token": access},
        params={
            "advertiser_ids": json.dumps([
                os.getenv("TIKTOK_AD_ACCOUNT_2025") or os.getenv("TIKTOK_AD_ACCOUNT_2024")
            ]),
            "fields": '["advertiser_id","name","status"]',
        },
        timeout=15,
    )
    body = r.json()
    if body.get("code") == 0:
        lst = body.get("data", {}).get("list", [])
        for a in lst:
            print(f"  Validated: account {a.get('advertiser_id')} — {a.get('name')} ({a.get('status')})")
    else:
        print(f"  [warn] Validation returned code {body.get('code')}: {body.get('message')}")


# ─── Entrypoints ─────────────────────────────────────────────────────────────

def do_refresh():
    rt = os.getenv("TIKTOK_REFRESH_TOKEN", "")
    if not rt:
        print("ERROR: TIKTOK_REFRESH_TOKEN not set in .env — run full OAuth first.")
        sys.exit(1)
    print("Using saved refresh_token to get new access_token...")
    data = _refresh(rt)
    _save(data)
    print("\nDone — tokens refreshed.")


def do_oauth():
    if not APP_ID or not APP_SECRET:
        print("ERROR: TIKTOK_APP_ID / TIKTOK_APP_SECRET not set in .env")
        sys.exit(1)

    auth_url = (
        "https://business-api.tiktok.com/portal/auth?"
        + urlencode({
            "app_id":        APP_ID,
            "state":         "nexa_tiktok_oauth",
            "redirect_uri":  REDIRECT_URI,
            "scope":         "advertiser.read,report.read",
            "response_type": "code",
        })
    )

    server = HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\nOpening TikTok authorization in your browser...")
    print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
    print(f"Make sure this redirect URI is registered in TikTok Developer Portal:")
    print(f"  {REDIRECT_URI}\n")
    webbrowser.open(auth_url)

    _done.wait(timeout=300)
    server.shutdown()

    if not _code:
        print("ERROR: no code received within 3 minutes. Did you approve the app?")
        sys.exit(1)

    print(f"Auth code received, exchanging for tokens...")
    data = _exchange(_code)
    _save(data)
    print("\nDone — tokens saved to .env and Railway.")


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        do_refresh()
    else:
        do_oauth()
