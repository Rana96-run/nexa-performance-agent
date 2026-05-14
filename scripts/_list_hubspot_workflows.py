"""List HubSpot workflows and find ones related to setting qoyod_source.
HubSpot has multiple workflow APIs:
  - /automation/v3/workflows (legacy v3, list/read)
  - /automation/v4/flows    (new flow API, more detail but stricter access)
We try both."""
import os, sys, json, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

def sec(t): print(f"\n{'='*70}\n{t}\n{'='*70}")

# Try v3 workflows API
sec("1. /automation/v3/workflows — list all workflows")
r = requests.get(f"{BASE}/automation/v3/workflows", headers=H, timeout=30)
if r.status_code == 200:
    data = r.json()
    flows = data.get("workflows", []) or data.get("results", [])
    print(f"  Got {len(flows)} workflows")
    for w in flows[:50]:
        wid = w.get("id") or w.get("workflowId")
        name = w.get("name", "—")
        enabled = w.get("enabled")
        print(f"  id={wid}  enabled={enabled}  name='{name}'")
else:
    print(f"  ERR {r.status_code}: {r.text[:200]}")

# Try v4 flows API
sec("2. /automation/v4/flows — list new-style flows")
r4 = requests.get(f"{BASE}/automation/v4/flows", headers=H, timeout=30)
if r4.status_code == 200:
    flows4 = r4.json().get("results", [])
    print(f"  Got {len(flows4)} flows")
    for w in flows4[:50]:
        print(f"  id={w.get('id')}  enabled={w.get('isEnabled')}  name='{w.get('name')}'")
else:
    print(f"  ERR {r4.status_code}: {r4.text[:200]}")
