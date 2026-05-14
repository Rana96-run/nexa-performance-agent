"""Fetch the 'Digital Marketing: Populating Qoyod Sources' workflow and dump
its full definition so we can analyse what it does."""
import os, sys, json, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# 1. List all workflows
r = requests.get(f"{BASE}/automation/v3/workflows", headers=H, timeout=30)
if r.status_code != 200:
    print(f"List ERR {r.status_code}: {r.text[:300]}")
    sys.exit(1)

data = r.json()
flows = data.get("workflows", [])
print(f"Total workflows: {len(flows)}\n")

# Find the Qoyod source ones
matching = [w for w in flows if "qoyod" in (w.get("name") or "").lower()]
print(f"Workflows matching 'qoyod' in name: {len(matching)}")
for w in matching:
    print(f"  id={w.get('id')}  enabled={w.get('enabled')}  name='{w.get('name')}'")
print()

# 2. Pull each one's full definition
for w in matching:
    wid = w.get("id")
    name = w.get("name")
    print(f"\n{'='*80}\nFetching workflow {wid}: {name}\n{'='*80}")
    r2 = requests.get(f"{BASE}/automation/v3/workflows/{wid}", headers=H, timeout=30)
    if r2.status_code != 200:
        print(f"  ERR {r2.status_code}: {r2.text[:200]}")
        continue
    detail = r2.json()
    # Dump to file for inspection
    fn = f"_workflow_{wid}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(detail, f, indent=2, ensure_ascii=False)
    print(f"  Saved full definition to {fn}")
    print(f"  Top-level keys: {list(detail.keys())[:20]}")
    print(f"  Type: {detail.get('type')}")
    print(f"  Action count: {len(detail.get('actions', []))}")
    print(f"  Enrollment criteria: {len(detail.get('enrollmentCriteria', {}).get('listFilterBranch', {}).get('filters', []))} filters")
