"""
Lists projects inside each Asana portfolio from .env so you can pick
real project GIDs to put into ASANA_PROJECT_* variables.

Run:
    python scripts/asana_list_projects.py
"""
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
if not TOKEN:
    sys.exit("Missing ASANA_ACCESS_TOKEN")

PORTFOLIOS = {
    "daily_activity": os.getenv("ASANA_PORTFOLIO_DAILY_ACTIVITY"),
    "optimization":   os.getenv("ASANA_PORTFOLIO_OPTIMIZATION"),
    "seasonal":       os.getenv("ASANA_PORTFOLIO_SEASONAL"),
}

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}


def list_items(portfolio_gid):
    url = f"https://app.asana.com/api/1.0/portfolios/{portfolio_gid}/items"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def main():
    print("\nCopy the GIDs you want into .env as:")
    print("  ASANA_PROJECT_DAILY_ACTIVITY=...")
    print("  ASANA_PROJECT_OPTIMIZATION=...")
    print("  ASANA_PROJECT_CAMPAIGNS_HUB=...")
    print("  ASANA_PROJECT_SEASONAL=...\n")

    for key, gid in PORTFOLIOS.items():
        if not gid:
            print(f"[{key}] -- no portfolio GID set in .env, skipping")
            continue
        print(f"\n=== Portfolio: {key}  (gid={gid}) ===")
        try:
            items = list_items(gid)
            if not items:
                print("  (empty)")
            for it in items:
                print(f"  {it.get('gid'):>20}   {it.get('name')}   [{it.get('resource_type')}]")
        except requests.HTTPError as e:
            print(f"  ERROR: {e}  body={e.response.text[:200]}")


if __name__ == "__main__":
    main()
