"""Audit every branch from raw v4 JSON. For each branch:
- List exactly what filters exist (no parser interpretation)
- Flag form-submission / association / membership filters explicitly
- Compute presence of every click_id check
- Output a verified table per branch."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.load(open("_workflow_v4_3613421768.json", encoding="utf-8"))
a1 = d["actions"][0]

# Click IDs we care about
CLICK_IDS = [
    "hs_google_click_id",
    "hs_facebook_click_id",
    "msclkid",
    "hs_tiktok_click_id",
    "hs_linkedin_click_id",
    "campaign_id",        # from URL Suffix
    "ad_group_id",
    "ad_id",
]


def fmt_filter(f):
    """Format a single filter — handle both property and form-submission types."""
    ft = f.get("filterType")
    if ft == "PROPERTY":
        p = f.get("property")
        op = f.get("operation", {})
        operator = op.get("operator")
        vals = op.get("values") or []
        if vals:
            return f"{p} {operator}({','.join(map(str, vals))})"
        return f"{p} {operator}"
    elif "formId" in f:
        return f"FORM_SUBMISSION(formId={f.get('formId')[:8]}...)"
    else:
        return f"UNKNOWN_FILTER_TYPE: ft={ft}  keys={list(f.keys())[:5]}"


def walk(node, depth=2):
    """Recursive walk; returns flat list of filter strings."""
    out = []
    indent = " " * depth
    for f in node.get("filters", []) or []:
        out.append(indent + fmt_filter(f))
    for sub in node.get("filterBranches", []) or []:
        op_label = sub.get("filterBranchOperator", "AND")
        # Check if this is an ASSOCIATION (nested-object) filter
        if sub.get("filterBranchType") == "ASSOCIATION":
            obj_type = sub.get("objectTypeId", "?")
            label = f"[ASSOCIATION objType={obj_type}]"
        else:
            label = ""
        out.append(indent + f"-- {op_label} {label}")
        out.extend(walk(sub, depth + 2))
    return out


for i, lb in enumerate(a1.get("listBranches", []), 1):
    name = lb.get("branchName") or "?"
    print(f"\n{'='*72}\nBranch {i}: {name}\n{'='*72}")

    fb = lb.get("filterBranch", {})
    or_groups = fb.get("filterBranches", []) or []
    if not or_groups:
        # Filters might be directly on fb
        lines = walk(fb)
        for ln in lines:
            print(ln)
    else:
        for j, andgrp in enumerate(or_groups):
            print(f"\n  OR{j}:")
            lines = walk(andgrp)
            for ln in lines:
                print(f"  {ln}")

    # Check which click IDs are referenced ANYWHERE in this branch
    raw_str = json.dumps(lb, ensure_ascii=False)
    print(f"\n  Click-ID presence in this branch:")
    for cid in CLICK_IDS:
        present = f'"{cid}"' in raw_str
        mark = "✓" if present else "✗"
        print(f"    {mark} {cid}")
