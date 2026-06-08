"""
Dashboard code guard — the 'police' layer for reports/ changes.

Fires on Write/Edit to any file under reports/. Runs three checks,
classifies each violation by responsible agent, writes the violations to
memory/dashboard_violations.jsonl, and blocks the write on block-severity.

Agent routing:
  growth-analyst  →  role overlap / data attribution in _TEAM_DEFS
  developer       →  CSS/HTML structural issues in templates
  marketing-ops   →  (reserved — config-level policy issues)

After blocking: the orchestrator runs the 'dashboard-audit' workflow, which
dispatches the responsible agents to fix and report automatically.
"""
import sys, json, re, os
from pathlib import Path
from datetime import datetime, timezone

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name  = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {})

if tool_name not in ("Write", "Edit"):
    sys.exit(0)

file_path = (tool_input.get("file_path") or "").replace("\\", "/")

WATCH_PATHS = ["reports/app.py", "reports/templates/"]
if not any(w in file_path for w in WATCH_PATHS):
    sys.exit(0)

content = (
    tool_input.get("content") or
    tool_input.get("new_string") or
    ""
)
if not content:
    sys.exit(0)

violations = []

# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — Role overlap  (responsible: growth-analyst)
#
# Every role string in _TEAM_DEFS["roles"] must belong to exactly ONE agent.
# A shared role means the same agent_activity_log row is summed into multiple
# agent cards, inflating everyone's action counts.
# ─────────────────────────────────────────────────────────────────────────────
if "_TEAM_DEFS" in content:
    role_to_agents: dict[str, list[str]] = {}

    # Split on dict boundaries and extract title + roles from each block
    blocks = re.split(r'(?=\{\s*["\']title["\'])', content)
    for block in blocks:
        title_m = re.search(r'["\']title["\']\s*:\s*["\']([^"\']+)["\']', block)
        roles_m = re.search(r'["\']roles["\']\s*:\s*\{([^}]*)\}', block)
        if not (title_m and roles_m):
            continue
        title = title_m.group(1)
        for role in re.findall(r'["\']([a-z_]+)["\']', roles_m.group(1)):
            role_to_agents.setdefault(role, []).append(title)

    for role, agents in role_to_agents.items():
        if len(agents) > 1:
            violations.append({
                "id": f"role_overlap__{role}",
                "type": "role_overlap",
                "severity": "block",
                "agent": "growth-analyst",
                "description": (
                    f'Role "{role}" is claimed by {len(agents)} agents: '
                    f'{", ".join(agents)}. '
                    f'The same log event is counted multiple times.'
                ),
                "file": file_path,
                "fix_hint": (
                    f'Remove "{role}" from all but the one agent whose job '
                    f'description best matches it. '
                    f'Remove from: {", ".join(agents[1:])}.'
                ),
            })

# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — Connector width mismatch  (responsible: developer)
#
# The tc-bar and the dept-column container must share the same coordinate
# system. If tc-bar has a hardcoded min(100%,Npx) override but the dept
# columns below are width:100%, the connector nodes drift off-centre.
# ─────────────────────────────────────────────────────────────────────────────
if "tc-bar" in content or "tc-stem" in content:
    has_hardcoded_width = bool(
        re.search(r'tc-bar[^>]*style="[^"]*width\s*:\s*min\(100%,\s*\d', content)
    )
    has_grid_wrapper = "grid-template-columns" in content

    if has_hardcoded_width and not has_grid_wrapper:
        violations.append({
            "id": "connector_width_mismatch",
            "type": "connector_width_mismatch",
            "severity": "block",
            "agent": "developer",
            "description": (
                "tc-bar uses a hardcoded width:min(100%,Npx) but the dept-column "
                "container below uses a different width. Connector nodes will not "
                "align with dept column headers."
            ),
            "file": file_path,
            "fix_hint": (
                "Remove the width override from tc-bar (let CSS width:100% apply). "
                "Wrap both the stem-up cells AND the dept columns in a single "
                "display:grid;grid-template-columns:repeat(3,1fr) container — "
                "one coordinate system guarantees perfect alignment."
            ),
        })

# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — Dead CSS: .team-sub-card max-width  (responsible: developer)
#
# If the CSS class sets max-width but every single HTML use of that class
# carries an inline max-width override, the CSS rule is dead weight.
# ─────────────────────────────────────────────────────────────────────────────
if "team-sub-card" in content:
    css_has_max_width = bool(
        re.search(r'\.team-sub-card\s*\{[^}]*\bmax-width\s*:\s*\d+', content, re.DOTALL)
    )
    if css_has_max_width:
        style_end = content.find("</style>")
        html_part = content[style_end:] if style_end >= 0 else content
        total_uses   = len(re.findall(r'class="[^"]*team-sub-card', html_part))
        inline_overrides = len(re.findall(
            r'class="[^"]*team-sub-card[^"]*"\s+style="[^"]*max-width', html_part
        ))
        if total_uses > 0 and inline_overrides == total_uses:
            violations.append({
                "id": "dead_css__team_sub_card_max_width",
                "type": "dead_css",
                "severity": "warn",
                "agent": "developer",
                "description": (
                    f".team-sub-card CSS sets max-width but all {total_uses} "
                    f"HTML uses override it inline. The CSS rule is never applied."
                ),
                "file": file_path,
                "fix_hint": (
                    "Remove max-width from .team-sub-card in the <style> block. "
                    "The inline style is the single source of truth for card width."
                ),
            })

# ─────────────────────────────────────────────────────────────────────────────
# Write violations to the queue (always, even for warn-only)
# ─────────────────────────────────────────────────────────────────────────────
if violations:
    queue = (
        Path(__file__).resolve().parent.parent.parent
        / "memory" / "dashboard_violations.jsonl"
    )
    queue.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()
    with open(queue, "a", encoding="utf-8") as fh:
        for v in violations:
            fh.write(json.dumps({**v, "ts": ts, "status": "open"}) + "\n")

    block_vs = [v for v in violations if v["severity"] == "block"]
    warn_vs  = [v for v in violations if v["severity"] == "warn"]

    if block_vs:
        # Build agent routing summary
        by_agent: dict[str, list[str]] = {}
        for v in violations:
            by_agent.setdefault(v["agent"], []).append(v["id"])

        lines = [
            "🛑 DASHBOARD GUARD — WRITE BLOCKED",
            "",
            f"  {len(block_vs)} block-severity + {len(warn_vs)} warn-severity violation(s) detected.",
            "  Violations written to: memory/dashboard_violations.jsonl",
            "",
            "  Agent routing:",
        ]
        for agent_name, ids in by_agent.items():
            lines.append(f"    → {agent_name}: {', '.join(ids)}")
        lines += [
            "",
            "  To auto-fix + report, run the dashboard-audit workflow:",
            "    Workflow({ name: 'dashboard-audit' })",
            "",
            "  Violations:",
        ]
        for v in violations:
            icon = "❌" if v["severity"] == "block" else "⚠"
            lines.append(f"    {icon} [{v['type']}] → {v['agent']}")
            lines.append(f"       {v['description']}")
            lines.append(f"       Fix: {v['fix_hint']}")
            lines.append("")

        print("\n".join(lines), file=sys.stderr)
        sys.exit(2)  # block the write

    # Warn-only: allow but inject context
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"⚠ dashboard_guard: {len(warn_vs)} warn violation(s) found and "
                f"queued in memory/dashboard_violations.jsonl. "
                f"Run Workflow({{name:'dashboard-audit'}}) to auto-fix."
            ),
        }
    }))

sys.exit(0)
