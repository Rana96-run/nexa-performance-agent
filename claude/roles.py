"""
Role-based prompt router for the Qoyod Performance Agent.

Each role loads its own MD file + the shared manager OS, rather than
concatenating all MD files into one monolithic prompt.
"""
from pathlib import Path

MD_DIR = Path(__file__).parent.parent / "md_files"

# Shared context loaded for every role
SHARED = ["qoyod-manager-os.md", "qoyod-brand-identity.md"]

ROLE_FILES = {
    "paid_media":  ["qoyod-paid-media-agent.md"],
    "hubspot_cro": ["qoyod-hubspot-cro-agent.md"],
    "task_flow":   ["qoyod-task-flow.md"],
    "creative":    ["qoyod-creative-agent.md"],
    "reporter":    ["qoyod-reporter-agent.md"],
}

# Which roles the manager invokes per trigger cadence
TRIGGER_ROUTES = {
    "daily":     ["paid_media", "hubspot_cro", "task_flow"],
    "weekly":    ["reporter", "creative", "hubspot_cro"],
    "monthly":   ["reporter"],
    "quarterly": ["reporter"],
    "on_demand": ["paid_media", "creative"],
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
