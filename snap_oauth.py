"""
Snapchat Marketing API OAuth — self-signed HTTPS local server.
Snap requires HTTPS redirect URIs. We use 127.0.0.1 with a self-signed cert.

IMPORTANT: In Snap Business Manager -> your app -> OAuth settings, add:
  Redirect URI: https://127.0.0.1:8443/snap/callback

Browser will warn about self-signed cert -> click "Advanced" -> "Proceed".
"""
import os, urllib.parse, http.server, threading, ssl, webbrowser, requests, ipaddress, datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("SNAPCHAT_CLIENT_ID")
CLIENT_SECRET = os.getenv("SNAPCHAT_CLIENT_SECRET")
REDIRECT_URI = "https://127.0.0.1:8443/snap/callback"
PORT = 8443
SCOPES = "snapchat-marketing-api"
ENV_PATH = Path(__file__).parent / ".env"
CERT_PATH = Path(__file__).parent / ".snap_cert.pem"
KEY_PATH = Path(__file__).parent / ".snap_key.pem"


def _make_cert():
    if CERT_PATH.exists() and KEY_PATH.exists():
        return
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    cert = (x509.CertificateBuilder()
        .subject_name(subj).issuer_name(subj)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256()))
    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print("[OK] Generated self-signed cert")


def _update_env(access, refresh):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out, a, r = [], False, False
    for line in lines:
        if line.startswith("SNAPCHAT_ACCESS_TOKEN=") or line.startswith("# SNAPCHAT_ACCESS_TOKEN="):
            out.append(f"SNAPCHAT_ACCESS_TOKEN={access}"); a = True
        elif line.startswith("SNAPCHAT_REFRESH_TOKEN=") or line.startswith("# SNAPCHAT_REFRESH_TOKEN="):
            out.append(f"SNAPCHAT_REFRESH_TOKEN={refresh}"); r = True
        else:
            out.append(line)
    if not a: out.append(f"SNAPCHAT_ACCESS_TOKEN={access}")
    if not r: out.append(f"SNAPCHAT_REFRESH_TOKEN={refresh}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if "/snap/callback" not in self.path:
            self.send_response(404); self.end_headers(); return
        p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "error" in p:
            err = p.get("error_description", p.get("error"))[0]
            print(f"\n[ERROR] {err}")
            self.send_response(400); self.end_headers()
            self.wfile.write(f"<pre>{err}</pre>".encode())
            threading.Thread(target=self.server.shutdown).start(); return
        code = p.get("code", [None])[0]
        if not code: self.send_response(400); self.end_headers(); return
        print("\n[OK] Got code, exchanging...")
        resp = requests.post("https://accounts.snapchat.com/login/oauth2/access_token",
            data={"grant_type":"authorization_code","code":code,
                  "client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,
                  "redirect_uri":REDIRECT_URI}, timeout=30)
        if resp.status_code != 200:
            print(f"[ERROR] {resp.status_code}: {resp.text}")
            self.send_response(500); self.end_headers()
            self.wfile.write(f"<pre>{resp.text}</pre>".encode())
            threading.Thread(target=self.server.shutdown).start(); return
        t = resp.json()
        a, r = t.get("access_token"), t.get("refresh_token")
        print("\n" + "="*60 + "\nSUCCESS — Snap tokens saved\n" + "="*60)
        print(f"access:  {a[:30]}...\nrefresh: {r[:30]}...")
        _update_env(a, r)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers()
        self.wfile.write(b"<html><body style='font-family:sans-serif;padding:40px;background:#0f1117;color:#e4e6f0'><h1 style='color:#00b894'>Snap Connected</h1><p>Return to terminal.</p></body></html>")
        threading.Thread(target=self.server.shutdown).start()
    def log_message(self, *a, **k): pass


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        raise SystemExit("SNAPCHAT_CLIENT_ID / SNAPCHAT_CLIENT_SECRET missing")
    _make_cert()

    auth_url = "https://accounts.snapchat.com/login/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": SCOPES})

    server = http.server.HTTPServer(("127.0.0.1", PORT), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print(f"Starting HTTPS server on {REDIRECT_URI}")
    print(f"\nACTION NEEDED: in Snap app settings, ensure redirect URI is exactly:\n   {REDIRECT_URI}\n")
    print("Opening browser. On the cert warning: Advanced -> Proceed to 127.0.0.1.")
    print(f"If browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)
    server.serve_forever()
