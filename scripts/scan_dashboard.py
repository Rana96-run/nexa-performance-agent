"""
Dashboard code scanner — standalone version of dashboard_guard.py checks.

Reads the live reports/app.py and reports/templates/activity.html,
runs the same 3 violation checks, and rewrites memory/dashboard_violations.jsonl
with the current state (preserves existing 'fixed' entries, replaces 'open').

Called by:
  - POST /api/ondemand/dashboard-scan  (from the dashboard "Run Scan" button)
  - Manually: railway run python scripts/scan_dashboard.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from datetime import datetime, timezone

BASE  = Path(__file__).resolve().parent.parent
QUEUE = BASE / "memory" / "dashboard_violations.jsonl"

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def run_checks() -> list[dict]:
    app_src  = _read(BASE / "reports" / "app.py")
    html_src = _read(BASE / "reports" / "templates" / "activity.html")
    ts       = datetime.now(timezone.utc).isoformat()
    found: list[dict] = []

    # ── Check 1: Role overlap in _TEAM_DEFS (growth-analyst) ─────────────────
    if "_TEAM_DEFS" in app_src:
        role_to_agents: dict[str, list[str]] = {}
        for block in re.split(r'(?=\{\s*["\']title["\'])', app_src):
            title_m = re.search(r'["\']title["\']\s*:\s*["\']([^"\']+)["\']', block)
            roles_m = re.search(r'["\']roles["\']\s*:\s*\{([^}]*)\}', block)
            if not (title_m and roles_m):
                continue
            title = title_m.group(1)
            for role in re.findall(r'["\']([a-z_]+)["\']', roles_m.group(1)):
                role_to_agents.setdefault(role, []).append(title)
        for role, agents in role_to_agents.items():
            if len(agents) > 1:
                found.append({
                    "id":          f"role_overlap__{role}",
                    "type":        "role_overlap",
                    "severity":    "block",
                    "agent":       "growth-analyst",
                    "description": (f'Role "{role}" claimed by {len(agents)} agents: '
                                    f'{", ".join(agents)}. Same log event counted multiple times.'),
                    "file":        "reports/app.py",
                    "fix_hint":    (f'Remove "{role}" from all but its rightful owner. '
                                    f'Remove from: {", ".join(agents[1:])}.'),
                    "ts":          ts,
                    "status":      "open",
                })

    # ── Check 2: Connector width mismatch (developer) ────────────────────────
    if "tc-bar" in html_src or "tc-stem" in html_src:
        has_hardcoded = bool(re.search(
            r'tc-bar[^>]*style="[^"]*width\s*:\s*min\(100%,\s*\d', html_src))
        has_grid = "grid-template-columns" in html_src
        if has_hardcoded and not has_grid:
            found.append({
                "id":          "connector_width_mismatch",
                "type":        "connector_width_mismatch",
                "severity":    "block",
                "agent":       "developer",
                "description": ("tc-bar uses a hardcoded width:min(100%,Npx) but dept columns "
                                 "use a different container width. Nodes won't align with headers."),
                "file":        "reports/templates/activity.html",
                "fix_hint":    ("Remove width override from tc-bar. Wrap stem-up cells + dept "
                                 "columns in display:grid;grid-template-columns:repeat(3,1fr)."),
                "ts":          ts,
                "status":      "open",
            })

    # ── Check 3: Dead CSS — .team-sub-card max-width (developer) ─────────────
    if "team-sub-card" in html_src:
        css_has_mw = bool(re.search(
            r'\.team-sub-card\s*\{[^}]*\bmax-width\s*:\s*\d+', html_src, re.DOTALL))
        if css_has_mw:
            style_end = html_src.find("</style>")
            html_part = html_src[style_end:] if style_end >= 0 else html_src
            total_uses    = len(re.findall(r'class="[^"]*team-sub-card', html_part))
            inline_ovr    = len(re.findall(
                r'class="[^"]*team-sub-card[^"]*"\s+style="[^"]*max-width', html_part))
            if total_uses > 0 and inline_ovr == total_uses:
                found.append({
                    "id":          "dead_css__team_sub_card_max_width",
                    "type":        "dead_css",
                    "severity":    "warn",
                    "agent":       "developer",
                    "description": (f".team-sub-card CSS sets max-width but all {total_uses} "
                                     f"HTML uses override it inline. CSS rule is never applied."),
                    "file":        "reports/templates/activity.html",
                    "fix_hint":    "Remove max-width from .team-sub-card CSS class.",
                    "ts":          ts,
                    "status":      "open",
                })

    return found

def write_queue(new_violations: list[dict]) -> None:
    """Preserve existing 'fixed' entries; replace all 'open' with fresh scan."""
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    existing_fixed: list[dict] = []
    if QUEUE.exists():
        for line in QUEUE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("status") == "fixed":
                    existing_fixed.append(obj)
            except Exception:
                pass

    with open(QUEUE, "w", encoding="utf-8") as fh:
        for entry in existing_fixed + new_violations:
            fh.write(json.dumps(entry) + "\n")

if __name__ == "__main__":
    violations = run_checks()
    write_queue(violations)
    open_v  = [v for v in violations if v["status"] == "open"]
    print(f"scan_dashboard: {len(open_v)} open violation(s) found", flush=True)
    for v in open_v:
        print(f"  [{v['severity']}] {v['id']} → {v['agent']}: {v['description'][:80]}", flush=True)
    sys.exit(0)
