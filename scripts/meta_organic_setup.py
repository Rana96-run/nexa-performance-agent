"""
Meta organic setup helper.
Given META_USER_TOKEN_SHORT (from Graph API Explorer), exchanges it for a
long-lived user token, then finds all Pages you admin, their permanent Page
Access Tokens, and the linked Instagram Business account.

Run:  python scripts/meta_organic_setup.py
Then paste the 3 values into .env.

Needs META_APP_ID and META_APP_SECRET in .env (same app used for Meta Ads).
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Force UTF-8 on Windows consoles so Arabic page names don't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

GRAPH = "https://graph.facebook.com/v21.0"


def main():
    short = os.getenv("META_USER_TOKEN_SHORT")
    app_id = os.getenv("META_APP_ID") or os.getenv("FB_APP_ID")
    app_sec = os.getenv("META_APP_SECRET") or os.getenv("FB_APP_SECRET")

    if not short:
        print("Missing META_USER_TOKEN_SHORT in .env"); sys.exit(1)
    if not app_id or not app_sec:
        print("Missing META_APP_ID / META_APP_SECRET in .env.")
        print("Find them at https://developers.facebook.com/apps -> your app -> Settings > Basic")
        sys.exit(1)

    # 1. Short -> long-lived user token (60 days)
    r = requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_sec,
        "fb_exchange_token": short,
    })
    if r.status_code >= 400:
        print("Exchange failed:", r.status_code, r.text); sys.exit(1)
    long_user = r.json()["access_token"]
    print(f"[OK] Long-lived user token (60 days): {long_user[:40]}...\n")

    # 2. List pages + their permanent tokens
    r = requests.get(f"{GRAPH}/me/accounts", params={
        "access_token": long_user,
        "fields": "id,name,access_token",
        "limit": 100,
    })
    pages = r.json().get("data", [])
    if not pages:
        print("No pages found. You need to be an admin of at least one FB Page.")
        sys.exit(1)

    print(f"[OK] Found {len(pages)} page(s):\n")
    for p in pages:
        pid = p["id"]
        # Lookup linked IG business account
        r2 = requests.get(f"{GRAPH}/{pid}", params={
            "access_token": p["access_token"],
            "fields": "instagram_business_account,name",
        })
        ig = r2.json().get("instagram_business_account", {}).get("id")
        print(f"--- Page: {p['name']} ---")
        print(f"  META_FB_PAGE_ID={pid}")
        print(f"  META_IG_BUSINESS_ID={ig or '(none linked)'}")
        print(f"  META_PAGE_ACCESS_TOKEN={p['access_token']}")
        print()

    print("Pick the Qoyod page above and paste those 3 values into .env.")


if __name__ == "__main__":
    main()
