"""
scripts/backfill_task_footer_v2.py
===================================
One-time backfill: add "Created by | Nexa Performance Agent" and
"Completed on | —" rows to all existing open Asana tasks that have the
old footer format but are missing these two new fields.

Run once, then delete or archive this script.
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asana
from asana.rest import ApiException
from config import (
    ASANA_TOKEN,
    ASANA_OPTIMIZATION_PROJECTS,
    ASANA_DAILY_PROJECTS,
    ASANA_SEASONAL_PROJECTS,
)

# ── All project IDs to scan ───────────────────────────────────────────────────
ALL_PROJECTS: dict[str, str] = {
    **{f"opt_{k}": v for k, v in ASANA_OPTIMIZATION_PROJECTS.items()},
    **{f"daily_{k}": v for k, v in ASANA_DAILY_PROJECTS.items()},
    **{f"seasonal_{k}": v for k, v in ASANA_SEASONAL_PROJECTS.items()},
}

FOOTER_MARKER = "📋 **Task Details**"

# Patterns to detect existing rows
_HAS_CREATED_BY  = re.compile(r"Created by", re.IGNORECASE)
_HAS_COMPLETED   = re.compile(r"Completed on", re.IGNORECASE)

# Row to insert after "Created on" line
CREATED_BY_ROW   = "| 🤖 Created by | Nexa Performance Agent |"
# Row to insert after "Due" line
COMPLETED_ON_ROW = "| ✅ Completed on | — |"


def _patch_notes(notes: str) -> tuple[str, bool]:
    """
    Return (patched_notes, changed).
    Inserts the two missing rows into the footer table if they're absent.
    """
    if FOOTER_MARKER not in notes:
        return notes, False

    need_created_by  = not _HAS_CREATED_BY.search(notes)
    need_completed   = not _HAS_COMPLETED.search(notes)

    if not need_created_by and not need_completed:
        return notes, False  # already up to date

    lines = notes.splitlines()
    new_lines = []
    for line in lines:
        new_lines.append(line)
        # Insert "Created by" immediately after any "Created on" / "Created" row
        if need_created_by and re.search(r"\|\s*📅\s*Created", line):
            new_lines.append(CREATED_BY_ROW)
            need_created_by = False
        # Insert "Completed on" immediately after any "Due" row
        if need_completed and re.search(r"\|\s*⏰\s*Due", line):
            new_lines.append(COMPLETED_ON_ROW)
            need_completed = False

    return "\n".join(new_lines), True


def run():
    configuration = asana.Configuration()
    configuration.access_token = ASANA_TOKEN
    client = asana.ApiClient(configuration)
    tasks_api = asana.TasksApi(client)

    updated = 0
    skipped = 0
    errors  = 0

    for label, project_id in ALL_PROJECTS.items():
        print(f"\n-- {label} ({project_id}) --")
        try:
            task_list = tasks_api.get_tasks_for_project(
                project_id,
                {"opt_fields": "gid,name,notes,completed", "limit": 100},
            )
        except ApiException as e:
            print(f"  [error] could not list tasks: {e.status}")
            errors += 1
            continue

        try:
            tasks = list(task_list)
        except ApiException as e:
            print(f"  [error] pagination failed ({e.status}) — project may not exist")
            errors += 1
            continue

        for task in tasks:
            if task.get("completed"):
                continue
            gid   = task["gid"]
            name  = task.get("name", "")[:60]
            notes = task.get("notes") or ""

            patched, changed = _patch_notes(notes)
            if not changed:
                skipped += 1
                continue

            try:
                tasks_api.update_task(
                    {"data": {"notes": patched}},
                    gid,
                    {},
                )
                safe = name.encode("ascii", "replace").decode("ascii")
                print(f"  OK {safe!r}")
                updated += 1
            except ApiException as e:
                safe = name.encode("ascii", "replace").decode("ascii")
                print(f"  ERR {safe!r}  error: {e}")
                errors += 1

    print(f"\n==================================")
    print(f"Updated : {updated}")
    print(f"Skipped : {skipped}  (already had both rows or no footer)")
    print(f"Errors  : {errors}")


if __name__ == "__main__":
    run()
