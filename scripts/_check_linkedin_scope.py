"""Verify the LinkedIn access token has rw_organization_admin scope.
LinkedIn's introspection endpoint returns the scopes attached to a token."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ.get("LI_ACCESS_TOKEN")
CLIENT_ID = os.environ.get("LI_CLIENT_ID")
CLIENT_SECRET = os.environ.get("LI_CLIENT_SECRET")

if not TOKEN:
    print("LI_ACCESS_TOKEN not set in env")
    sys.exit(1)

# Introspection endpoint
r = requests.post(
    "https://www.linkedin.com/oauth/v2/introspectToken",
    data={
        "token": TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
    timeout=30,
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"\nActive: {data.get('active')}")
    print(f"Scope:  {data.get('scope', 'N/A')}")
    print(f"Expires (epoch): {data.get('expires_at')}")
    # Check for rw_organization_admin
    scope = data.get("scope") or ""
    if "rw_organization_admin" in scope:
        print("\n✓ rw_organization_admin scope present — clone_campaign_creatives() will work")
    else:
        print("\n✗ rw_organization_admin scope MISSING — re-run scripts/linkedin_oauth.py")
else:
    print(f"Error: {r.text[:300]}")
