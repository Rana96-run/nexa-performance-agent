import os, sys, requests, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}"}

# flowId from v3 migrationStatus
r = requests.get("https://api.hubapi.com/automation/v4/flows/3613421768", headers=H, timeout=30)
print("v4 status:", r.status_code)
if r.status_code == 200:
    with open("_workflow_v4_3613421768.json", "w", encoding="utf-8") as f:
        json.dump(r.json(), f, indent=2, ensure_ascii=False)
    print(f"Saved {len(json.dumps(r.json()))} chars")
else:
    print(r.text[:500])
