"""Confirm campaign_id / ad_group_id / ad_id exist on Contact, Lead, Deal
and check whether any have a defined sync/calculated source."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}"}
BASE = "https://api.hubapi.com"

# Look up each property exactly by name across all 3 objects
OBJECTS = [("0-1", "Contact"), ("0-136", "Lead"), ("0-3", "Deal")]
NAMES = ["campaign_id", "ad_group_id", "ad_id",
         "lead_campaign_id_sync", "lead_adgroup_id_sync", "lead_ad_id_sync",
         "deal_campaign_id_sync", "deal_adgroup_id_sync", "deal_ad_id_sync"]

for obj_type, label in OBJECTS:
    print(f"\n=== {label} ({obj_type}) ===")
    r = requests.get(f"{BASE}/crm/v3/properties/{obj_type}", headers=H, timeout=30)
    if r.status_code != 200:
        print(f"  ERR {r.status_code}")
        continue
    by_name = {p["name"]: p for p in r.json().get("results", [])}
    for n in NAMES:
        if n in by_name:
            p = by_name[n]
            calc = "CALCULATED" if p.get("calculated") else "manual/synced"
            print(f"  {n:30s} EXISTS  type={p.get('type'):10s}  source={calc}")
