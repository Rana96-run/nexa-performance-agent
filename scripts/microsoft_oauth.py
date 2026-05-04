"""
Microsoft Ads OAuth 2.0 flow — mints MS_REFRESH_TOKEN.

Run from the project root:
    python scripts/microsoft_oauth.py

Steps:
  1. Opens Microsoft sign-in in your browser
  2. Local server on port 8080 catches the callback
  3. Exchanges the code for access + refresh tokens
  4. Writes MS_REFRESH_TOKEN to .env and prints the Railway set command
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

CLIENT_ID     = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("MS_REDIRECT_URI", "http://localhost:8080/ms-ads/callback")

AUTH_URL  = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE     = "https://ads.microsoft.com/msads.manage offline_access"

_code: str | None = None
_done = threading.Event()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _code
        params = parse_qs(urlparse(self.path).query)
        _code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        self.send_response(200)
        self.end_headers()
        if error:
            msg = f"<h2>Error: {error}</h2><p>{params.get('error_description', [''])[0]}</p>"
        else:
            msg = "<h2>Authorized. You can close this tab.</h2>"
        self.wfile.write(msg.encode())
        _done.set()

    def log_message(self, *_):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: MS_CLIENT_ID / MS_CLIENT_SECRET not set in .env")
        sys.exit(1)

    parsed = urlparse(REDIRECT_URI)
    port   = parsed.port or 8080

    auth_url = AUTH_URL + "?" + urlencode({
        "response_type": "code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPE,
        "state":         "nexa_ms_oauth",
        "prompt":        "select_account",
    })

    server = HTTPServer(("localhost", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print(f"\nOpening Microsoft sign-in in your browser...")
    print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    _done.wait(timeout=300)
    server.shutdown()

    if not _code:
        print("ERROR: no code received. Did you complete sign-in and approve the app?")
        sys.exit(1)

    print("Code received — exchanging for tokens...")
    r = requests.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "code":          _code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         SCOPE,
    }, timeout=15)
    r.raise_for_status()
    tokens = r.json()

    refresh_token = tokens.get("refresh_token", "")
    if not refresh_token:
        print("ERROR: no refresh_token in response — check offline_access scope was granted")
        print(f"Response: {tokens}")
        sys.exit(1)

    set_key(".env", "MS_REFRESH_TOKEN", refresh_token)
    print(f"\nMS_REFRESH_TOKEN saved to .env  ({len(refresh_token)} chars)")
    print(f"\nSet on Railway (run in PowerShell):")
    print(f"  railway variables set MS_REFRESH_TOKEN=\"{refresh_token}\"")


if __name__ == "__main__":
    main()
