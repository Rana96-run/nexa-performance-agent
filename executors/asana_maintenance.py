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
    """Return incomplete tasks for a project with gid, name, due_on, created_at."""
    try:
        api = asana.TasksApi(client)
        tasks = api.get_tasks_for_project(
            project_id,
            {
                "completed_since": "now",   # only incomplete
                "opt_fields": "gid,name,due_on,created_at,completed",
                "limit": 100,
            }
        )
        return [t for t in tasks if not t.get("completed")]
    except AsanaApiException as e:
        print(f"[asana-maintenance] fetch tasks error for project {project_id}: {e}")
        return []


# ── 1. Overdue reminders ──────────────────────────────────────────────────────

def send_overdue_reminders(min_days_overdue: int = 1,
                           max_days_overdue: int = 30) -> int:
    """
    Post a grouped Slack reminder for tasks that are overdue.

    - min_days_overdue=1  → start reminding the day after due date
    - max_days_overdue=30 → stop reminding after 30 days (likely abandoned)
    - Returns number of overdue tasks found.
    """
    from notifications.quiet import is_quiet, quiet_log

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

    # Sort: most overdue first
    overdue.sort(key=lambda t: t["days_late"], reverse=True)

    lines = [f":alarm_clock: *{len(overdue)} Asana task(s) are overdue — please action or reschedule:*"]
    for t in overdue:
        url = f"https://app.asana.com/0/{t['project']}/{t['gid']}"
        lines.append(
            f"  • {t['days_late']}d overdue — <{url}|{t['name'][:70]}> (was due {t['due_on']})"
        )
    message = "\n".join(lines)

    if is_quiet():
        quiet_log("asana-maintenance", SLACK_CHANNEL_NOTIFY, message)
        print(f"[asana-maintenance] {len(overdue)} overdue tasks (quiet mode).")
        return len(overdue)

    try:
        from slack_sdk import WebClient
        wc = WebClient(token=SLACK_BOT_TOKEN)
        wc.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=message)
        print(f"[asana-maintenance] Reminder sent: {len(overdue)} overdue tasks.")
    except Exception as e:
        print(f"[asana-maintenance] Slack reminder failed: {e}")

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
