"""
Role-based prompt router for Nexa — Qoyod Performance Agent.

Each role loads its own MD file + the shared manager OS, rather than
concatenating all MD files into one monolithic prompt.
"""
from pathlib import Path

MD_DIR = Path(__file__).parent.parent / "md_files"

# Shared context loaded for every role
SHARED = ["qoyod-manager-os.md", "qoyod-brand-identity.md"]

# Roles available to Nexa — modelled on the actual paid-media team seats.
# Each role is a teammate the agent stands in for. Display names render
# automatically from these keys (`media_buyer` -> "Media Buyer").
ROLE_FILES = {
    "media_buyer":           ["qoyod-paid-media-agent.md"],   # Hands-on optimizer: daily pauses, quick fixes, scale
    "paid_media_analyst":    ["qoyod-analyst-agent.md"],       # Trend analysis, anomaly attribution, week-over-week
    "paid_media_strategist": ["nexa-strategist.md"],           # Briefs, scale plans, channel mix, quarterly bets
    "marketing_assistant":   ["qoyod-task-flow.md"],           # PM/junior: turns decisions into Asana tasks, owns runbooks
    # Daily-report writer is invoked separately AFTER the team roles run, by
    # claude/reporter.py — not part of TRIGGER_ROUTES.
    "daily_report":          ["qoyod-daily-report.md"],
}

# Which roles Nexa invokes per trigger cadence
TRIGGER_ROUTES = {
    "daily":     ["media_buyer", "paid_media_analyst", "marketing_assistant"],
    "weekly":    ["media_buyer", "paid_media_analyst", "paid_media_strategist", "marketing_assistant"],
    "monthly":   ["paid_media_analyst", "paid_media_strategist", "marketing_assistant"],
    "quarterly": ["paid_media_analyst", "paid_media_strategist"],
    "on_demand": ["media_buyer", "paid_media_strategist", "marketing_assistant"],
}


def load_prompt(role: str) -> str:
    """Build the system prompt for one role: shared context + that role's MD file."""
    if role not in ROLE_FILES:
        raise ValueError(f"Unknown role: {role}")
    parts = []
    for fname in SHARED + ROLE_FILES[role]:
        p = MD_DIR / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def roles_for_trigger(trigger: str) -> list:
    return TRIGGER_ROUTES.get(trigger, [])
