"""
LinkedIn OAuth 2.0 flow — gets a fresh access + refresh token.

Run from the project root:
    python scripts/linkedin_oauth.py

It will:
  1. Open the LinkedIn authorization URL in your browser
  2. Start a local server on port 8080 to catch the callback
  3. Exchange the code for tokens
  4. Write LI_ACCESS_TOKEN and LI_REFRESH_TOKEN to .env
"""
from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
import requests
from dotenv import load_dotenv, set_key

load_dotenv(override=True)

CLIENT_ID     = os.getenv("LI_CLIENT_ID")
CLIENT_SECRET = os.getenv("LI_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("LI_REDIRECT_URI", "http://localhost:8080/callback")
SCOPES        = "r_ads r_ads_reporting rw_ads r_basicprofile"
# rw_organization_admin removed: causes unauthorized_scope_error in some app configurations.
# openid/profile/email removed: OIDC scopes not authorized for this app.

_code: str | None = None
_done = threading.Event()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _code
        parsed = urlparse(self.path)
        # Only process the OAuth callback path — ignore favicon, prefetch, etc.
        if not parsed.path.startswith("/callback"):
            self.send_response(204)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if code:
            _code = code
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorized. You can close this tab.</h2>")
            _done.set()
        else:
            # LinkedIn returned an error (user denied, or state mismatch)
            error = params.get("error", ["unknown"])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"<h2>Auth failed: {error}. Close this tab and try again.</h2>".encode())
            _done.set()

    def log_message(self, *_):
        pass


def main():
    auth_url = (
        "https://www.linkedin.com/oauth/v2/authorization?"
        + urlencode({
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": "nexa_li_oauth",
        })
    )

    server = HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("=== Paste this URL into your browser ===")
    print(auth_url)
    print("========================================")
    print("Waiting for callback (5 min timeout)...")
    # webbrowser.open(auth_url)  # disabled — paste the URL manually

    _done.wait(timeout=300)
    server.shutdown()

    if not _code:
        print("ERROR: no code received. Did you approve the app?")
        return

    print("Code received, exchanging for tokens...")
    r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type":    "authorization_code",
        "code":          _code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }, timeout=15)
    r.raise_for_status()
    d = r.json()

    access  = d["access_token"]
    refresh = d.get("refresh_token", "")

    env_path = ".env"
    set_key(env_path, "LI_ACCESS_TOKEN", access)
    if refresh:
        set_key(env_path, "LI_REFRESH_TOKEN", refresh)

    print(f"\nTokens saved to .env")
    print(f"  access_token  ({len(access)} chars): {access[:40]}...")
    if refresh:
        print(f"  refresh_token ({len(refresh)} chars): {refresh[:40]}...")

    # Quick validation — use ads accounts endpoint (no OIDC scope required)
    headers = {"Authorization": f"Bearer {access}", "LinkedIn-Version": "202502"}
    v = requests.get(
        "https://api.linkedin.com/v2/adAccountsV2?q=search&search.type.values[0]=BUSINESS",
        headers=headers, timeout=10,
    )
    if v.ok:
        print(f"\nToken valid — ads API reachable (status {v.status_code})")
    else:
        print(f"\nWARN: token saved but ads API returned {v.status_code}: {v.text[:200]}")


if __name__ == "__main__":
    main()
