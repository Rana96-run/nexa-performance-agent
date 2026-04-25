"""
collectors/zapier.py
====================
Monitors the Qoyod Zapier account for:
  - Errored zap runs (fires Slack alert + Asana task)
  - On-hold / held tasks (fires Slack alert)
  - Paused/disabled zaps that should be running (daily summary)
  - Auto-resumes held tasks where safe (configurable)

Two modes
---------
1. Polling  — called by the reporting scheduler or daily agent cadence.
              Scans the last N hours of zap run history.

2. Webhook  — /webhooks/zapier receives real-time error payloads sent by
              a "Catch Hook" Zap you set up in Zapier to monitor other Zaps.
              See docs/zapier-monitoring-setup.md for the Zap recipe.

Zapier API
----------
Base URL : https://api.zapier.com/v1
Auth     : Bearer <ZAPIER_API_TOKEN>  (Settings → API → create token)
Key endpoints:
  GET  /zaps                  list all zaps (name, is_enabled, status)
  GET  /zap-runs              run history (status: success|error|held|filtered)
  POST /zap-runs/{id}/replay  replay a single failed run

Rate limit: ~100 req/min.  We stay well under with incremental polling.

.env variable required:
  ZAPIER_API_TOKEN=<your token>
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY

# ─── Config ───────────────────────────────────────────────────────────────────
_TOKEN   = os.getenv("ZAPIER_API_TOKEN", "")
_BASE    = "https://api.zapier.com/v1"
_SLACK   = WebClient(token=SLACK_BOT_TOKEN)

# Auto-resume held tasks? Set False if you want human approval first.
AUTO_RESUME_HELD = os.getenv("ZAPIER_AUTO_RESUME", "false").lower() == "true"

# Zap run statuses we care about
Status = Literal["success", "error", "held", "filtered", "throttled"]
_ALERT_STATUSES = {"error", "held", "throttled"}


# ─── API helpers ──────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}", "Accept": "application/json"}


def _get(path: str, params: dict | None = None) -> dict | list | None:
    if not _TOKEN:
        print("[zapier] ZAPIER_API_TOKEN not set — skipping")
        return None
    try:
        r = requests.get(
            f"{_BASE}{path}",
            headers=_headers(),
            params=params or {},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        print(f"[zapier] API error {e.response.status_code} on {path}: {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"[zapier] Request failed {path}: {e}")
        return None


def _post(path: str, payload: dict | None = None) -> dict | None:
    if not _TOKEN:
        return None
    try:
        r = requests.post(
            f"{_BASE}{path}",
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload or {},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[zapier] POST failed {path}: {e}")
        return None


# ─── Data fetchers ────────────────────────────────────────────────────────────

def get_all_zaps() -> list[dict]:
    """Return all zaps with id, name, is_enabled, last_run_at."""
    data = _get("/zaps")
    if data is None:
        return []
    # API returns {"objects": [...]} or a list directly
    zaps = data.get("objects", data) if isinstance(data, dict) else data
    return [
        {
            "id":          str(z.get("id", "")),
            "name":        z.get("title") or z.get("name") or f"Zap {z.get('id')}",
            "is_enabled":  z.get("is_enabled", False),
            "state":       z.get("state", "unknown"),
            "url":         z.get("url") or f"https://zapier.com/editor/{z.get('id')}",
        }
        for z in (zaps if isinstance(zaps, list) else [])
    ]


def get_zap_runs(since_hours: int = 24, status: str | None = None) -> list[dict]:
    """
    Return zap runs from the last N hours.
    Optionally filter by status: 'error' | 'held' | 'success' | 'filtered'.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    params: dict = {
        "created_at__gte": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 200,
    }
    if status:
        params["status"] = status

    data = _get("/zap-runs", params)
    if data is None:
        return []
    runs = data.get("objects", data) if isinstance(data, dict) else data
    return [
        {
            "id":         str(r.get("id", "")),
            "zap_id":     str(r.get("zap_id", "")),
            "zap_name":   r.get("zap") or f"Zap {r.get('zap_id')}",
            "status":     r.get("status", "unknown"),
            "created_at": r.get("created_at", ""),
            "error_msg":  r.get("error_message") or r.get("exception") or "",
            "url":        r.get("url") or "",
        }
        for r in (runs if isinstance(runs, list) else [])
    ]


def resume_held_run(run_id: str) -> bool:
    """Replay a held or errored run. Returns True on success."""
    result = _post(f"/zap-runs/{run_id}/replay")
    if result is not None:
        print(f"[zapier] Resumed run {run_id}")
        return True
    return False


# ─── Analysis ─────────────────────────────────────────────────────────────────

def analyse(since_hours: int = 24) -> dict:
    """
    Scan last N hours of zap runs. Returns a structured summary:
      {
        "total_runs":   int,
        "errors":       [run, ...],
        "held":         [run, ...],
        "disabled_zaps":[zap, ...],
        "error_rate":   float,   # errors / total
        "since_hours":  int,
      }
    """
    runs       = get_zap_runs(since_hours=since_hours)
    all_zaps   = get_all_zaps()

    errors  = [r for r in runs if r["status"] == "error"]
    held    = [r for r in runs if r["status"] == "held"]
    total   = len(runs)
    rate    = round(len(errors) / total, 3) if total else 0.0

    disabled_zaps = [z for z in all_zaps if not z["is_enabled"]]

    return {
        "since_hours":   since_hours,
        "total_runs":    total,
        "errors":        errors,
        "held":          held,
        "disabled_zaps": disabled_zaps,
        "error_rate":    rate,
    }


# ─── Slack helpers ────────────────────────────────────────────────────────────

def _now_riyadh() -> str:
    tz = timezone(timedelta(hours=3))
    return datetime.now(tz).strftime("%d %b %Y %H:%M")


def _slack_post(blocks: list, text: str) -> None:
    try:
        _SLACK.chat_postMessage(
            channel=SLACK_CHANNEL_NOTIFY, blocks=blocks, text=text
        )
    except SlackApiError as e:
        print(f"[zapier] Slack error: {e}")


def _fmt_run_line(r: dict) -> str:
    name = (r.get("zap_name") or "Unknown Zap")[:50]
    err  = (r.get("error_msg") or "No message")[:120]
    ts   = r.get("created_at", "")[:16].replace("T", " ")
    return f"• *{name}* at {ts}\n  `{err}`"


# ─── Slack summary ────────────────────────────────────────────────────────────

def post_slack_summary(summary: dict) -> None:
    """Post a Zapier health summary to Slack."""
    errors  = summary["errors"]
    held    = summary["held"]
    disabled = summary["disabled_zaps"]
    rate    = summary["error_rate"]
    total   = summary["total_runs"]
    window  = summary["since_hours"]

    if total == 0 and not disabled:
        print("[zapier] No runs and no disabled zaps — nothing to post")
        return

    # Colour indicator
    if rate > 0.15 or len(errors) > 10:
        icon = ":red_circle:"
        status_line = f"*{len(errors)} errors* in {total} runs ({rate*100:.1f}% error rate)"
    elif errors or held:
        icon = ":large_yellow_circle:"
        status_line = f"*{len(errors)} errors, {len(held)} held* in {total} runs"
    else:
        icon = ":large_green_circle:"
        status_line = f"All {total} runs successful"

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{icon} *Zapier Health — last {window}h*\n"
                    f"{status_line}\n"
                    f"_Checked {_now_riyadh()}_"
                ),
            },
        }
    ]

    if errors:
        top = errors[:5]  # show at most 5
        lines = "\n".join(_fmt_run_line(r) for r in top)
        more  = f"\n_…and {len(errors)-5} more_" if len(errors) > 5 else ""
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Errored runs:*\n{lines}{more}"},
        })

    if held:
        top = held[:3]
        lines = "\n".join(f"• {r.get('zap_name','?')[:50]}" for r in top)
        more  = f"\n_…and {len(held)-3} more_" if len(held) > 3 else ""
        resume_note = " _(auto-resuming…)_" if AUTO_RESUME_HELD else " _(manual review needed)_"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*On-hold tasks:*{resume_note}\n{lines}{more}"},
        })

    if disabled:
        names = ", ".join(f"`{z['name'][:40]}`" for z in disabled[:5])
        more  = f" +{len(disabled)-5} more" if len(disabled) > 5 else ""
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f":pause_button: *Disabled Zaps:* {names}{more}"},
        })

    _slack_post(blocks, f"Zapier: {status_line}")


# ─── Asana task creation ──────────────────────────────────────────────────────

def _create_asana_tasks(errors: list[dict], held: list[dict]) -> None:
    try:
        from executors.asana import create_task
    except Exception:
        return

    # Group errors by zap_name to avoid one task per run
    by_zap: dict[str, list] = {}
    for r in errors:
        by_zap.setdefault(r["zap_name"], []).append(r)

    for zap_name, runs in by_zap.items():
        sample_err = runs[0].get("error_msg", "No detail")[:300]
        create_task(
            title=f"Zapier error — {zap_name[:60]} ({len(runs)} run{'s' if len(runs)>1 else ''})",
            description=(
                f"Zap: {zap_name}\n"
                f"Error count: {len(runs)}\n"
                f"Sample error: {sample_err}\n"
                f"First seen: {runs[0].get('created_at','')[:16]}\n"
                f"Last seen:  {runs[-1].get('created_at','')[:16]}\n"
                f"Action: Investigate and fix the Zap trigger/action."
            ),
            project_key="daily_activity",
            task_type="Zapier Error",
        )

    for r in held[:5]:  # cap at 5 held tasks
        create_task(
            title=f"Zapier held task — {r.get('zap_name','?')[:60]}",
            description=(
                f"Zap: {r.get('zap_name','?')}\n"
                f"Run ID: {r.get('id','?')}\n"
                f"Created: {r.get('created_at','')[:16]}\n"
                f"Action: Review in Zapier Task History and resume or discard."
            ),
            project_key="daily_activity",
            task_type="Zapier Held",
        )


# ─── Auto-resume ──────────────────────────────────────────────────────────────

def _auto_resume(held: list[dict]) -> int:
    """Resume all held tasks. Returns count resumed."""
    resumed = 0
    for r in held:
        if resume_held_run(r["id"]):
            resumed += 1
    return resumed


# ─── Main entry (called by scheduler / agent) ────────────────────────────────

def run_check(since_hours: int = 24, create_tasks: bool = True) -> dict:
    """
    Full Zapier health check. Called by the daily agent cadence or scheduler.
    Returns the summary dict.
    """
    print(f"[zapier] Running health check (last {since_hours}h)...")
    summary = analyse(since_hours=since_hours)

    errors  = summary["errors"]
    held    = summary["held"]

    print(
        f"[zapier] {summary['total_runs']} runs | "
        f"{len(errors)} errors | {len(held)} held | "
        f"{len(summary['disabled_zaps'])} disabled"
    )

    # Auto-resume held tasks if configured
    if AUTO_RESUME_HELD and held:
        resumed = _auto_resume(held)
        summary["auto_resumed"] = resumed
        print(f"[zapier] Auto-resumed {resumed} held tasks")
    else:
        summary["auto_resumed"] = 0

    # Post Slack summary if there's anything to report
    if errors or held or summary["disabled_zaps"]:
        post_slack_summary(summary)

    # Create Asana tasks for errors and held items
    if create_tasks and (errors or held):
        _create_asana_tasks(errors, held)

    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    result = run_check(since_hours=hours)
    print(f"\nSummary:")
    print(f"  Total runs:    {result['total_runs']}")
    print(f"  Errors:        {len(result['errors'])}")
    print(f"  Held:          {len(result['held'])}")
    print(f"  Disabled zaps: {len(result['disabled_zaps'])}")
    print(f"  Error rate:    {result['error_rate']*100:.1f}%")
    if result.get("auto_resumed"):
        print(f"  Auto-resumed:  {result['auto_resumed']}")
