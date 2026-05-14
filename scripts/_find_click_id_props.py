"""Find which property names on Lead Module hold Google + Microsoft click IDs."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

H = {"Authorization": f"Bearer {os.environ['HUBSPOT_ACCESS_TOKEN']}"}

for obj_id, label in [("0-136", "Lead Module"), ("0-1", "Contact")]:
    r = requests.get(f"https://api.hubapi.com/crm/v3/properties/{obj_id}", headers=H, timeout=30)
    props = {p["name"]: p.get("label", "") for p in r.json().get("results", [])}
    print(f"\n=== {label} ({obj_id}) — click_id properties ===")
    for n in sorted(props):
        low = n.lower()
        if "click" in low or "gclid" in low or "msclkid" in low:
            print(f"  {n:35s}  → {props[n]}")
