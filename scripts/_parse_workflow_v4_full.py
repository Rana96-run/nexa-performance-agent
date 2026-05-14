"""Parse the v4 workflow's listBranches to extract all 14 channel-classification
rules in a human-readable form."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.load(open("_workflow_v4_3613421768.json", encoding="utf-8"))
actions = {a["actionId"]: a for a in d["actions"]}

# Action 1 is the LIST_BRANCH
a1 = actions["1"]

def fmt_filter(f):
    p = f.get("property")
    op = f.get("operation", {})
    operator = op.get("operator")
    vals = op.get("values") or []
    vs = ",".join(str(v) for v in vals)
    return f"{p} {operator}({vs})"

def walk_filter_branch(node, depth=2):
    indent = " " * depth
    lines = []
    op_label = node.get("filterBranchOperator", "AND")
    for f in node.get("filters", []) or []:
        lines.append(indent + f"{op_label} " + fmt_filter(f))
    for sub in node.get("filterBranches", []) or []:
        lines.extend(walk_filter_branch(sub, depth + 2))
    return lines

# Each listBranch in listBranches has a name + filterBranch + connection
for i, lb in enumerate(a1.get("listBranches", []), 1):
    branch_name = lb.get("branchName") or f"branch_{i}"
    fb = lb.get("filterBranch", {})
    # fb has filterBranches[] each with filters[]
    # Top-level grouping is OR (any one of the AND-blocks matches)
    or_groups = fb.get("filterBranches", []) or []
    print(f"\n━━━ Branch {i}: '{branch_name}' ━━━")
    if not or_groups:
        # Maybe filters directly on fb
        for f in fb.get("filters", []):
            print(f"    {fmt_filter(f)}")
    else:
        for j, andgrp in enumerate(or_groups):
            print(f"  OR{j}: ", end="")
            ands = [fmt_filter(f) for f in andgrp.get("filters", [])]
            print(" AND ".join(ands))
            # Recurse for nested sub-branches
            for sub in andgrp.get("filterBranches", []) or []:
                sub_ands = [fmt_filter(f) for f in sub.get("filters", [])]
                print(f"        nested " + (sub.get("filterBranchOperator", "AND")) + ": " + " AND ".join(sub_ands))
    # Where does this branch lead?
    conn = lb.get("connection", {})
    if conn:
        next_aid = conn.get("nextActionId")
        if next_aid and next_aid in actions:
            target = actions[next_aid]
            val = target.get("fields", {}).get("value", {})
            static_val = val.get("staticValue") if isinstance(val, dict) else val
            prop = target.get("fields", {}).get("property_name")
            print(f"  → SET {prop} = '{static_val}'")

# Default branch (fallback when no listBranch matches)
default = a1.get("defaultBranch")
if default:
    print(f"\n━━━ DEFAULT (no branch matched) ━━━")
    conn = default.get("connection", {})
    if conn:
        next_aid = conn.get("nextActionId")
        if next_aid and next_aid in actions:
            target = actions[next_aid]
            val = target.get("fields", {}).get("value", {})
            static_val = val.get("staticValue") if isinstance(val, dict) else val
            prop = target.get("fields", {}).get("property_name")
            print(f"  → SET {prop} = '{static_val}'")
