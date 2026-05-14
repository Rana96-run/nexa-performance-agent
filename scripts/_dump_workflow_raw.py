"""Dump the workflow actions in a readable form to understand the structure."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.load(open("_workflow_v4_3613421768.json", encoding="utf-8"))
print(f"Workflow: {d['name']}  enabled={d.get('isEnabled')}\n")

for i, a in enumerate(d.get("actions", [])):
    print(f"\n━━━ Action {i}: id={a.get('actionId')} ━━━")
    aid = a.get("actionId")
    atype = a.get("type")
    ati = a.get("actionTypeId", "")
    print(f"  type={atype}  actionTypeId={ati}")

    # If LIST_BRANCH, walk filter branches
    if atype == "LIST_BRANCH":
        print(f"  Branches:")
        for j, br in enumerate(a.get("listFilterBranches") or a.get("branches") or []):
            branch_name = br.get("branchName") or br.get("branch_name") or f"branch_{j}"
            print(f"    [{j}] '{branch_name}'")
            fb = br.get("filterBranch", {})
            def walk(node, indent=8, op="AND"):
                if not node:
                    return
                for f in node.get("filters", []) or []:
                    print(f"{' '*indent}{f.get('property')} {f.get('operator')} {f.get('value') or ''}")
                for sub in node.get("filterBranches", []) or []:
                    walk(sub, indent + 2, sub.get("filterBranchOperator", "AND"))
            walk(fb)
            next_aid = br.get("connection", {}).get("nextActionId") if br.get("connection") else None
            print(f"        → next action: {next_aid}")

    elif "SET_PROPERTY" in str(ati) or atype == "SET_PROPERTY":
        # Field schemas vary across action types
        fields = a.get("fields", {})
        print(f"  Fields: {json.dumps(fields, ensure_ascii=False)[:200]}")

    elif atype == "SINGLE_CONNECTION":
        conn = a.get("connection", {})
        print(f"  → next action: {conn.get('nextActionId') if conn else None}")

    else:
        # Dump all keys for unknown types
        print(f"  Keys: {list(a.keys())}")
        # Pretty-print first 300 chars
        s = json.dumps(a, default=str, ensure_ascii=False)
        print(f"  Raw (preview): {s[:300]}")
