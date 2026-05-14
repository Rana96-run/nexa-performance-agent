"""Search every workflow's actions for ones that set 'qoyod_source' (any value)."""
import os, sys, json, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# Get all workflow IDs
r = requests.get(f"{BASE}/automation/v3/workflows", headers=H, timeout=30)
flows = r.json().get("workflows", [])
print(f"Scanning {len(flows)} workflows for actions touching qoyod_source...\n")

def walk_actions(actions, path):
    """Recursively find SET_CONTACT_PROPERTY actions that set qoyod_source."""
    for a in actions or []:
        if a.get("type") == "SET_CONTACT_PROPERTY" and a.get("propertyName") == "qoyod_source":
            yield (path, a.get("newValue"))
        for child_key in ("acceptActions", "rejectActions"):
            for hit in walk_actions(a.get(child_key, []), path + f"→{a.get('actionId')}.{child_key[:6]}"):
                yield hit

setters_by_workflow = {}
for w in flows:
    wid = w.get("id")
    name = w.get("name", "?")
    r2 = requests.get(f"{BASE}/automation/v3/workflows/{wid}", headers=H, timeout=30)
    if r2.status_code != 200:
        continue
    detail = r2.json()
    hits = list(walk_actions(detail.get("actions", []), ""))
    if hits:
        setters_by_workflow[wid] = (name, w.get("enabled"), hits)

print(f"Found {len(setters_by_workflow)} workflows that set qoyod_source:\n")
for wid, (name, enabled, hits) in setters_by_workflow.items():
    print(f"━━━ [{wid}] {name}  enabled={enabled}")
    for path, val in hits:
        print(f"     SET qoyod_source = '{val}'  via {path}")
    print()
