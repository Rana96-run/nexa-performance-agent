"""
Google Ads OAuth Helper - generates a refresh token.
Run once to get your GOOGLE_ADS_REFRESH_TOKEN.
"""
import http.server
import urllib.parse
import requests
import webbrowser
import json
import threading

CLIENT_ID = "160399108734-9tiflh39bn41r9lq245ejgf6bh2tqtgg.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REDIRECT_URI = "http://localhost:8080/"
SCOPES = "https://www.googleapis.com/auth/adwords"
PORT = 8080

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/?code=") or "code=" in self.path:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "code" in params:
                code = params["code"][0]
                print(f"\n[OK] Got auth code")

                token_resp = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "redirect_uri": REDIRECT_URI,
                        "grant_type": "authorization_code",
                    },
                )

                if token_resp.status_code == 200:
                    tokens = token_resp.json()
                    refresh = tokens.get("refresh_token", "N/A")
                    access = tokens.get("access_token", "N/A")
                    print("\n" + "="*60)
                    print("SUCCESS! Refresh token generated.")
                    print("="*60)
                    print(f"\nRefresh Token:\n{refresh}\n")
                    print(f"Access Token (expires in {tokens.get('expires_in', 0)}s):\n{access[:50]}...\n")
                    print("Add to .env:")
                    print(f"GOOGLE_ADS_REFRESH_TOKEN={refresh}")
                    print("="*60)

                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    html = f"""
                    <html><body style='font-family:sans-serif;padding:40px;background:#0f1117;color:#e4e6f0;'>
                    <h1 style='color:#00b894'>Success!</h1>
                    <p>Refresh token generated. Return to your terminal to copy it.</p>
                    <p><strong>Refresh Token (first 40 chars):</strong><br>
                    <code>{refresh[:40]}...</code></p>
                    <p>You can close this window.</p>
                    </body></html>
                    """
                    self.wfile.write(html.encode())
                else:
                    print(f"\n[ERROR] {token_resp.status_code}: {token_resp.text}")
                    self.send_response(500)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"<html><body><h1>Error</h1><pre>{token_resp.text}</pre></body></html>".encode())
            else:
                error = params.get("error", ["unknown"])[0]
                print(f"\n[ERROR] Auth failed: {error}")
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(f"<html><body><h1>Auth Error: {error}</h1></body></html>".encode())

            threading.Thread(target=self.server.shutdown).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    print(f"Starting local server on {REDIRECT_URI}")
    print(f"\nOpening browser for Google authorization...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")

    server = http.server.HTTPServer(("localhost", PORT), OAuthHandler)
    webbrowser.open(auth_url)
    server.serve_forever()
