"""Parse the v3 workflow JSON which has the actual filter logic.
Build a human-readable IF/THEN summary of what classifies each qoyod_source."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.load(open("_workflow_56383267.json", encoding="utf-8"))
print(f"Workflow: {d['name']}\n")

# v3 actions are nested
for i, a in enumerate(d.get("actions", [])):
    atype = a.get("type")
    aid = a.get("actionId")
    print(f"\n━━━ Action {aid}: {atype} ━━━")

    if atype == "BRANCH":
        # filters: list of OR groups, each containing AND filters
        for or_idx, or_group in enumerate(a.get("filters", [])):
            print(f"  OR group {or_idx}:")
            for f in or_group:
                prop = f.get("property")
                op = f.get("operator")
                val = f.get("value") or ""
                print(f"    AND {prop} {op} '{val}'")
        # Show branches
        accepts = a.get("acceptActions", [])
        rejects = a.get("rejectActions", [])
        print(f"  → if TRUE: actions {[x.get('actionId') for x in accepts]}")
        print(f"  → if FALSE: actions {[x.get('actionId') for x in rejects]}")

    elif atype == "SET_CONTACT_PROPERTY" or atype == "SET_PROPERTY":
        prop = a.get("propertyName")
        val = a.get("newValue")
        print(f"  SET {prop} = '{val}'")

    else:
        # Dump first 250 chars
        s = json.dumps(a, ensure_ascii=False, default=str)[:300]
        print(f"  RAW: {s}")
