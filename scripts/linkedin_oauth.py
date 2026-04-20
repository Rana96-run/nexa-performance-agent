"""
LinkedIn OAuth helper.
Opens the browser -> you sign in -> this script catches the redirect,
exchanges the code for an access token, and prints it.

Run:  python scripts/linkedin_oauth.py
Then paste LI_ACCESS_TOKEN into .env.
"""
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("LI_CLIENT_ID")
CLIENT_SECRET = os.getenv("LI_CLIENT_SECRET")
REDIRECT_URI = os.getenv("LI_REDIRECT_URI", "http://localhost:8080/callback")

# Community Management API scopes (organic) + Marketing (if approved)
SCOPES = [
    "r_organization_social",
    "rw_organization_admin",
    "r_ads",
    "r_ads_reporting",
    "r_basicprofile",
]

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

received = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if "code" in qs:
            received["code"] = qs["code"][0]
            self.wfile.write(b"<h2>OK. You can close this tab.</h2>")
        elif "error" in qs:
            received["error"] = qs.get("error_description", qs["error"])[0]
            self.wfile.write(f"<h2>Error: {received['error']}</h2>".encode())
        else:
            self.wfile.write(b"<h2>No code in query string.</h2>")

    def log_message(self, *a, **k):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Missing LI_CLIENT_ID / LI_CLIENT_SECRET in .env"); sys.exit(1)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": "qoyod",
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    print("Opening browser for LinkedIn sign-in...")
    print(url)
    webbrowser.open(url)

    host, port = "localhost", int(urlparse(REDIRECT_URI).port or 8080)
    server = HTTPServer((host, port), Handler)
    print(f"Listening on {host}:{port} for redirect...")
    while "code" not in received and "error" not in received:
        server.handle_request()

    if "error" in received:
        print("OAuth error:", received["error"]); sys.exit(1)

    print("Got code, exchanging for token...")
    r = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": received["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    if r.status_code >= 400:
        print("Token exchange failed:", r.status_code, r.text); sys.exit(1)
    tok = r.json()
    print("\n=== SUCCESS ===")
    print(f"LI_ACCESS_TOKEN={tok['access_token']}")
    print(f"(expires in {tok.get('expires_in', 0) // 86400} days)")
    if tok.get("refresh_token"):
        print(f"LI_REFRESH_TOKEN={tok['refresh_token']}")
    print("\nPaste the above into .env.")
    print("\nTo find your LI_ORGANIZATION_URN, run after pasting the token:")
    print("  python scripts/linkedin_oauth.py orgs")

    if len(sys.argv) > 1 and sys.argv[1] == "orgs":
        find_orgs(tok["access_token"])


def find_orgs(token):
    # Works with r_organization_social / rw_organization_admin
    r = requests.get(
        "https://api.linkedin.com/rest/organizationAcls",
        headers={
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": "202410",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
    )
    print(r.status_code, r.text[:2000])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "orgs":
        load_dotenv()
        tok = os.getenv("LI_ACCESS_TOKEN")
        if not tok:
            print("Set LI_ACCESS_TOKEN in .env first"); sys.exit(1)
        find_orgs(tok)
    else:
        main()
