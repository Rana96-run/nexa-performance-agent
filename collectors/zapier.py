"""
collectors/zapier.py
====================
Monitors the Qoyod Zapier account and FIXES problems automatically:
  - Errored zap runs  → auto-replayed immediately + Slack alert + Asana task
  - On-hold tasks     → auto-resumed immediately + Slack alert
  - Paused/disabled zaps that should be running → daily summary alert
  - Persistent errors (failed >MAX_REPLAY_ATTEMPTS) → escalate to Asana

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

# Auto-fix is ALWAYS ON — replay errors, resume held tasks automatically.
# Set ZAPIER_AUTO_FIX=false in .env only if you need a manual-approval window.
AUTO_FIX = os.getenv("ZAPIER_AUTO_FIX", "true").lower() != "false"

# Max times we'll replay the same run before giving up and escalating.
MAX_REPLAY_ATTEMPTS = int(os.getenv("ZAPIER_MAX_REPLAY_ATTEMPTS", "3"))

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

    # Colour indicator — after auto-fix, persistent errors are what matter
    persistent = summary.get("auto_replay", {}).get("persistent", [])
    replay_ct  = summary.get("auto_replay", {}).get("replayed", 0)
    resume_ct  = summary.get("auto_resume", {}).get("resumed", 0)

    if persistent or (rate > 0.15 and not replay_ct):
        icon = ":red_circle:"
        status_line = f"*{len(persistent)} zap(s) still broken* after auto-retry — manual fix needed"
    elif errors or held:
        fixed_note = ""
        if replay_ct or resume_ct:
            parts = []
            if replay_ct: parts.append(f"{replay_ct} error(s) replayed")
            if resume_ct: parts.append(f"{resume_ct} held task(s) resumed")
            fixed_note = f" — :white_check_mark: {' & '.join(parts)}"
        icon = ":large_yellow_circle:"
        status_line = f"*{len(errors)} errors, {len(held)} held* in {total} runs{fixed_note}"
    else:
        icon = ":large_green_circle:"
        status_line = f"All {total} runs successful — no issues"

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
        top   = errors[:5]  # show at most 5
        lines = "\n".join(_fmt_run_line(r) for r in top)
        more  = f"\n_…and {len(errors)-5} more_" if len(errors) > 5 else ""
        # Show fix status if available
        ar = summary.get("auto_replay", {})
        if ar.get("replayed"):
            fix_note = f" :recycle: _{ar['replayed']} replayed automatically_"
        elif ar.get("persistent"):
            fix_note = f" :fire: _{len(ar['persistent'])} zap(s) still failing after {MAX_REPLAY_ATTEMPTS} retries — escalated_"
        elif AUTO_FIX:
            fix_note = " _(replay attempted)_"
        else:
            fix_note = " _(AUTO_FIX disabled — manual action needed)_"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Errored runs:*{fix_note}\n{lines}{more}"},
        })

    if held:
        top   = held[:3]
        lines = "\n".join(f"• {r.get('zap_name','?')[:50]}" for r in top)
        more  = f"\n_…and {len(held)-3} more_" if len(held) > 3 else ""
        rs = summary.get("auto_resume", {})
        resume_note = (
            f" :white_check_mark: _{rs.get('resumed', 0)} resumed automatically_"
            if AUTO_FIX else " _(AUTO_FIX disabled — manual review needed)_"
        )
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


# ─── Auto-fix (replay errors + resume held) ───────────────────────────────────

def _auto_replay_errors(errors: list[dict]) -> dict:
    """
    Replay every errored run.
    Returns {"replayed": int, "failed": int, "skipped": int}.
    Skips runs that have already been replayed MAX_REPLAY_ATTEMPTS times
    (detected by checking if the same zap has > MAX_REPLAY_ATTEMPTS errors
    in the window — an approximation; Zapier doesn't expose attempt count).
    """
    # Group by zap to detect persistent failures
    by_zap: dict[str, list] = {}
    for r in errors:
        by_zap.setdefault(r["zap_name"], []).append(r)

    replayed = 0
    failed   = 0
    skipped  = 0
    persistent: list[str] = []  # zaps we've given up on

    for zap_name, runs in by_zap.items():
        if len(runs) > MAX_REPLAY_ATTEMPTS:
            # Too many failures for this zap — it needs human investigation
            persistent.append(zap_name)
            skipped += len(runs)
            print(f"[zapier] PERSISTENT error in '{zap_name}' ({len(runs)} runs) — escalating")
            continue

        for r in runs:
            run_id = r.get("id")
            if not run_id:
                skipped += 1
                continue
            if resume_held_run(run_id):  # same endpoint works for error replay
                replayed += 1
                print(f"[zapier] Replayed error run {run_id} ({zap_name})")
            else:
                failed += 1

    return {"replayed": replayed, "failed": failed, "skipped": skipped,
            "persistent": persistent}


def _auto_resume_held(held: list[dict]) -> dict:
    """
    Resume ALL held tasks immediately.
    Returns {"resumed": int, "failed": int}.
    """
    resumed = 0
    failed  = 0
    for r in held:
        run_id = r.get("id")
        if not run_id:
            continue
        if resume_held_run(run_id):
            resumed += 1
            print(f"[zapier] Resumed held task {run_id} ({r.get('zap_name','?')})")
        else:
            failed += 1
    return {"resumed": resumed, "failed": failed}


def _escalate_persistent(persistent_zaps: list[str]) -> None:
    """Create an Asana task and Slack alert for zaps that keep failing."""
    if not persistent_zaps:
        return
    names = "\n".join(f"• {z}" for z in persistent_zaps)
    msg = (
        f":zap: :fire: *Zapier — Persistent Errors (need manual fix)*\n"
        f"These zaps have failed more than {MAX_REPLAY_ATTEMPTS} times "
        f"and require investigation:\n{names}"
    )
    _slack_post([{"type": "section", "text": {"type": "mrkdwn", "text": msg}}],
               f"Zapier persistent errors: {', '.join(persistent_zaps[:3])}")
    try:
        from executors.asana import create_task
        create_task(
            title=f"Zapier persistent error — {persistent_zaps[0][:60]} (+{len(persistent_zaps)-1} more)",
            description=(
                f"These Zaps have failed more than {MAX_REPLAY_ATTEMPTS} times "
                f"and were NOT auto-replayed:\n\n{names}\n\n"
                f"Action: Open Zapier Task History, check the failing step, and fix the root cause."
            ),
            project_key="daily_activity",
            task_type="Zapier Error",
        )
    except Exception as e:
        print(f"[zapier] Asana escalation task failed: {e}")


# ─── Main entry (called by scheduler / agent) ────────────────────────────────

def run_check(since_hours: int = 24, create_tasks: bool = True) -> dict:
    """
    Full Zapier health check + auto-fix.
    - Replays ALL errored runs (unless persistent: >MAX_REPLAY_ATTEMPTS failures)
    - Resumes ALL held tasks immediately
    - Posts Slack summary
    - Creates Asana tasks for persistent errors only
    Returns the summary dict with fix stats appended.
    """
    print(f"[zapier] Running health check + auto-fix (last {since_hours}h)...")
    summary = analyse(since_hours=since_hours)

    errors   = summary["errors"]
    held     = summary["held"]
    disabled = summary["disabled_zaps"]

    print(
        f"[zapier] {summary['total_runs']} runs | "
        f"{len(errors)} errors | {len(held)} held | "
        f"{len(disabled)} disabled"
    )

    replay_stats = {"replayed": 0, "failed": 0, "skipped": 0, "persistent": []}
    resume_stats = {"resumed": 0, "failed": 0}

    if AUTO_FIX:
        # Fix errors — replay every errored run immediately
        if errors:
            replay_stats = _auto_replay_errors(errors)
            print(
                f"[zapier] Errors: replayed={replay_stats['replayed']} "
                f"failed={replay_stats['failed']} "
                f"skipped={replay_stats['skipped']} "
                f"persistent={len(replay_stats['persistent'])}"
            )
            # Escalate zaps that keep failing despite replays
            if replay_stats["persistent"]:
                _escalate_persistent(replay_stats["persistent"])

        # Fix held tasks — resume every one immediately
        if held:
            resume_stats = _auto_resume_held(held)
            print(f"[zapier] Held: resumed={resume_stats['resumed']} failed={resume_stats['failed']}")
    else:
        print("[zapier] AUTO_FIX=false — monitoring only, no replays/resumes")

    summary["auto_replay"]  = replay_stats
    summary["auto_resume"]  = resume_stats

    # Post Slack summary (includes what was fixed)
    if errors or held or disabled:
        post_slack_summary(summary)

    # Create Asana tasks only for errors that persisted after replay attempts
    if create_tasks:
        persistent = replay_stats.get("persistent", [])
        persistent_runs = [r for r in errors if r.get("zap_name") in persistent]
        if persistent_runs or held:
            _create_asana_tasks(persistent_runs, [])  # held already resumed, just log errors

    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    result = run_check(since_hours=hours)
    ar = result.get("auto_replay", {})
    rs = result.get("auto_resume", {})
    print(f"\nSummary:")
    print(f"  Total runs:    {result['total_runs']}")
    print(f"  Errors:        {len(result['errors'])}")
    print(f"  Held:          {len(result['held'])}")
    print(f"  Disabled zaps: {len(result['disabled_zaps'])}")
    print(f"  Error rate:    {result['error_rate']*100:.1f}%")
    print(f"  Replayed:      {ar.get('replayed', 0)}")
    print(f"  Replay failed: {ar.get('failed', 0)}")
    print(f"  Persistent:    {len(ar.get('persistent', []))}")
    print(f"  Resumed held:  {rs.get('resumed', 0)}")
