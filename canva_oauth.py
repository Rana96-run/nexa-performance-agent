"""
Canva OAuth Helper with PKCE — generates access + refresh tokens.
Run once, click through Canva consent, tokens auto-saved to .env.
"""
import os
import base64
import hashlib
import secrets
import urllib.parse
import http.server
import threading
import webbrowser
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CANVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:8080/canva/callback"
PORT = 8080

SCOPES = " ".join([
    "brandtemplate:content:read",
    "brandtemplate:content:write",
    "brandtemplate:meta:read",
    "folder:read",
    "folder:write",
    "folder:permission:read",
    "design:content:read",
    "design:content:write",
    "design:meta:read",
    "design:permission:read",
    "design:permission:write",
    "asset:read",
    "asset:write",
    "comment:read",
    "app:read",
    "app:write",
])

ENV_PATH = Path(__file__).parent / ".env"


def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _update_env(access_token: str, refresh_token: str):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    set_access = set_refresh = False
    for line in lines:
        if line.startswith("# CANVA_ACCESS_TOKEN=") or line.startswith("CANVA_ACCESS_TOKEN="):
            out.append(f"CANVA_ACCESS_TOKEN={access_token}")
            set_access = True
        elif line.startswith("# CANVA_REFRESH_TOKEN=") or line.startswith("CANVA_REFRESH_TOKEN="):
            out.append(f"CANVA_REFRESH_TOKEN={refresh_token}")
            set_refresh = True
        else:
            out.append(line)
    if not set_access:
        out.append(f"CANVA_ACCESS_TOKEN={access_token}")
    if not set_refresh:
        out.append(f"CANVA_REFRESH_TOKEN={refresh_token}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


class Handler(http.server.BaseHTTPRequestHandler):
    verifier = None  # set before server starts

    def do_GET(self):
        if "/canva/callback" not in self.path:
            self.send_response(404)
            self.end_headers()
            return

        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)

        if "error" in params:
            err = params.get("error_description", params.get("error"))[0]
            print(f"\n[ERROR] Canva returned: {err}")
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Canva auth error</h1><pre>{err}</pre>".encode())
            threading.Thread(target=self.server.shutdown).start()
            return

        code = params.get("code", [None])[0]
        if not code:
            self.send_response(400)
            self.end_headers()
            return

        print("\n[OK] Got authorization code, exchanging for tokens...")

        # Canva requires Basic auth with client_id:client_secret for token exchange
        import base64 as _b64
        basic = _b64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

        resp = requests.post(
            "https://api.canva.com/rest/v1/oauth/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": Handler.verifier,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"\n[ERROR] Token exchange failed: {resp.status_code}")
            print(resp.text)
            self.send_response(500)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Token exchange failed</h1><pre>{resp.text}</pre>".encode())
            threading.Thread(target=self.server.shutdown).start()
            return

        tokens = resp.json()
        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in")

        print("\n" + "=" * 60)
        print("SUCCESS! Canva tokens generated.")
        print("=" * 60)
        print(f"Access token: {access[:30]}... (expires in {expires_in}s)")
        print(f"Refresh token: {refresh[:30]}...")
        print("=" * 60)

        _update_env(access, refresh)
        print(f"\n[OK] Saved to {ENV_PATH}")

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style='font-family:sans-serif;padding:40px;background:#0f1117;color:#e4e6f0;'>
        <h1 style='color:#00b894'>Canva Connected</h1>
        <p>Tokens saved. Return to your terminal.</p>
        </body></html>
        """)
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, *a, **kw):
        pass


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        raise SystemExit("CANVA_CLIENT_ID / CANVA_CLIENT_SECRET missing in .env")

    verifier, challenge = _pkce_pair()
    Handler.verifier = verifier

    auth_url = (
        "https://www.canva.com/api/oauth/authorize?"
        + urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "s256",
        })
    )

    print("Starting local callback server on http://127.0.0.1:8080/")
    print("\nOpening browser for Canva authorization...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    webbrowser.open(auth_url)
    server.serve_forever()
    print("\nDone.")
