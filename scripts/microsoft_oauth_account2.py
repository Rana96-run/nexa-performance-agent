"""
Microsoft Ads OAuth — device_code flow for Account 2 (public client).

Run from project root:
    railway run python scripts/microsoft_oauth_account2.py

Steps:
  1. Fetches a device code from Azure AD
  2. Prints a short URL + code — open in browser, sign in with @qoyod.com account
  3. Polls until user approves
  4. Writes MS_REFRESH_TOKEN_2 to .env and prints the Railway set command
"""
from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv, set_key

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(override=True)

CLIENT_ID = os.getenv("MS_CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID", "common")
SCOPE     = "https://ads.microsoft.com/msads.manage offline_access"

DEVICE_CODE_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode"
TOKEN_URL       = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"


def main():
    if not CLIENT_ID:
        print("ERROR: MS_CLIENT_ID not set")
        sys.exit(1)

    # Step 1 — request device code
    r = requests.post(DEVICE_CODE_URL, data={
        "client_id": CLIENT_ID,
        "scope":     SCOPE,
    }, timeout=15)
    r.raise_for_status()
    dc = r.json()

    print("\n" + "=" * 60)
    print(dc["message"])
    print("=" * 60)
    print("\nSign in with your @qoyod.com account.")
    print("Waiting for approval...\n")

    interval = dc.get("interval", 5)
    expires  = time.time() + dc.get("expires_in", 900)

    while time.time() < expires:
        time.sleep(interval)
        poll = requests.post(TOKEN_URL, data={
            "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
            "client_id":   CLIENT_ID,
            "device_code": dc["device_code"],
        }, timeout=15)
        body = poll.json()

        if "refresh_token" in body:
            refresh_token = body["refresh_token"]
            set_key(".env", "MS_REFRESH_TOKEN_2", refresh_token)
            print(f"MS_REFRESH_TOKEN_2 saved to .env  ({len(refresh_token)} chars)")
            print(f"\nRun this to update Railway:")
            print(f'  railway variables set MS_REFRESH_TOKEN_2="{refresh_token}"')
            return

        err = body.get("error", "")
        if err == "authorization_pending":
            print(".", end="", flush=True)
            continue
        elif err == "slow_down":
            interval += 5
            continue
        else:
            print(f"\nERROR: {err} — {body.get('error_description', '')}")
            sys.exit(1)

    print("\nERROR: timed out waiting for approval.")
    sys.exit(1)


if __name__ == "__main__":
    main()
