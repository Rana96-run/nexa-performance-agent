"""
YouTube OAuth 2.0 flow — gets a refresh token for YouTube Analytics API.

Run from the project root:
    railway run python scripts/youtube_oauth.py

It will:
  1. Open the Google authorization URL in your browser
  2. Start a local server on port 8080 to catch the callback
  3. Exchange the code for tokens
  4. Discover and write YT_CHANNEL_ID to .env
  5. Write YT_REFRESH_TOKEN to .env
"""
from __future__ import annotations

import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
import requests
from dotenv import load_dotenv, set_key

load_dotenv(override=True)

CLIENT_ID     = os.getenv("YT_CLIENT_ID")
CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET")
REDIRECT_URI  = "http://localhost:8080/callback"
SCOPES        = " ".join([
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
])

_code: str | None = None
_done = threading.Event()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _code
        parsed = urlparse(self.path)
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
            error = params.get("error", ["unknown"])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"<h2>Auth failed: {error}. Close this tab and try again.</h2>".encode())
            _done.set()

    def log_message(self, *_):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: YT_CLIENT_ID or YT_CLIENT_SECRET not set in env.")
        return

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode({
            "response_type":  "code",
            "client_id":      CLIENT_ID,
            "redirect_uri":   REDIRECT_URI,
            "scope":          SCOPES,
            "access_type":    "offline",
            "prompt":         "consent",   # force refresh_token to be issued
            "state":          "nexa_yt_oauth",
        })
    )

    server = HTTPServer(("localhost", 8080), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\nOpening Google authorization in your browser...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    _done.wait(timeout=300)
    server.shutdown()

    if not _code:
        print("ERROR: no code received. Did you approve the app?")
        return

    print("Code received, exchanging for tokens...")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type":    "authorization_code",
        "code":          _code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }, timeout=15)
    r.raise_for_status()
    d = r.json()

    refresh = d.get("refresh_token", "")
    access  = d["access_token"]

    if not refresh:
        print("ERROR: no refresh_token in response. Did you use 'prompt=consent'?")
        print("Response:", d)
        return

    env_path = ".env"
    set_key(env_path, "YT_REFRESH_TOKEN", refresh)
    print(f"\nYT_REFRESH_TOKEN saved ({len(refresh)} chars)")

    # Discover channel ID
    ch_r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "id,snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {access}"},
        timeout=10,
    )
    if ch_r.ok:
        items = ch_r.json().get("items", [])
        if items:
            channel_id   = items[0]["id"]
            channel_name = items[0]["snippet"]["title"]
            set_key(env_path, "YT_CHANNEL_ID", channel_id)
            print(f"YT_CHANNEL_ID saved: {channel_id}  ({channel_name})")
        else:
            print("WARN: no channels found for this account — set YT_CHANNEL_ID manually")
    else:
        print(f"WARN: could not fetch channel ({ch_r.status_code}) — set YT_CHANNEL_ID manually")

    print("\nDone. Run 'railway run python collectors/youtube_bq.py' to test.")


if __name__ == "__main__":
    main()
