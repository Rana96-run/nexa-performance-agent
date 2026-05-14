"""Fetch the active 'Digital Marketing: Populating Qoyod Sources' workflow
via v4 flows API which returns the actual IF/THEN action tree."""
import os, sys, json, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# Active workflow ID
WORKFLOW_ID = 56383267
print(f"Fetching workflow {WORKFLOW_ID} via v4 flows API...")

# v4 endpoint
r = requests.get(f"{BASE}/automation/v4/flows/{WORKFLOW_ID}", headers=H, timeout=30)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    detail = r.json()
    fn = f"_workflow_v4_{WORKFLOW_ID}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(detail, f, indent=2, ensure_ascii=False)
    print(f"Saved to {fn}")
    print(f"Top-level keys: {list(detail.keys())}")
    print(f"Action count: {len(detail.get('actions', []))}")
    # Sample first few actions
    for i, a in enumerate(detail.get("actions", [])[:5]):
        print(f"\nAction {i}: actionId={a.get('actionId')}  type={a.get('type')}  actionTypeId={a.get('actionTypeId')}")
        print(f"  keys: {list(a.keys())}")
else:
    print(f"ERR: {r.text[:400]}")
    # Fall back — list flows to see if id changed
    print("\nFalling back to list flows...")
    r2 = requests.get(f"{BASE}/automation/v4/flows", headers=H, timeout=30)
    if r2.status_code == 200:
        for w in r2.json().get("results", [])[:20]:
            if "qoyod" in (w.get("name") or "").lower():
                print(f"  id={w.get('id')}  name='{w.get('name')}'  isEnabled={w.get('isEnabled')}")
