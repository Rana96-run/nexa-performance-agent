"""Action Points tab — live Asana mirror.

Rebuilds the master sheet's '04 · Action Points — by Channel' tab from the
current Asana task state on each run. Groups OPEN + recently-completed tasks
by channel. Pulls real status (Asana custom 'Status' field) so editorial
nuance (Under Review / Blocked) survives — not just binary done/open.

Scheduler-callable via update_action_points(). Runs nightly.
"""
from __future__ import annotations
import os
import re
import requests
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import ASANA_TOKEN, ASANA_PROJECTS

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
TAB = "04 · Action Points — by Channel"

# Show open tasks + tasks completed within this many days (recent wins stay visible)
RECENT_DONE_DAYS = 7

# Channel detection from task name — order matters (most specific first)
CHANNEL_KEYWORDS = [
    ("GOOGLE ADS",        ["google_ads", "google ads", "pmax", "search_", "qawaem",
                            "zatca", "financialstatement", "fin statement", "finstatement"]),
    ("META",              ["meta", "facebook", " fb ", "instagram"]),
    ("SNAPCHAT",          ["snapchat", "snap "]),
    ("TIKTOK",            ["tiktok", "tik tok"]),
    ("MICROSOFT ADS (BING)", ["microsoft", "bing"]),
    ("LINKEDIN",          ["linkedin"]),
    ("ENGINEERING (CROSS-CHANNEL)", ["eng:", "schema", "collector", "dashboard",
                                     "pipeline", "bigquery", " bq ", "scheduler"]),
]

# Arabic Asana status labels → English for the sheet
STATUS_MAP = {
    "تحت المراجعة": "Under Review",
    "قيد التنفيذ":  "In Progress",
    "مكتمل":        "Done",
    "جديد":         "New",
    "محظور":        "Blocked",
}


def _detect_channel(name: str) -> str:
    n = f" {name.lower()} "
    for channel, kws in CHANNEL_KEYWORDS:
        if any(kw in n for kw in kws):
            return channel
    return "OTHER"


def _parse_type(name: str) -> str:
    """Extract Type from '[Type | Action]' or '[X | Type]' prefix."""
    m = re.match(r"\[([^\]]+)\]", name or "")
    if not m:
        return ""
    parts = [p.strip() for p in m.group(1).split("|")]
    # Convention: [task_type | action] — action is the verb we want as Type
    return parts[-1] if parts else ""


def _cf(custom_fields: list, field_name: str) -> str:
    for c in custom_fields or []:
        if c.get("name") == field_name:
            return c.get("display_value") or ""
    return ""


def _pull_tasks() -> list[dict]:
    """Pull OPEN + recently-completed tasks across all projects."""
    hdr = {"Authorization": f"Bearer {ASANA_TOKEN}"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DONE_DAYS)
    out = []
    for key, pid in ASANA_PROJECTS.items():
        after = None
        while True:
            params = {
                "opt_fields": "name,completed,completed_at,permalink_url,"
                              "custom_fields.name,custom_fields.display_value",
                "limit": 100,
            }
            if after:
                params["offset"] = after
            r = requests.get(f"https://app.asana.com/api/1.0/projects/{pid}/tasks",
                             headers=hdr, params=params, timeout=30)
            if r.status_code != 200:
                break
            body = r.json()
            for t in body.get("data", []):
                name = t.get("name", "")
                if not name or name.startswith("[Direct Log"):
                    continue   # skip system/log tasks
                completed = t.get("completed", False)
                # Keep open tasks, or completed within the recent window
                if completed:
                    ca = t.get("completed_at")
                    if not ca:
                        continue
                    try:
                        ca_dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                        if ca_dt < cutoff:
                            continue
                    except ValueError:
                        continue
                cf = t.get("custom_fields", [])
                raw_status = _cf(cf, "Status")
                status = "DONE" if completed else (STATUS_MAP.get(raw_status, raw_status) or "OPEN")
                out.append({
                    "channel":  _detect_channel(name),
                    "action":   re.sub(r"^\[[^\]]+\]\s*", "", name)[:120],  # strip prefix
                    "priority": _cf(cf, "Priority") or "—",
                    "type":     _parse_type(name) or "—",
                    "status":   status,
                    "url":      t.get("permalink_url", ""),
                })
            after = body.get("next_page", {}).get("offset") if body.get("next_page") else None
            if not after:
                break
    return out


def _dedupe(tasks: list[dict]) -> list[dict]:
    """Collapse recurring nightly tasks. Tasks like 'Meta — zero-conv pause (12)'
    fire daily with a changing (N) count — keep only ONE per distinct action,
    preferring OPEN over DONE and the shortest/cleanest name."""
    def _key(t):
        # Strip ANY trailing parenthetical — "(12)", "(10 campaigns)", "(3 ads)" —
        # so daily-fired variants of the same action collapse to one row.
        base = re.sub(r"\s*\([^)]*\)\s*$", "", t["action"]).strip().lower()
        # Also strip a leading "PENDING APPROVAL:" / "EXECUTED:" status prefix
        base = re.sub(r"^(pending approval|executed):\s*", "", base)
        return (t["channel"], base)
    seen = {}
    for t in tasks:
        k = _key(t)
        prev = seen.get(k)
        if prev is None:
            seen[k] = t
        else:
            # Prefer an OPEN/Under-Review task over a DONE one (still actionable)
            prev_done = prev["status"] == "DONE"
            cur_done = t["status"] == "DONE"
            if prev_done and not cur_done:
                seen[k] = t
    return list(seen.values())


def update_action_points() -> dict:
    """Rebuild the Action Points tab from live Asana. Scheduler entry point."""
    tasks = _dedupe(_pull_tasks())
    if not tasks:
        return {"written": 0, "detail": "no tasks pulled"}

    # Group by channel, in display order
    CHANNEL_ORDER = ["GOOGLE ADS", "META", "SNAPCHAT", "TIKTOK",
                     "MICROSOFT ADS (BING)", "LINKEDIN",
                     "ENGINEERING (CROSS-CHANNEL)", "OTHER"]
    by_channel = {}
    for t in tasks:
        by_channel.setdefault(t["channel"], []).append(t)

    # Build the sheet rows
    now_riyadh = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M")
    rows = [[f"Live Asana mirror — {len(tasks)} open + recently-done tasks. "
             f"Auto-synced {now_riyadh} Riyadh."]]
    for ch in CHANNEL_ORDER:
        items = by_channel.get(ch)
        if not items:
            continue
        # Open tasks first, then done; within each, High priority first
        prio_rank = {"High": 0, "Medium": 1, "Low": 2, "—": 3}
        items.sort(key=lambda x: (x["status"] == "DONE", prio_rank.get(x["priority"], 3)))
        rows.append([ch])
        rows.append(["Action", "Priority", "Type", "Status", "Asana URL"])
        for t in items:
            rows.append([t["action"], t["priority"], t["type"], t["status"], t["url"]])
        rows.append([])   # spacer

    # Write: clear the tab, then write fresh
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    svc = build("sheets", "v4", credentials=creds)
    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1:Z200").execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="RAW", body={"values": rows}).execute()
    return {"written": len(rows), "tasks": len(tasks),
            "channels": list(by_channel.keys()),
            "detail": f"rebuilt {len(tasks)} tasks across {len(by_channel)} channels"}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, ".")
    from dotenv import load_dotenv; load_dotenv()
    print(update_action_points())
