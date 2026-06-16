"""
executors/asana_maintenance.py
================================
Two housekeeping jobs that run as part of the daily operational cycle:

1. send_overdue_reminders()
   - Finds incomplete Asana tasks whose due_on is in the past
   - Posts a Slack reminder to SLACK_CHANNEL_NOTIFY once per task
     (uses cache to avoid spamming the same task twice)
   - Groups by project, sorts by days overdue

2. refresh_stale_due_dates()
   - Finds incomplete tasks whose due_on is still today or yesterday
     (i.e. tasks the agent created but nobody acted on in 24h)
   - Rolls the due date forward to tomorrow so they stay visible
     in Asana "Due Today/Tomorrow" views and don't go stale
   - Only rolls tasks created by this agent (title prefix filter)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import asana
from asana.rest import ApiException as AsanaApiException
from dotenv import load_dotenv

load_dotenv(override=True)

from config import (
    ASANA_TOKEN,
    ASANA_OPTIMIZATION_PROJECTS,
    ASANA_DAILY_PROJECTS,
    SLACK_BOT_TOKEN,
    SLACK_CHANNEL_NOTIFY,
)

_RIYADH = timezone(timedelta(hours=3))
_TODAY  = datetime.now(_RIYADH).date()


def _get_client() -> asana.ApiClient:
    cfg = asana.Configuration()
    cfg.access_token = ASANA_TOKEN
    return asana.ApiClient(cfg)


def _all_project_ids() -> list[str]:
    """Return every project GID we manage."""
    ids = []
    for v in ASANA_OPTIMIZATION_PROJECTS.values():
        if v: ids.append(v)
    for v in ASANA_DAILY_PROJECTS.values():
        if v: ids.append(v)
    return list(set(ids))


def _fetch_incomplete_tasks(client: asana.ApiClient, project_id: str) -> list[dict]:
    """Return incomplete tasks for a project."""
    try:
        api = asana.TasksApi(client)
        tasks = api.get_tasks_for_project(
            project_id,
            {
                "completed_since": "now",
                "opt_fields": "gid,name,due_on,created_at,completed",
                "limit": 100,
            }
        )
        return [t for t in tasks if not t.get("completed")]
    except AsanaApiException as e:
        print(f"[asana-maintenance] fetch tasks error for project {project_id}: {e}")
        return []


def _fetch_all_tasks(client: asana.ApiClient, project_id: str,
                     since_days: int = 7) -> list[dict]:
    """Return both complete and incomplete tasks created within the last N days."""
    try:
        api  = asana.TasksApi(client)
        since_dt = (datetime.now(_RIYADH) - timedelta(days=since_days)).strftime(
            "%Y-%m-%dT00:00:00.000Z"
        )
        tasks = api.get_tasks_for_project(
            project_id,
            {
                "completed_since": since_dt,
                "opt_fields": "gid,name,due_on,created_at,completed,completed_at",
                "limit": 100,
            }
        )
        return list(tasks)
    except AsanaApiException as e:
        print(f"[asana-maintenance] fetch all tasks error for project {project_id}: {e}")
        return []


# ── Category classifier ───────────────────────────────────────────────────────

# Maps keyword patterns (lowercase) → category label
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("scale",              "Scale"),
    ("scaled",             "Scale"),
    ("pause",              "Pause"),
    ("paused",             "Pause"),
    ("drill-down",         "Drill-down"),
    ("drilldown",          "Drill-down"),
    ("keyword",            "Drill-down"),
    ("ad/keyword",         "Drill-down"),
    ("impression share",   "Awareness"),
    ("impressionshare",    "Awareness"),
    ("websitetraffic",     "Awareness"),
    ("website traffic",    "Awareness"),
    ("awareness",          "Awareness"),
    ("traffic",            "Awareness"),
    ("junk-leads",         "Junk Leads"),
    ("junk leads",         "Junk Leads"),
    ("optimize",           "Optimize"),
    ("cpql investigation", "Optimize"),
    ("investigation",      "Optimize"),
]

_CATEGORY_ORDER = ["Scale", "Pause", "Drill-down", "Optimize", "Junk Leads", "Awareness"]
_CATEGORY_ICON  = {
    "Scale":      ":large_green_circle:",
    "Pause":      ":red_circle:",
    "Drill-down": ":large_orange_circle:",
    "Optimize":   ":large_blue_circle:",
    "Junk Leads": ":large_yellow_circle:",
    "Awareness":  ":white_circle:",
}


def _classify_task(name: str) -> str:
    """Return the category label for a task based on its title."""
    lower = name.lower()
    for pattern, label in _CATEGORY_PATTERNS:
        if pattern in lower:
            return label
    return "Other"


def get_task_category_summary(since_days: int = 7) -> dict[str, dict[str, int]]:
    """
    Query all optimization + daily projects for tasks created in the last
    `since_days` days. Return a dict:
        { category: { "done": int, "pending": int } }

    Only includes categories that have at least one task.
    """
    client   = _get_client()
    summary: dict[str, dict[str, int]] = {}

    for project_id in _all_project_ids():
        for task in _fetch_all_tasks(client, project_id, since_days=since_days):
            cat      = _classify_task(task.get("name", ""))
            done     = bool(task.get("completed"))
            entry    = summary.setdefault(cat, {"done": 0, "pending": 0})
            if done:
                entry["done"]    += 1
            else:
                entry["pending"] += 1

    return summary


# ── 1. Overdue reminders ──────────────────────────────────────────────────────

def send_overdue_reminders(min_days_overdue: int = 1,
                           max_days_overdue: int = 30) -> int:
    """
    Post a grouped Slack reminder for tasks that are overdue.

    - min_days_overdue=1  → start reminding the day after due date
    - max_days_overdue=30 → stop reminding after 30 days (likely abandoned)
    - Returns number of overdue tasks found.
    """
    client   = _get_client()
    overdue: list[dict] = []

    for project_id in _all_project_ids():
        for task in _fetch_incomplete_tasks(client, project_id):
            due_on = task.get("due_on")
            if not due_on:
                continue
            try:
                due_date = datetime.strptime(due_on, "%Y-%m-%d").date()
            except ValueError:
                continue
            days_late = (_TODAY - due_date).days
            if min_days_overdue <= days_late <= max_days_overdue:
                overdue.append({
                    "gid":       task["gid"],
                    "name":      task["name"],
                    "due_on":    due_on,
                    "days_late": days_late,
                    "project":   project_id,
                })

    if not overdue:
        print("[asana-maintenance] No overdue tasks.")
        return 0

    # Sort: most overdue first, then group by category
    overdue.sort(key=lambda t: t["days_late"], reverse=True)

    # Group by category for the Slack message
    by_cat: dict[str, list[dict]] = {}
    for t in overdue:
        cat = _classify_task(t["name"])
        by_cat.setdefault(cat, []).append(t)

    # Log overdue tasks to console only — do NOT post to Slack.
    # Overdue task counts surface in the main #notify daily summary (Asana line).
    # Individual task links stay inside Asana; Slack stays clean (2 messages/night).
    for cat in _CATEGORY_ORDER + [c for c in by_cat if c not in _CATEGORY_ORDER]:
        tasks = by_cat.get(cat)
        if not tasks:
            continue
        print(f"[asana-maintenance] overdue: {cat} × {len(tasks)}")
        for t in tasks:
            print(f"  {t['days_late']}d  {t['name'][:80]}")

    print(f"[asana-maintenance] {len(overdue)} overdue task(s) — logged only, no Slack post.")
    return len(overdue)


# ── 2. Roll forward stale due dates ──────────────────────────────────────────

def refresh_stale_due_dates(max_roll_days: int = 7) -> int:
    """
    Roll the due date forward to tomorrow for tasks that are still incomplete
    and whose due date has already passed (up to max_roll_days ago).

    This keeps "Due Today/Tomorrow" views in Asana clean and ensures tasks
    that nobody acted on in 24h don't silently disappear into the past.

    - max_roll_days=7: don't roll tasks older than 7 days (likely abandoned;
      those are handled by send_overdue_reminders instead).
    - Returns number of tasks updated.
    """
    client      = _get_client()
    tasks_api   = asana.TasksApi(client)
    tomorrow    = (_TODAY + timedelta(days=1)).isoformat()
    updated     = 0

    for project_id in _all_project_ids():
        for task in _fetch_incomplete_tasks(client, project_id):
            due_on = task.get("due_on")
            if not due_on:
                continue
            try:
                due_date = datetime.strptime(due_on, "%Y-%m-%d").date()
            except ValueError:
                continue

            days_late = (_TODAY - due_date).days
            # Roll forward only tasks 1–max_roll_days days past their due date
            if 1 <= days_late <= max_roll_days:
                try:
                    tasks_api.update_task(
                        task["gid"],
                        {"data": {"due_on": tomorrow}},
                        {}
                    )
                    print(f"[asana-maintenance] Rolled due date: {task['name'][:60]!r}  "
                          f"{due_on} -> {tomorrow}")
                    updated += 1
                except AsanaApiException as e:
                    print(f"[asana-maintenance] update failed for {task['gid']}: {e}")

    print(f"[asana-maintenance] {updated} task due dates rolled to {tomorrow}.")
    return updated


# ── Combined daily run ────────────────────────────────────────────────────────

def run_daily_maintenance():
    """
    Called once per day from the operational scheduler.
    Order:
      1. Roll stale due dates (1–7d overdue) → keeps tasks visible in Asana
      2. Send Slack reminders (1–30d overdue) → alerts team to outstanding work
    """
    print("[asana-maintenance] Starting daily maintenance...")
    rolled   = refresh_stale_due_dates(max_roll_days=7)
    reminded = send_overdue_reminders(min_days_overdue=1, max_days_overdue=30)
    print(f"[asana-maintenance] Done. Rolled={rolled}, Reminded={reminded}")
    return {"rolled": rolled, "reminded": reminded}


if __name__ == "__main__":
    run_daily_maintenance()
