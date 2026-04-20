"""
Microsoft Ads OAuth helper — generates refresh token.
Uses Azure AD v2 endpoint with the tenant-specific authority.

Requires in Azure app:
  Authentication -> Platform (Web) -> Redirect URI: http://localhost:8080/microsoft/callback
  API permissions -> Microsoft Advertising -> delegated: ads.manage  +  offline_access
"""
import os, urllib.parse, http.server, threading, webbrowser, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("MS_CLIENT_ID")
CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
TENANT_ID = os.getenv("MS_TENANT_ID", "common")
REDIRECT_URI = os.getenv("MS_REDIRECT_URI", "http://localhost:8080/microsoft/callback")
PORT = int(REDIRECT_URI.split(":")[2].split("/")[0])

SCOPES = "https://ads.microsoft.com/msads.manage offline_access"
AUTH_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"

ENV_PATH = Path(__file__).parent / ".env"


def _update_env(refresh: str, access: str = ""):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out, set_r, set_a = [], False, False
    for line in lines:
        if line.startswith("MS_REFRESH_TOKEN=") or line.startswith("# MS_REFRESH_TOKEN="):
            out.append(f"MS_REFRESH_TOKEN={refresh}"); set_r = True
        elif line.startswith("MS_ACCESS_TOKEN=") or line.startswith("# MS_ACCESS_TOKEN="):
            if access:
                out.append(f"MS_ACCESS_TOKEN={access}"); set_a = True
            else:
                out.append(line)
        else:
            out.append(line)
    if not set_r:
        out.append(f"MS_REFRESH_TOKEN={refresh}")
    if access and not set_a:
        out.append(f"MS_ACCESS_TOKEN={access}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if "/microsoft/callback" not in self.path:
            self.send_response(404); self.end_headers(); return
        p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "error" in p:
            err = p.get("error_description", p.get("error"))[0]
            print(f"\n[ERROR] {err}")
            self.send_response(400); self.send_header("Content-Type","text/html"); self.end_headers()
            self.wfile.write(f"<h1>Auth error</h1><pre>{err}</pre>".encode())
            threading.Thread(target=self.server.shutdown).start(); return
        code = p.get("code", [None])[0]
        if not code:
            self.send_response(400); self.end_headers(); return

        print("\n[OK] Got auth code. Exchanging for tokens...")
        r = requests.post(TOKEN_URL, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
            "scope": SCOPES,
        }, timeout=30)

        if r.status_code != 200:
            print(f"\n[ERROR] Token exchange failed: {r.status_code}\n{r.text}")
            self.send_response(500); self.send_header("Content-Type","text/html"); self.end_headers()
            self.wfile.write(f"<h1>Token exchange failed</h1><pre>{r.text}</pre>".encode())
            threading.Thread(target=self.server.shutdown).start(); return

        t = r.json()
        refresh = t.get("refresh_token")
        access = t.get("access_token")
        print("\n" + "="*60 + "\nSUCCESS — Microsoft Ads tokens received\n" + "="*60)
        print(f"Refresh: {refresh[:40]}...")
        print(f"Access:  {access[:40]}... (expires in {t.get('expires_in')}s)")
        _update_env(refresh, access)
        print(f"\n[OK] Saved to {ENV_PATH}")

        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
        self.wfile.write(b"<html><body style='font-family:sans-serif;padding:40px;background:#0f1117;color:#e4e6f0'><h1 style='color:#00b894'>Microsoft Ads Connected</h1><p>Return to terminal.</p></body></html>")
        threading.Thread(target=self.server.shutdown).start()
    def log_message(self, *a, **k): pass


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        raise SystemExit("MS_CLIENT_ID / MS_CLIENT_SECRET missing in .env")

    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "response_mode": "query",
        "scope": SCOPES,
        "prompt": "consent",
    })

    print(f"Starting callback server on {REDIRECT_URI}")
    print(f"Using tenant: {TENANT_ID}")
    print(f"\nOpening browser...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")

    server = http.server.HTTPServer(("localhost", PORT), H)
    webbrowser.open(auth_url)
    server.serve_forever()
