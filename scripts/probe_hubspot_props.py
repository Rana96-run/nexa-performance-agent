"""
probe_hubspot_props.py — list all HubSpot lead (0-8) properties + enum options.
Run: python scripts/probe_hubspot_props.py
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
if not TOKEN:
    print("ERROR: HUBSPOT_ACCESS_TOKEN not set in .env", file=sys.stderr)
    sys.exit(1)

SEARCH_TERMS = ("disqualif", "reason", "not_qual")


def main():
    url = "https://api.hubapi.com/crm/v3/properties/leads"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    params = {"limit": 500}

    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    data = r.json()

    results = data.get("results", [])
    print(f"Total lead properties returned: {len(results)}\n")

    matched = [
        prop for prop in results
        if any(term in prop.get("name", "").lower() for term in SEARCH_TERMS)
    ]

    print(f"Matching properties ({len(matched)} found):\n")
    print("=" * 70)

    for prop in sorted(matched, key=lambda p: p.get("name", "")):
        name  = prop.get("name", "")
        label = prop.get("label", "")
        ptype = prop.get("type", "")
        ftype = prop.get("fieldType", "")

        print(f"  name  : {name}")
        print(f"  label : {label}")
        print(f"  type  : {ptype} / fieldType: {ftype}")

        options = prop.get("options", [])
        if options:
            print(f"  options ({len(options)}):")
            for opt in sorted(options, key=lambda o: o.get("displayOrder", 9999)):
                val   = opt.get("value", "")
                lbl   = opt.get("label", "")
                hidden = opt.get("hidden", False)
                flag   = " [hidden]" if hidden else ""
                print(f"    - {val!r:40s}  {lbl}{flag}")
        else:
            print("  options: (none — not an enumeration)")

        print("-" * 70)


if __name__ == "__main__":
    main()
