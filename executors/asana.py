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
from asana.rest import ApiException as AsanaApiException
from config import (
    ASANA_TOKEN, ASANA_PROJECTS, ASANA_ASSIGNEE_GID,
    ASANA_ASSIGNEE_GOOGLE_ADS_GID, ASANA_ASSIGNEE_DEFAULT_GID,
    ASANA_CHANNEL_LABELS, ASANA_ASSET_LEVEL_LABELS, ASANA_CHANNEL_ASSET_MATRIX,
    ASANA_OPTIMIZATION_PROJECTS, ASANA_DAILY_PROJECTS, ASANA_SEASONAL_PROJECTS,
    ASANA_ACTIVE_SEASONAL,
    asana_section_name,
)
from cache.cache_manager import task_is_new, record_task, get_task_gid


def _assignee_for_role(log_role: str, channel: str = "") -> str:
    """
    Route to the correct Asana assignee GID using the central AGENT_IDENTITY map.

    Priority:
      1. log_role match in AGENT_IDENTITY (e.g. "campaign_creator" → Campaign Manager)
      2. Channel override: google_ads always → Rana Khalid regardless of role
      3. Fall back to DEFAULT_GID

    Callers pass log_role from the function that's creating the task so the
    assignment reflects WHO did the work, not just which channel it touched.
    """
    from config import agent_identity, ASANA_ASSIGNEE_GOOGLE_ADS_GID
    ch = (channel or "").lower().replace(" ", "_").replace("-", "_")
    # Channel override: Google Ads is always Rana's domain
    if ch in ("google_ads", "google ads", "microsoft_ads", "bing_ads"):
        return ASANA_ASSIGNEE_GOOGLE_ADS_GID
    identity = agent_identity(log_role)
    return identity.get("asana_gid") or ASANA_ASSIGNEE_DEFAULT_GID or ASANA_ASSIGNEE_GID


def _assignee_name_for_role(log_role: str, channel: str = "") -> str:
    """Human-readable name of the assignee (shown in task footer)."""
    from config import agent_identity, ASANA_ASSIGNEE_GOOGLE_ADS_GID
    ch = (channel or "").lower().replace(" ", "_").replace("-", "_")
    if ch in ("google_ads", "google ads", "microsoft_ads", "bing_ads"):
        return "Rana Khalid"
    return agent_identity(log_role).get("display_name", "Donia Mohamed")


# Legacy wrappers — kept so old call-sites don't break while migrating
def _assignee_for_channel(channel: str) -> str:
    return _assignee_for_role("default", channel)

def _assignee_name_for_channel(channel: str) -> str:
    return _assignee_name_for_role("default", channel)

# Action -> priority label (shown in task footer)
_ACTION_PRIORITY = {
    "pause":    "High",
    "exclude":  "High",
    "optimize": "Medium",
    "scale":    "Medium",
    "launch":   "Medium",
    "fix":      "High",
    "refresh":  "Low",
}

# ── Custom field GIDs ─────────────────────────────────────────────────────────
# Estimated time — workspace-level number field (minutes).
# Confirmed present in: Google Ads, Meta, Snapchat optimization projects.
_CF_ESTIMATED_TIME = "1207977944194162"

# Status — workspace-level enum field (confirmed 2026-05-13).
# Set on every task so the Status column is populated on creation.
_CF_STATUS_GID    = "1208009827500816"
_CF_STATUS_TODO   = "1208009827500819"   # "To do"

# How long (minutes) each action type is estimated to take.
_ACTION_ESTIMATED_MINUTES: dict[str, int] = {
    "pause":    15,
    "scale":    20,
    "optimize": 30,
    "fix":      45,
    "launch":   30,
    "refresh":  20,
    "exclude":  10,
}

# Priority custom field — varies per project (different GIDs, different enum options).
# Confirmed via Asana API 2026-05-11.
# Format: project_id -> {field_gid, priority_label -> enum_option_gid}
_PROJECT_PRIORITY_CF: dict[str, dict] = {
    "1213239419217795": {   # Google Ads Optimization (Recovery)
        "field_gid": "1213239419217798",
        "Critical": "1213239419217800",
        "High":     "1213239419217799",
        "Medium":   "1213239419217801",
        "Low":      "1213239419217801",   # map Low → Medium
    },
    "1213294555250809": {   # Bing Ads Scaling
        "field_gid": "1213294555250812",
        "Critical": "1213294555250813",   # map Critical → High
        "High":     "1213294555250813",
        "Medium":   "1213294555250814",
        "Low":      "1213294555250814",   # map Low → Medium
    },
}

# Projects confirmed to have the Estimated time field (verified 2026-05-11).
_PROJECTS_WITH_ESTIMATED_TIME = {
    "1213239419217795",   # Google Ads Optimization
    "1213280413868927",   # Meta Ads (Recovery)
    "1214135546324721",   # Snapchat Ads Optimization
    "1214135614950965",   # TikTok Ads Optimization
}


def _task_footer(channel: str, asset_level: str, action: str, task_type: str,
                 log_role: str = "default") -> str:
    """Structured metadata block appended to every task description."""
    from datetime import datetime, timedelta, timezone
    from config import agent_identity
    riyadh      = timezone(timedelta(hours=3))
    now_str     = datetime.now(riyadh).strftime("%Y-%m-%d %H:%M Riyadh")
    due_str     = (datetime.now(riyadh) + timedelta(days=1)).strftime("%Y-%m-%d")
    priority    = _ACTION_PRIORITY.get((action or "").lower(), "Medium")
    ch_label    = ASANA_CHANNEL_LABELS.get(
                      (channel or "").lower().replace(" ", "_").replace("-", "_"),
                      channel or "—")
    lvl_label   = ASANA_ASSET_LEVEL_LABELS.get((asset_level or "").lower(), asset_level or "—")
    assignee    = _assignee_name_for_role(log_role, channel)
    created_by  = agent_identity(log_role).get("display_name", "Nexa Agent")
    return (
        f"\n\n---\n"
        f"**Task Details**\n\n"
        f"| Field | Value |\n"
        f"|---|---|\n"
        f"| Created on | {now_str} |\n"
        f"| Created by | {created_by} |\n"
        f"| Due | {due_str} |\n"
        f"| Completed on | — |\n"
        f"| Priority | {priority} |\n"
        f"| Type | {task_type} |\n"
        f"| Channel | {ch_label} |\n"
        f"| Asset level | {lvl_label} |\n"
        f"| Action | {(action or '—').title()} |\n"
        f"| Assignee | {assignee} |"
    )

# Cache section GIDs so we only look them up once per session
_section_cache: dict[str, str] = {}   # "project_id:section_name" -> section_gid

# Cache open tasks per project so we search Asana at most once per project per run
_open_tasks_cache: dict[str, list[dict]] = {}   # project_id -> [{gid, name, due_on}]


def _get_open_tasks(client, project_id: str) -> list[dict]:
    """Fetch all open tasks for a project (cached within the current process run)."""
    if project_id in _open_tasks_cache:
        return _open_tasks_cache[project_id]
    tasks_api = asana.TasksApi(client)
    results: list[dict] = []
    try:
        for task in tasks_api.get_tasks({
            "project": project_id,
            "limit": 100,
            "opt_fields": "gid,name,completed,due_on",
        }):
            if not task.get("completed"):
                results.append({
                    "gid":    task["gid"],
                    "name":   task.get("name") or "",
                    "due_on": task.get("due_on"),
                })
    except Exception as e:
        print(f"[asana] open-task fetch failed for project {project_id}: {e}")
    _open_tasks_cache[project_id] = results
    return results


def _find_open_task_by_campaign(client, project_id: str, campaign_name: str) -> tuple[str | None, str | None]:
    """
    Return (gid, due_on) of the first open task in project_id whose title
    contains campaign_name (case-insensitive). Returns (None, None) if not found.
    """
    if not campaign_name:
        return None, None
    needle = campaign_name.lower()
    for task in _get_open_tasks(client, project_id):
        if needle in task["name"].lower():
            return task["gid"], task["due_on"]
    return None, None


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

        # Section doesn't exist — create it.
        # Asana SDK v5 wraps the body in an opts dict under 'body' key.
        result = sections_api.create_section_for_project(
            project_id,
            {"body": {"data": {"name": section_name}}},
        )
        gid = result["gid"]
        _section_cache[cache_key] = gid
        print(f"[asana] created section '{section_name}' in project {project_id}")
        return gid

    except AsanaApiException as e:
        print(f"[asana] section error for '{section_name}': {e}")
        return None


def _channel_section_name(channel: str, asset_level: str = "") -> str | None:
    """Map (channel, asset_level) -> Asana section name like 'Google Ads — Campaign'."""
    if not channel:
        return None
    ch_key  = channel.lower().replace(" ", "_").replace("-", "_")
    lvl_key = (asset_level or "").lower()
    if ch_key not in ASANA_CHANNEL_LABELS:
        return None
    return asana_section_name(ch_key, lvl_key)


def _normalise_channel(channel: str) -> str:
    """Lowercase + underscore the channel slug so it matches our routing maps."""
    return (channel or "").lower().replace(" ", "_").replace("-", "_")


def _resolve_project_id(project_key: str, channel: str, task_type: str,
                        seasonal_hint: str = "") -> str | None:
    """
    Pick the correct Asana project ID based on category × channel × task type.

    project_key: 'daily_activity' | 'optimization' | 'seasonal' | 'campaigns_hub'
    channel:     normalised channel slug (e.g. 'google_ads', 'meta')
    task_type:   role-emitted task type (e.g. 'Direct Log', 'Recommendation', 'Tracking')
    seasonal_hint: optional explicit seasonal campaign key
    """
    ch = _normalise_channel(channel)

    # ── Optimization portfolio: route to the per-channel project ──────────────
    if project_key == "optimization":
        if ch in ASANA_OPTIMIZATION_PROJECTS:
            return ASANA_OPTIMIZATION_PROJECTS[ch]
        # No channel match -> fall back to the legacy single-project setting
        return ASANA_PROJECTS.get("optimization")

    # ── Daily Activity portfolio: route by task category ─────────────────────
    if project_key == "daily_activity":
        tt = (task_type or "").lower()
        # Heuristics on the task type / decision text emitted by the roles
        if any(k in tt for k in ("budget", "pacing", "spend alert", "overspend")):
            return ASANA_DAILY_PROJECTS["budget"]
        if any(k in tt for k in ("creative", "ad refresh", "fatigue", "qa")):
            return ASANA_DAILY_PROJECTS["creative"]
        if any(k in tt for k in ("keyword", "negative", "placement", "search term")):
            return ASANA_DAILY_PROJECTS["keyword"]
        if any(k in tt for k in ("tracking", "utm", "pixel", "capi", "attribution", "crm sync")):
            return ASANA_DAILY_PROJECTS["tracking"]
        if any(k in tt for k in ("competitor", "market", "benchmark")):
            return ASANA_DAILY_PROJECTS["competitor"]
        # Default = Daily Performance Review
        return ASANA_DAILY_PROJECTS["performance"]

    # ── Seasonal portfolio: route to the active seasonal campaign ─────────────
    if project_key == "seasonal":
        if seasonal_hint and seasonal_hint in ASANA_SEASONAL_PROJECTS:
            return ASANA_SEASONAL_PROJECTS[seasonal_hint]
        return ASANA_SEASONAL_PROJECTS.get(ASANA_ACTIVE_SEASONAL)

    # ── Campaigns Hub: legacy single-project ─────────────────────────────────
    return ASANA_PROJECTS.get(project_key)


# ---------------------------------------------------------------------------
# Main task creator
# ---------------------------------------------------------------------------

def create_task(
    title:         str,
    description:   str,
    project_key:   str,
    task_type:     str = "Recommendation",
    channel:       str = "",           # e.g. "google_ads", "meta", "snapchat"
    asset_level:   str = "",           # campaign | adset | ad | audience | tracking | keyword
    action:        str = "",           # pause | scale | refresh | launch | optimize | fix
    campaign_name: str = "",           # if set, used for cross-day dedup against live Asana
    log_role:      str = "default",    # agent log-role that is creating this task
                                       # used to set assignee + "Created by" footer field
) -> str | None:
    """
    Create an Asana task in the correct project and per-channel/per-asset-level section.

    project_key:   'daily_activity' | 'optimization' | 'campaigns_hub' | 'seasonal'
    channel:       used to route to "<Channel> — <AssetLevel>" section in Optimization
    asset_level:   campaign | adset | ad | audience | tracking | keyword
    action:        action verb prepended to the title (Pause / Scale / Refresh / Fix)
    campaign_name: when provided, the executor searches for any open (non-completed) task
                   in the target project whose title contains this string. If found and
                   the task is past-due, its due date is bumped to tomorrow. Either way
                   the existing GID is returned without creating a duplicate.
    log_role:      the agent's activity-log role (e.g. "performance_audit",
                   "keyword_management", "health_monitor"). Drives assignee selection
                   and the "Created by" field in the task footer. Defaults to "default"
                   for legacy callers that haven't been updated yet.

    Returns the task GID (new or existing), or None on failure.
    """
    # Auto-infer log_role from the calling module name when caller passes "default".
    # This means legacy callers in google_ads_audit_tasks.py / microsoft_ads_audit_tasks.py
    # /display_audit_tasks.py get the right agent identity without needing code changes.
    if log_role == "default":
        import traceback as _tb, sys as _sys
        for frame in _tb.extract_stack():
            mod = frame.filename.replace("\\", "/").split("/")[-1].replace(".py", "")
            if mod in ("google_ads_audit_tasks", "microsoft_ads_audit_tasks"):
                log_role = "keyword_management"    # Campaign Manager
                break
            if mod in ("display_audit_tasks", "creative_performance"):
                log_role = "performance_audit"     # Performance Lead
                break
            if mod in ("collector_failures", "connector_tracker", "daily_reconciliation"):
                log_role = "health_monitor"        # Project Coordinator
                break
            if mod in ("spike_detector", "period_compare", "forecaster"):
                log_role = "spike_detector"        # Growth Analyst
                break
            if mod == "operational_scheduler":
                log_role = "ops_scheduler"         # AI Orchestrator
                break
            if mod in ("cro_tasks", "cro_specialist", "lp_brief"):
                log_role = "cro_specialist"        # CRO Specialist → Rana
                break
            if mod in ("ui_ux_tasks", "design_handoff"):
                log_role = "ui_ux_design"          # UI/UX Designer → Rana
                break
            if mod in ("lp_deploy", "lp_developer", "developer_tasks"):
                log_role = "lp_developer"          # Developer → Tony Helmy + Rana follower
                break
            if mod in ("creative_brief", "creative_strategy_tasks"):
                log_role = "creative_strategy"     # Creative Strategist → Donia
                break

    # Title format: "[task_type | action] title"
    parts = [task_type]
    if action:
        parts.append(action.title())
    prefix = " | ".join(parts)
    full_title = f"[{prefix}] {title}"

    # Same-day deduplication guard (local ledger)
    if not task_is_new(full_title, project_key):
        existing = get_task_gid(full_title, project_key)
        print(f"[asana] skipped duplicate: {full_title[:60]!r} -> gid={existing}")
        return existing

    # Resolve to the right project based on category × channel × task type.
    project_id = _resolve_project_id(project_key, channel, task_type)
    if not project_id:
        print(f"[asana] could not resolve project for key={project_key!r} channel={channel!r}")
        return None

    from datetime import date as _date_cls, datetime, timedelta, timezone
    riyadh   = timezone(timedelta(hours=3))
    due_date = (datetime.now(riyadh) + timedelta(days=1)).strftime("%Y-%m-%d")

    client    = get_client()
    tasks_api = asana.TasksApi(client)

    # Cross-day dedup: search live Asana for any open task containing campaign_name.
    # This handles campaigns that stay unresolved across multiple nightly runs.
    if campaign_name:
        existing_gid, existing_due = _find_open_task_by_campaign(client, project_id, campaign_name)
        if existing_gid:
            today_iso = _date_cls.today().isoformat()
            if existing_due and existing_due < today_iso:
                try:
                    tasks_api.update_task({"data": {"due_on": due_date}}, existing_gid, {})
                    print(f"[asana] bumped due date gid={existing_gid}: {existing_due} -> {due_date}")
                    _open_tasks_cache.pop(project_id, None)
                except AsanaApiException as e:
                    print(f"[asana] due-date update failed: {e}")
            else:
                print(f"[asana] skipped (open task exists, due={existing_due}): gid={existing_gid}")
            return existing_gid

    # Append structured metadata footer to every description
    full_description = description + _task_footer(
        channel, asset_level, action, task_type, log_role=log_role
    )

    # Build task body
    task_data: dict = {
        "name":     full_title,
        "notes":    full_description,
        "projects": [project_id],
        "due_on":   due_date,
    }
    assignee_gid = _assignee_for_role(log_role, channel)
    if assignee_gid:
        task_data["assignee"] = assignee_gid

    # Build follower set:
    #   - Always: Rana + Donia (cross-visibility on all tasks)
    #   - Additionally: co_assignee_gid from AGENT_IDENTITY (e.g. Rana on Developer tasks)
    from config import agent_identity as _agent_identity
    co_gid = _agent_identity(log_role).get("co_assignee_gid", "")
    follower_gids = list(
        {ASANA_ASSIGNEE_GOOGLE_ADS_GID, ASANA_ASSIGNEE_DEFAULT_GID, co_gid}
        - {assignee_gid or "", ""}
    )
    if follower_gids:
        task_data["followers"] = follower_gids

    # Populate custom fields for the target project.
    # Only set fields confirmed present — avoids 400 errors from missing fields.
    cf: dict = {}
    act_lower = (action or "").lower()

    # Status — workspace-level field; set "To do" on every new task.
    cf[_CF_STATUS_GID] = _CF_STATUS_TODO

    # Estimated time — only for projects confirmed to have this field
    if project_id in _PROJECTS_WITH_ESTIMATED_TIME:
        est = _ACTION_ESTIMATED_MINUTES.get(act_lower)
        if est is not None:
            cf[_CF_ESTIMATED_TIME] = est

    # Priority — per-project enum field
    if project_id in _PROJECT_PRIORITY_CF:
        priority = _ACTION_PRIORITY.get(act_lower, "Medium")
        pmap = _PROJECT_PRIORITY_CF[project_id]
        enum_gid = pmap.get(priority) or pmap.get("Medium")
        if enum_gid:
            cf[pmap["field_gid"]] = enum_gid

    task_data["custom_fields"] = cf

    # Section routing — for Optimization projects, route into the
    # asset-level section (e.g. "Campaign", "Ad Set / Group", "Audience").
    if project_key == "optimization" and asset_level:
        section_label = ASANA_ASSET_LEVEL_LABELS.get(asset_level)
        if section_label:
            section_gid = _get_or_create_section(client, project_id, section_label)
            if section_gid:
                task_data["memberships"] = [
                    {"project": project_id, "section": section_gid}
                ]

    # QA gate — hard-block if footer is malformed or numeric claims orphan.
    # Auto-retries once on transient BQ staleness, then raises QAGateError.
    try:
        from qa.gate import gate, QAGateError
        try:
            gate.verify_asana(task_data)
        except QAGateError as e:
            print(f"[asana] QA gate BLOCKED task creation: {e}")
            return None
    except ImportError:
        pass  # qa module not present — degrade gracefully

    try:
        task = tasks_api.create_task({"data": task_data}, {})
        gid  = task["gid"]
        record_task(full_title, project_key, gid)
        bits = [b for b in (channel, asset_level, action) if b]
        chan_note = f" [{' / '.join(bits)}]" if bits else ""
        print(f"[asana] created{chan_note}: {full_title[:60]!r}  gid={gid}")
        try:
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="task_creator", action="asana_task_created",
                channel=channel or None, rows_affected=1,
                details={"project_key": project_key, "task_action": action,
                         "asset_level": asset_level, "gid": gid,
                         "title": full_title[:120]},
            )
        except Exception:
            pass
        return gid
    except AsanaApiException as e:
        print(f"[asana] error: {e}")
        return None


# ---------------------------------------------------------------------------
# Ensure all channel sections exist (call once at startup if needed)
# ---------------------------------------------------------------------------

def ensure_channel_sections():
    """
    For each per-channel Optimization project (Google Ads, Meta, Snap, TikTok,
    LinkedIn, YouTube, Microsoft), make sure the asset-level sections exist:
        Campaign / Ad Set / Group / Ad / Audience / Tracking / Keyword
    Sections are added IN ADDITION to whatever sections already exist
    (we never delete or rename existing sections).
    """
    client = get_client()
    created = 0
    for ch_key, project_id in ASANA_OPTIMIZATION_PROJECTS.items():
        levels = ASANA_CHANNEL_ASSET_MATRIX.get(ch_key, [])
        for lvl in levels:
            label = ASANA_ASSET_LEVEL_LABELS.get(lvl)
            if not label:
                continue
            _get_or_create_section(client, project_id, label)
            created += 1
    print(f"[asana] verified/created {created} asset-level sections across {len(ASANA_OPTIMIZATION_PROJECTS)} optimization projects")
    _ensure_status_field_on_projects(client)


def _ensure_status_field_on_projects(client):
    """Attach the workspace Status field to all perf-marketing projects so it
    shows as a column.  Safe to call multiple times — Asana ignores duplicates."""
    from config import ASANA_DAILY_PROJECTS
    all_pids = list(ASANA_OPTIMIZATION_PROJECTS.values()) + list(ASANA_DAILY_PROJECTS.values())
    proj_api = asana.ProjectsApi(client)
    added = 0
    for pid in all_pids:
        if not pid:
            continue
        try:
            proj_api.add_custom_field_setting_for_project(
                {"data": {"custom_field": _CF_STATUS_GID}},
                pid,
                {},
            )
            added += 1
        except AsanaApiException as e:
            if "already" in str(e).lower() or "duplicate" in str(e).lower() or "400" in str(e):
                pass  # field already attached — expected on subsequent calls
            else:
                print(f"[asana] warn: could not attach Status field to {pid}: {e}")
    if added:
        print(f"[asana] attached Status field to {added} project(s)")
