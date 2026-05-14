"""Parse the v4 flow JSON and produce a human-readable summary of the
IF/THEN/SET-PROPERTY chain that classifies qoyod_source."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.load(open("_workflow_v4_3613421768.json", encoding="utf-8"))
print(f"Workflow: {d.get('name')}")
print(f"Enabled: {d.get('isEnabled')}")
print(f"Object type: {d.get('objectTypeId')}")
print(f"Action count: {len(d.get('actions', []))}\n")

# Build an action map by actionId
by_id = {a["actionId"]: a for a in d.get("actions", [])}

# Walk actions in id order
for aid in sorted(by_id.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
    a = by_id[aid]
    atype = a.get("type")
    ati = a.get("actionTypeId", "")
    fields = a.get("fields", {})

    if atype == "SINGLE_CONNECTION":
        # plain connector — skip
        continue

    if atype == "SET_PROPERTY" or "set-property" in str(ati).lower() or "0-2" in str(ati):
        prop = fields.get("property_name") or fields.get("propertyName") or fields.get("targetProperty")
        val = fields.get("property_value") or fields.get("value") or fields.get("propertyValue")
        next_a = a.get("connection", {}).get("nextActionId") if isinstance(a.get("connection"), dict) else None
        print(f"  [{aid:>4}] SET    {prop} = '{val}'  → next={next_a}")
    elif atype == "LIST_BRANCH" or "list-branch" in str(ati).lower() or atype == "BRANCH":
        branches = a.get("connections", a.get("listFilterBranches") or [])
        filters_summary = []
        # Get filter description if available
        for fb_idx, fb in enumerate(a.get("listFilterBranches", []) or []):
            label = fb.get("filterBranch", {}).get("filterBranches", [])
            # Just dump filter property names + operators
            def walk(node, acc):
                if not node: return
                for fn in node.get("filters", []) or []:
                    acc.append(f"{fn.get('property')}={fn.get('operator')}({fn.get('value')})")
                for sub in node.get("filterBranches", []) or []:
                    walk(sub, acc)
            acc = []
            walk(fb.get("filterBranch", {}), acc)
            filters_summary.append(f"branch{fb_idx}: " + " AND ".join(acc[:5]))
        print(f"  [{aid:>4}] BRANCH:")
        for fs in filters_summary[:10]:
            print(f"          {fs}")
    else:
        print(f"  [{aid:>4}] type={atype}  ati={ati}  keys={list(a.keys())[:6]}")
