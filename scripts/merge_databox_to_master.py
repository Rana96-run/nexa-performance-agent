#!/usr/bin/env python3
"""
Merge Databox push chain from standalone workflow 7ZEROvwTg3UrGAP6
into Master Performance Workflow T8icImtZFLYeCa7e, then deactivate
the standalone workflow.

Run: python scripts/merge_databox_to_master.py
"""
import json, urllib.request, urllib.error, sys, uuid, copy
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

N8N_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIyYTZlMDMwNC0wN2RhLTRjNzktYTUwNi0zYzkyYjU5ODFiZDEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjA2Yjk1Y2YtNzJiOS00ZGM0LWIxOTAtNTY0Y2QyNzdhMDNiIiwiaWF0IjoxNzgxMTgxODU3fQ"
    ".UvVwQcF0-bW8ipJlgSTPEYe1Zg8tdJE3ZoJ-vJIFi8s"
)
BASE    = "https://qoyod.app.n8n.cloud"
MASTER  = "T8icImtZFLYeCa7e"
DATABOX = "7ZEROvwTg3UrGAP6"

POSITION_OFFSET = [3000, 0]

PUT_FIELDS = {"name", "nodes", "connections", "staticData", "pinData", "settings"}
SETTINGS_ALLOWED = {
    "executionOrder", "saveManualExecutions", "saveExecutionProgress",
    "saveDataSuccessExecution", "saveDataErrorExecution", "callerPolicy",
    "executionTimeout", "timezone", "errorWorkflow", "callerIds"
}


def req(method, path, body=None):
    url  = BASE + "/api/v1" + path
    data = json.dumps(body).encode() if body else None
    r    = urllib.request.Request(
        url, data=data,
        headers={"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        print(f"  HTTP {e.code} {e.reason}: {body_bytes.decode('utf-8', errors='replace')}")
        raise


# ─────────────────────────────────────────────────────────────
# STEP 1 — Fetch both workflows
# ─────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1 — Fetching both workflows")
print("=" * 60)

master  = req("GET", f"/workflows/{MASTER}")
databox = req("GET", f"/workflows/{DATABOX}")

print(f"\nMaster workflow: {master['name']}  (active={master.get('active')})")
print("  Nodes:")
for n in master["nodes"]:
    print(f"    [{n['type'].split('.')[-1]}]  {n['name']}")

print(f"\nDatabox workflow: {databox['name']}  (active={databox.get('active')})")
print("  Nodes:")
for n in databox["nodes"]:
    print(f"    [{n['type'].split('.')[-1]}]  {n['name']}")


# ─────────────────────────────────────────────────────────────
# STEP 2 — Identify hook point in Master
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2 — Identifying hook node in Master")
print("=" * 60)

FRESHNESS_CANDIDATES = [
    "IF · Data Fresh?", "IF - Data Fresh?", "IF · Data fresh?",
    "IF - Data fresh?", "Data Fresh?", "If Data Fresh",
]

hook_node = None
for n in master["nodes"]:
    if n["name"] in FRESHNESS_CANDIDATES:
        hook_node = n
        break

if hook_node is None:
    # Try partial match
    for n in master["nodes"]:
        if "fresh" in n["name"].lower() and n["type"].lower().endswith("if"):
            hook_node = n
            break

if hook_node is None:
    # Fall back to Schedule Trigger
    for n in master["nodes"]:
        if "scheduleTrigger" in n["type"] or "scheduletrigger" in n["type"].lower():
            hook_node = n
            break

if hook_node is None:
    # Last resort: first node
    hook_node = master["nodes"][0]

hook_node_name = hook_node["name"]
print(f"  Hook node found: '{hook_node_name}'  (type={hook_node['type']})")


# ─────────────────────────────────────────────────────────────
# STEP 3 — Extract Databox chain (exclude Schedule trigger)
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3 — Extracting Databox chain nodes")
print("=" * 60)

def is_schedule_trigger(node):
    t = node.get("type", "").lower()
    return "scheduletrigger" in t or t == "n8n-nodes-base.scheduletrigger"

db_trigger = None
db_chain_nodes = []
for n in databox["nodes"]:
    if is_schedule_trigger(n):
        db_trigger = n
        print(f"  Databox trigger (excluded): '{n['name']}'")
    else:
        db_chain_nodes.append(n)
        print(f"  Chain node (included): '{n['name']}'  [{n['type'].split('.')[-1]}]")

if db_trigger is None:
    print("  WARNING: No schedule trigger found in Databox workflow!")


# ─────────────────────────────────────────────────────────────
# STEP 4 — Find entry nodes (what trigger connected to)
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 4 — Finding Databox entry nodes")
print("=" * 60)

db_conns = databox.get("connections", {})
entry_node_names = []

if db_trigger:
    trigger_name = db_trigger["name"]
    trigger_conns = db_conns.get(trigger_name, {})
    for output_group in trigger_conns.get("main", []):
        for conn in output_group:
            entry_node_names.append(conn["node"])

if not entry_node_names:
    # If no trigger found, treat first chain nodes with no incoming connections as entries
    all_target_names = set()
    for src_node_conns in db_conns.values():
        for output_group in src_node_conns.get("main", []):
            for conn in output_group:
                all_target_names.add(conn["node"])
    for n in db_chain_nodes:
        if n["name"] not in all_target_names:
            entry_node_names.append(n["name"])

print(f"  Entry nodes (will connect from hook): {entry_node_names}")


# ─────────────────────────────────────────────────────────────
# STEP 5 — Add Databox nodes to Master with new IDs + position offset
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 5 — Adding Databox nodes to Master")
print("=" * 60)

# Build name→new_id mapping for connection rewiring if needed
old_id_to_name = {}
name_to_new_id = {}

new_nodes = []
for n in db_chain_nodes:
    new_n = copy.deepcopy(n)
    old_id = n.get("id", "")
    new_id = str(uuid.uuid4())
    new_n["id"] = new_id
    old_id_to_name[old_id] = n["name"]
    name_to_new_id[n["name"]] = new_id

    # Offset position
    orig_pos = n.get("position", [0, 0])
    new_n["position"] = [orig_pos[0] + POSITION_OFFSET[0], orig_pos[1] + POSITION_OFFSET[1]]

    print(f"  Added: '{new_n['name']}'  id={new_id}  pos={new_n['position']}")
    new_nodes.append(new_n)

master["nodes"].extend(new_nodes)
print(f"  Total Master nodes now: {len(master['nodes'])}")


# ─────────────────────────────────────────────────────────────
# STEP 6 — Wire connections
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 6 — Wiring connections")
print("=" * 60)

master_conns = master.get("connections", {})

# 6a — Copy all intra-Databox connections (exclude those originating from trigger)
chain_node_names = {n["name"] for n in db_chain_nodes}
excluded_src = {db_trigger["name"]} if db_trigger else set()

for src_name, src_conns in db_conns.items():
    if src_name in excluded_src:
        continue  # skip trigger's connections — we'll re-wire from hook
    if src_name not in chain_node_names:
        continue  # skip anything not in our chain

    if src_name not in master_conns:
        master_conns[src_name] = {}
    if "main" not in master_conns[src_name]:
        master_conns[src_name]["main"] = []

    for i, output_group in enumerate(src_conns.get("main", [])):
        # Extend master_conns[src_name]["main"] to cover index i
        while len(master_conns[src_name]["main"]) <= i:
            master_conns[src_name]["main"].append([])
        for conn in output_group:
            if conn["node"] in chain_node_names:
                master_conns[src_name]["main"][i].append(dict(conn))
                print(f"  Intra-chain: '{src_name}' → '{conn['node']}'  (output {i})")

# 6b — Wire hook node to each Databox entry node
if hook_node_name not in master_conns:
    master_conns[hook_node_name] = {}
if "main" not in master_conns[hook_node_name]:
    master_conns[hook_node_name]["main"] = []

# Use output index 0 (true branch for IF, or single output for Schedule)
if len(master_conns[hook_node_name]["main"]) == 0:
    master_conns[hook_node_name]["main"].append([])

for entry_name in entry_node_names:
    conn = {"node": entry_name, "type": "main", "index": 0}
    master_conns[hook_node_name]["main"][0].append(conn)
    print(f"  Hook wire: '{hook_node_name}' [output 0] → '{entry_name}'")

master["connections"] = master_conns


# ─────────────────────────────────────────────────────────────
# STEP 7 — PUT updated Master workflow
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 7 — PUT updated Master workflow")
print("=" * 60)

# Clean settings
raw_settings = master.get("settings", {})
clean_settings = {k: v for k, v in raw_settings.items() if k in SETTINGS_ALLOWED}

put_body = {
    "name":        master["name"],
    "nodes":       master["nodes"],
    "connections": master["connections"],
    "staticData":  master.get("staticData"),
    "pinData":     master.get("pinData", {}),
    "settings":    clean_settings,
}

try:
    result = req("PUT", f"/workflows/{MASTER}", put_body)
    print(f"  PUT succeeded. Master workflow updated: {result.get('name')}  (id={result.get('id')})")
    put_ok = True
except Exception as e:
    print(f"  PUT FAILED: {e}")
    put_ok = False


# ─────────────────────────────────────────────────────────────
# STEP 8 — Deactivate Databox Sync workflow
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 8 — Deactivating Databox Sync workflow")
print("=" * 60)

deactivate_ok = False

# Try dedicated deactivate endpoint first
try:
    r = req("POST", f"/workflows/{DATABOX}/deactivate")
    print(f"  Deactivated via POST /deactivate: active={r.get('active')}")
    deactivate_ok = True
except Exception as e:
    print(f"  POST /deactivate failed: {e}")

if not deactivate_ok:
    # Fallback: PUT with active=false
    try:
        db_put = req("GET", f"/workflows/{DATABOX}")
        db_settings = {k: v for k, v in db_put.get("settings", {}).items() if k in SETTINGS_ALLOWED}
        db_body = {
            "name":        db_put["name"],
            "nodes":       db_put["nodes"],
            "connections": db_put["connections"],
            "staticData":  db_put.get("staticData"),
            "pinData":     db_put.get("pinData", {}),
            "settings":    db_settings,
        }
        r2 = req("PUT", f"/workflows/{DATABOX}", db_body)
        # Then try PATCH active
        try:
            r3 = req("PATCH", f"/workflows/{DATABOX}", {"active": False})
            print(f"  Deactivated via PATCH: active={r3.get('active')}")
            deactivate_ok = True
        except Exception as e2:
            print(f"  PATCH active=false also failed: {e2}")
    except Exception as e:
        print(f"  Fallback PUT also failed: {e}")


# ─────────────────────────────────────────────────────────────
# STEP 9 — Summary
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 9 — Summary")
print("=" * 60)
print(f"  Master workflow ({MASTER}) updated: {'YES' if put_ok else 'NO'}")
print(f"  Nodes added to Master: {len(new_nodes)}")
for n in new_nodes:
    print(f"    - {n['name']}")
print(f"  Hook node used: '{hook_node_name}'")
print(f"  Entry nodes wired from hook: {entry_node_names}")
print(f"  Databox Sync ({DATABOX}) deactivated: {'YES' if deactivate_ok else 'NO (manual deactivation needed)'}")
print("\nDone.")
