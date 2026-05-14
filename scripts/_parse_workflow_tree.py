"""Walk the nested BRANCH/SET_PROPERTY action tree recursively."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.load(open("_workflow_56383267.json", encoding="utf-8"))
print(f"Workflow: {d['name']}  enabled={d.get('enabled')}\n")

def walk(actions, depth=0, label=""):
    indent = "  " * depth
    for a in actions:
        aid = a.get("actionId")
        atype = a.get("type")
        if atype == "BRANCH":
            print(f"{indent}├─ [{aid}] BRANCH {label}")
            # Summarize filters
            for or_idx, or_grp in enumerate(a.get("filters", [])):
                conds = []
                for f in or_grp:
                    p = f.get("property")
                    op = f.get("operator")
                    v = f.get("value") or ""
                    if v and len(v) > 30:
                        v = v[:30] + "..."
                    conds.append(f"{p} {op} '{v}'" if v else f"{p} {op}")
                print(f"{indent}│  OR{or_idx}: {' AND '.join(conds)}")
            print(f"{indent}│  IF TRUE  →")
            walk(a.get("acceptActions", []), depth + 1, "(then)")
            print(f"{indent}│  IF FALSE →")
            walk(a.get("rejectActions", []), depth + 1, "(else)")
        elif atype == "SET_CONTACT_PROPERTY":
            prop = a.get("propertyName")
            val = a.get("newValue")
            print(f"{indent}└─ [{aid}] SET {prop} = '{val}'  ✓")
        else:
            print(f"{indent}└─ [{aid}] {atype}")

walk(d.get("actions", []))
