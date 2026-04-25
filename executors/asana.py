"""
Asana task executor for Nexa — Qoyod Performance Agent.

Features:
- Deduplication: tasks are fingerprinted (title + project) before creation.
  If an identical task was already created today, the call is a no-op.
- Per-channel sections: tasks in the Optimization project are routed to
  the correct channel section (Google Ads / Meta / Snapchat / LinkedIn /
  Microsoft Ads / TikTok). Sections are auto-created if they don't exist.
"""
import asana
from config import ASANA_TOKEN, ASANA_PROJECTS, ASANA_CHANNEL_SECTIONS
from cache.cache_manager import task_is_new, record_task, get_task_gid

# Cache section GIDs so we only look them up once per session
_section_cache: dict[str, str] = {}   # "project_id:section_name" → section_gid


def get_client():
    configuration = asana.Configuration()
    configuration.access_token = ASANA_TOKEN
    return asana.ApiClient(configuration)


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _get_or_create_section(client, project_id: str, section_name: str) -> str | None:
    """Return the GID for a named section in a project, creating it if needed."""
    cache_key = f"{project_id}:{section_name}"
    if cache_key in _section_cache:
        return _section_cache[cache_key]

    sections_api = asana.SectionsApi(client)
    try:
        existing = sections_api.get_sections_for_project(project_id, {"opt_fields": "gid,name"})
        for sec in existing:
            if sec.get("name", "").strip().lower() == section_name.strip().lower():
                gid = sec["gid"]
                _section_cache[cache_key] = gid
                return gid

        # Section doesn't exist — create it
        result = sections_api.create_section_for_project(
            project_id,
            {"data": {"name": section_name}},
            {},
        )
        gid = result["gid"]
        _section_cache[cache_key] = gid
        print(f"[asana] created section '{section_name}' in project {project_id}")
        return gid

    except asana.ApiException as e:
        print(f"[asana] section error for '{section_name}': {e}")
        return None


def _channel_section_name(channel: str) -> str | None:
    """Map a channel key to its Asana section display name."""
    if not channel:
        return None
    key = channel.lower().replace(" ", "_").replace("-", "_")
    return ASANA_CHANNEL_SECTIONS.get(key)


# ---------------------------------------------------------------------------
# Main task creator
# ---------------------------------------------------------------------------

def create_task(
    title:       str,
    description: str,
    project_key: str,
    task_type:   str = "Recommendation",
    channel:     str = "",           # e.g. "google_ads", "meta", "snapchat"
) -> str | None:
    """
    Create an Asana task in the correct project and (for Optimization project)
    the correct per-channel section.

    project_key:  'daily_activity' | 'optimization' | 'campaigns_hub' | 'seasonal'
    channel:      optional — used to route to the right section in Optimization
    Returns the task GID (new or existing), or None on failure.
    """
    full_title = f"[{task_type}] {title}"

    # Deduplication guard
    if not task_is_new(full_title, project_key):
        existing = get_task_gid(full_title, project_key)
        print(f"[asana] skipped duplicate: {full_title[:60]!r} → gid={existing}")
        return existing

    project_id = ASANA_PROJECTS.get(project_key)
    if not project_id:
        print(f"[asana] unknown project key: {project_key!r}")
        return None

    client    = get_client()
    tasks_api = asana.TasksApi(client)

    # Build task body
    task_data: dict = {
        "name":     full_title,
        "notes":    description,
        "projects": [project_id],
    }

    # Add section routing for Optimization project (per-channel)
    if project_key == "optimization" and channel:
        section_name = _channel_section_name(channel)
        if section_name:
            section_gid = _get_or_create_section(client, project_id, section_name)
            if section_gid:
                task_data["memberships"] = [
                    {"project": project_id, "section": section_gid}
                ]

    try:
        task = tasks_api.create_task({"data": task_data}, {})
        gid  = task["gid"]
        record_task(full_title, project_key, gid)
        chan_note = f" [{channel}]" if channel else ""
        print(f"[asana] created{chan_note}: {full_title[:60]!r}  gid={gid}")
        return gid
    except asana.ApiException as e:
        print(f"[asana] error: {e}")
        return None


# ---------------------------------------------------------------------------
# Ensure all channel sections exist (call once at startup if needed)
# ---------------------------------------------------------------------------

def ensure_channel_sections():
    """
    Pre-create all channel sections in the Optimization project.
    Safe to call on every startup — skips sections that already exist.
    """
    project_id = ASANA_PROJECTS.get("optimization")
    if not project_id:
        return
    client = get_client()
    for key, name in ASANA_CHANNEL_SECTIONS.items():
        _get_or_create_section(client, project_id, name)
    print("[asana] channel sections verified/created in Optimization project")
