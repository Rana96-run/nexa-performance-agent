"""
Google Ads OAuth 2.0 flow — mints GOOGLE_ADS_REFRESH_TOKEN.

Run from the project root:
    railway run python scripts/google_ads_oauth.py

Steps:
  1. Opens Google sign-in in your browser
  2. Local server on port 8080 catches the callback
  3. Exchanges the code for access + refresh tokens
  4. Writes GOOGLE_ADS_REFRESH_TOKEN to .env and prints the Railway + GitHub set commands

IMPORTANT: In Google Cloud Console, add http://localhost:8080/callback
as an Authorised redirect URI for your OAuth 2.0 client before running.
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv, set_key

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(override=True)

CLIENT_ID     = os.getenv("GOOGLE_ADS_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8080/callback"

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE     = "https://www.googleapis.com/auth/adwords"

_code: str | None = None
_done = threading.Event()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _code
        params = parse_qs(urlparse(self.path).query)
        _code  = params.get("code", [None])[0]
        error  = params.get("error", [None])[0]
        self.send_response(200)
        self.end_headers()
        if error:
            msg = f"<h2>Error: {error}</h2>"
        else:
            msg = "<h2>Authorized. You can close this tab.</h2>"
        self.wfile.write(msg.encode())
        _done.set()

    def log_message(self, *_):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET not set in .env")
        sys.exit(1)

    auth_url = AUTH_URL + "?" + urlencode({
        "response_type": "code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",   # forces a new refresh_token even if previously granted
        "state":         "nexa_gads_oauth",
    })

    server = HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\nOpening Google sign-in in your browser...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    _done.wait(timeout=300)
    server.shutdown()

    if not _code:
        print("ERROR: no code received. Did you complete sign-in?")
        sys.exit(1)

    print("Code received — exchanging for tokens...")
    r = requests.post(TOKEN_URL, data={
        "grant_type":   "authorization_code",
        "code":         _code,
        "redirect_uri": REDIRECT_URI,
        "client_id":    CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }, timeout=15)
    r.raise_for_status()
    tokens = r.json()

    refresh_token = tokens.get("refresh_token", "")
    if not refresh_token:
        print("ERROR: no refresh_token in response.")
        print("Make sure 'prompt=consent' is set and the app has offline access.")
        print(f"Response: {tokens}")
        sys.exit(1)

    set_key(".env", "GOOGLE_ADS_REFRESH_TOKEN", refresh_token)
    print(f"\nGOOGLE_ADS_REFRESH_TOKEN saved to .env  ({len(refresh_token)} chars)")
    print("\nUpdate Railway (run in PowerShell):")
    print(f'  railway variables set GOOGLE_ADS_REFRESH_TOKEN="{refresh_token}"')
    print("\nUpdate GitHub Secret:")
    print(f'  gh secret set GOOGLE_ADS_REFRESH_TOKEN --body "{refresh_token}" --repo Rana96-run/nexa-performance-agent')


if __name__ == "__main__":
    main()
