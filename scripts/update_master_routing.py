#!/usr/bin/env python3
"""
Updates the Master workflow (T8icImtZFLYeCa7e) to add:
  1. KPI Evaluator — reads Query KPIs output, runs waterfall, outputs one item per flag
  2. Route by Flag Type — Switch node (6 outputs: roas/cpql/cpl/qual/is/ctr)
  3. Execute Workflow nodes — one per sub-flow (A–F)
  4. Merge Sub-Flow Results — combines all Execute outputs
  5. Wires results into existing Wait — ai-orchestrator node

Reads sub-workflow IDs from scripts/_subflow_ids.json
"""
import json, urllib.request, urllib.error, sys, uuid, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

N8N_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIyYTZlMDMwNC0wN2RhLTRjNzktYTUwNi0zYzkyYjU5ODFiZDEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjA2Yjk1Y2YtNzJiOS00ZGM0LWIxOTAtNTY0Y2QyNzdhMDNiIiwiaWF0IjoxNzgxMTgxODU3fQ"
    ".UvVwQcF0-bW8ipJlgSTPEYe1Zg8tdJE3ZoJ-vJIFi8s"
)
BASE   = "https://qoyod.app.n8n.cloud"
MASTER = "T8icImtZFLYeCa7e"

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
def nid(n): return str(uuid.uuid5(_NS, "master_routing_"+n))

def req(method, path, body=None):
    url  = BASE + "/api/v1" + path
    data = json.dumps(body).encode() if body else None
    r    = urllib.request.Request(
        url, data=data,
        headers={"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"},
        method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8','replace')[:600]}")
        return None

# Load sub-workflow IDs
ids_path = os.path.join(os.path.dirname(__file__), "_subflow_ids.json")
with open(ids_path) as f:
    SF = json.load(f)

print(f"Sub-workflow IDs loaded: {SF}")

# Fetch Master
print(f"\nFetching Master workflow {MASTER}...")
wf = req("GET", f"/workflows/{MASTER}")
if not wf:
    sys.exit("Failed to fetch Master")

nodes = wf["nodes"]
conns = wf["connections"]
nmap  = {n["name"]: n for n in nodes}

print(f"  Master has {len(nodes)} nodes")

# Find anchor node position (Query KPIs)
qkpi = nmap.get("Query KPIs")
if not qkpi:
    sys.exit("Cannot find 'Query KPIs' node in Master")
ax, ay = qkpi["position"]
print(f"  'Query KPIs' at position [{ax}, {ay}]")

# Find Wait — ai-orchestrator
wait_orch = nmap.get("Wait — ai-orchestrator")
if not wait_orch:
    # Try alternate name
    for n in nodes:
        if "ai-orchestrator" in n["name"] and "Wait" in n["name"]:
            wait_orch = n
            break
if not wait_orch:
    print("  WARNING: Could not find 'Wait — ai-orchestrator' — will not auto-wire final merge")

# ── New nodes ─────────────────────────────────────────────────────────────────
# Place them to the right of Query KPIs, using y-offset for clarity

BASE_X = ax + 1200   # right of Query KPIs
BASE_Y = ay          # same y row as Query KPIs

KPI_EVAL_JS = r"""
const kpis = $('Query KPIs').all().map(i => i.json);
const flags = [];
const today = new Date().toISOString().slice(0, 10);

for (const row of kpis) {
  const { channel, roas, cpql, cpl, qual_pct, spend, leads } = row;
  if (!spend || spend < 5) continue; // skip channels with tiny spend

  // ROAS < 1x → 3-factor check (Sub-Flow A)
  if (roas !== null && roas < 1.0) {
    flags.push({ flag_type: 'roas', channel, roas, cpql: cpql||0,
                 qual_rate_pct: qual_pct||0, leads_total: leads||0,
                 prior_leads_total: leads||0, spend, date: today });
  }

  // CPQL > $60 (above scale target) → Sub-Flow C
  if (cpql !== null && cpql > 60 && (leads||0) >= 3) {
    flags.push({ flag_type: 'cpql', channel, cpql, cpl: cpl||0,
                 qual_rate_pct: qual_pct||0, leads, spend, date: today });
  }

  // CPL > $25 (above scale target) → Sub-Flow B
  if (cpl !== null && cpl > 25 && (leads||0) >= 3) {
    flags.push({ flag_type: 'cpl', channel, cpl, leads, spend, date: today });
  }

  // Qual rate < 45% → Sub-Flow D
  if (qual_pct !== null && qual_pct < 45 && (leads||0) >= 5) {
    flags.push({ flag_type: 'qual', channel, qual_rate_pct: qual_pct,
                 cpql: cpql||0, leads, spend, date: today });
  }
}

if (flags.length === 0) {
  return [{ json: { flag_type: 'green',
                    message: 'ALL SYSTEMS GREEN — no KPI flags today',
                    date: today } }];
}

console.log(`KPI Evaluator: ${flags.length} flag(s) found`);
return flags.map(f => ({ json: f }));
"""

new_nodes = [
    # 1. KPI Evaluator
    {
        "id": nid("kpi_eval"),
        "name": "KPI Evaluator",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [BASE_X, BASE_Y],
        "parameters": {"mode": "runOnceForAllItems", "jsCode": KPI_EVAL_JS}
    },
    # 2. Route by Flag Type (Switch)
    {
        "id": nid("switch"),
        "name": "Route by Flag Type",
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3,
        "position": [BASE_X + 400, BASE_Y],
        "parameters": {
            "mode": "rules",
            "rules": {"values": [
                {"conditions": {"conditions": [{"id": nid("r_roas"), "leftValue": "={{ $json.flag_type }}", "rightValue": "roas", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
                {"conditions": {"conditions": [{"id": nid("r_cpql"), "leftValue": "={{ $json.flag_type }}", "rightValue": "cpql", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
                {"conditions": {"conditions": [{"id": nid("r_cpl"),  "leftValue": "={{ $json.flag_type }}", "rightValue": "cpl",  "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
                {"conditions": {"conditions": [{"id": nid("r_qual"), "leftValue": "={{ $json.flag_type }}", "rightValue": "qual", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
                {"conditions": {"conditions": [{"id": nid("r_is"),   "leftValue": "={{ $json.flag_type }}", "rightValue": "is",   "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}},
                {"conditions": {"conditions": [{"id": nid("r_ctr"),  "leftValue": "={{ $json.flag_type }}", "rightValue": "ctr",  "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}}
            ]},
            "fallbackOutput": "extra",
            "options": {}
        }
    },
    # 3–8. Execute Workflow nodes (one per sub-flow)
    {
        "id": nid("exec_a"),
        "name": "Execute A — ROAS Check",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y - 600],
        "parameters": {
            "source": "database",
            "workflowId": SF["A"],
            "mode": "each",
            "options": {}
        }
    },
    {
        "id": nid("exec_c"),
        "name": "Execute C — CPQL Fix",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y - 400],
        "parameters": {
            "source": "database",
            "workflowId": SF["C"],
            "mode": "each",
            "options": {}
        }
    },
    {
        "id": nid("exec_b"),
        "name": "Execute B — CPL Fix",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y - 200],
        "parameters": {
            "source": "database",
            "workflowId": SF["B"],
            "mode": "each",
            "options": {}
        }
    },
    {
        "id": nid("exec_d"),
        "name": "Execute D — Qual Fix",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y],
        "parameters": {
            "source": "database",
            "workflowId": SF["D"],
            "mode": "each",
            "options": {}
        }
    },
    {
        "id": nid("exec_e"),
        "name": "Execute E — IS Fix",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y + 200],
        "parameters": {
            "source": "database",
            "workflowId": SF["E"],
            "mode": "each",
            "options": {}
        }
    },
    {
        "id": nid("exec_f"),
        "name": "Execute F — Creative Fix",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y + 400],
        "parameters": {
            "source": "database",
            "workflowId": SF["F"],
            "mode": "each",
            "options": {}
        }
    },
    # 9. All Systems Green passthrough
    {
        "id": nid("green"),
        "name": "All Systems Green",
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": [BASE_X + 800, BASE_Y + 600],
        "parameters": {}
    },
    # 10. Merge Sub-Flow Results
    {
        "id": nid("merge"),
        "name": "Merge Sub-Flow Results",
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3,
        "position": [BASE_X + 1300, BASE_Y],
        "parameters": {"mode": "append", "options": {}}
    },
    # Sticky note to document the new section
    {
        "id": nid("sticky"),
        "name": "KPI Decision Tree",
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [BASE_X - 50, BASE_Y - 700],
        "parameters": {
            "content": "## KPI Decision Tree\n\n**KPI Evaluator** reads yesterday's channel-level data\nand emits one flag per issue:\n\n- `roas` → Sub-Flow A (ROAS & Channel Health)\n- `cpql` → Sub-Flow C (CPQL Fix)\n- `cpl` → Sub-Flow B (CPL Fix)\n- `qual` → Sub-Flow D (Qual Ratio Fix)\n- `is` → Sub-Flow E (Impression Share Fix)\n- `ctr` → Sub-Flow F (Creative Fix)\n\nThresholds: ROAS<1x, CPQL>$60, CPL>$25, Qual<45%\nAll results → Merge → Wait — ai-orchestrator",
            "width": 340, "height": 320, "color": 3
        }
    }
]

# ── Check which new nodes already exist ──────────────────────────────────────
existing_names = {n["name"] for n in nodes}
added = []
for nn in new_nodes:
    if nn["name"] not in existing_names:
        nodes.append(nn)
        added.append(nn["name"])
        print(f"  + Adding node: {nn['name']}")
    else:
        print(f"  = Already exists: {nn['name']}")

# ── Wire new connections ─────────────────────────────────────────────────────
def add_conn(src, dst, si=0, di=0):
    conns.setdefault(src, {"main": []})
    while len(conns[src]["main"]) <= si:
        conns[src]["main"].append([])
    existing = [c["node"] for c in conns[src]["main"][si]]
    if dst not in existing:
        conns[src]["main"][si].append({"node": dst, "type": "main", "index": di})
        print(f"  + Wire: {src} [{si}] → {dst} [{di}]")

print("\nWiring connections...")

# Query KPIs → KPI Evaluator (additional target on same output)
add_conn("Query KPIs", "KPI Evaluator")

# KPI Evaluator → Switch
add_conn("KPI Evaluator", "Route by Flag Type")

# Switch outputs (0=roas, 1=cpql, 2=cpl, 3=qual, 4=is, 5=ctr, fallback=6)
add_conn("Route by Flag Type", "Execute A — ROAS Check",  si=0)
add_conn("Route by Flag Type", "Execute C — CPQL Fix",    si=1)
add_conn("Route by Flag Type", "Execute B — CPL Fix",     si=2)
add_conn("Route by Flag Type", "Execute D — Qual Fix",    si=3)
add_conn("Route by Flag Type", "Execute E — IS Fix",      si=4)
add_conn("Route by Flag Type", "Execute F — Creative Fix",si=5)
add_conn("Route by Flag Type", "All Systems Green",        si=6)

# All Execute nodes → Merge Sub-Flow Results (indexed inputs)
add_conn("Execute A — ROAS Check",   "Merge Sub-Flow Results", di=0)
add_conn("Execute C — CPQL Fix",     "Merge Sub-Flow Results", di=1)
add_conn("Execute B — CPL Fix",      "Merge Sub-Flow Results", di=2)
add_conn("Execute D — Qual Fix",     "Merge Sub-Flow Results", di=3)
add_conn("Execute E — IS Fix",       "Merge Sub-Flow Results", di=4)
add_conn("Execute F — Creative Fix", "Merge Sub-Flow Results", di=5)
add_conn("All Systems Green",        "Merge Sub-Flow Results", di=6)

# Merge Sub-Flow Results → Wait — ai-orchestrator (additional input)
if wait_orch:
    wait_name = wait_orch["name"]
    # Find the next available input index
    existing_inputs = conns.get(wait_name, {}).get("main", [[]])[0] if False else []
    # Count existing sources going INTO wait_orch
    in_count = sum(
        1 for src, src_conns in conns.items()
        for port in src_conns.get("main", [])
        for c in port
        if c["node"] == wait_name
    )
    add_conn("Merge Sub-Flow Results", wait_name, di=in_count)
    print(f"  Merge → {wait_name} at input index {in_count}")
else:
    print("  WARNING: Wait — ai-orchestrator not found, skipping final wire")

# ── Strip unsafe settings fields ─────────────────────────────────────────────
raw_settings = wf.get("settings", {})
safe_settings = {k: raw_settings[k] for k in [
    "executionOrder", "saveManualExecutions", "callerPolicy", "errorWorkflow",
    "saveDataErrorExecution", "saveDataSuccessExecution", "saveExecutionProgress",
    "executionTimeout", "timezone"
] if k in raw_settings}

# ── PUT updated workflow ──────────────────────────────────────────────────────
print(f"\nPutting updated Master workflow ({len(nodes)} nodes)...")
result = req("PUT", f"/workflows/{MASTER}", {
    "name": wf["name"],
    "nodes": nodes,
    "connections": conns,
    "settings": safe_settings
})

if result and "id" in result:
    print(f"  ✓ Master updated: {len(result['nodes'])} nodes, active={result.get('active')}")

    # Verify new nodes are present
    new_node_names = {nn["name"] for nn in new_nodes if not nn["name"].startswith("KPI")}
    found = [n["name"] for n in result["nodes"] if n["name"] in new_node_names or "Sub-Flow" in n.get("name","") or "KPI" in n.get("name","")]
    print(f"  New nodes in Master: {found}")
else:
    print("  ✗ Master PUT failed")
    sys.exit(1)

print("\n=== Master routing update complete ===")
print(f"KPI sub-flow routing is now wired into Master workflow {MASTER}")
print("Sub-workflows are inactive — activate manually in n8n UI after testing")
