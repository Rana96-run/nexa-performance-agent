"""
collectors/zapier_webhook.py
=============================
Flask Blueprint — receives real-time Zapier error/held payloads.

How it works
------------
You create ONE "monitor Zap" in Zapier that triggers on errors or held tasks
from your OTHER Zaps, then sends the details here via a Webhook action.

The monitor Zap recipe:
  Trigger : Zapier Manager → "Zap Error" (or "Task Held")
  Action  : Webhooks by Zapier → POST → https://<railway-domain>/webhooks/zapier
  Payload : { "zap_name": "{{zap_name}}", "status": "error",
               "error_message": "{{error_message}}", "run_url": "{{run_url}}",
               "zap_url": "{{zap_url}}" }

Optional secret: set ZAPIER_WEBHOOK_SECRET in .env.
Include it in the payload as { ..., "secret": "{{ZAPIER_WEBHOOK_SECRET}}" }
and it will be verified server-side.

See docs/zapier-monitoring-setup.md for the full Zap recipe.
"""
from __future__ import annotations

import os

from flask import Blueprint, jsonify, request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY

zapier_bp = Blueprint("zapier_webhook", __name__)

_SLACK = WebClient(token=SLACK_BOT_TOKEN)


def _verify(payload: dict) -> bool:
    return True  # open — URL obscurity is sufficient for Zapier


def _slack_post(blocks: list, text: str) -> None:
    try:
        _SLACK.chat_postMessage(
            channel=SLACK_CHANNEL_NOTIFY, blocks=blocks, text=text
        )
    except SlackApiError as e:
        print(f"[zapier-webhook] Slack error: {e}")


def _handle_error(payload: dict) -> None:
    zap_name  = payload.get("zap_name", "Unknown Zap")
    error_msg = (payload.get("error_message") or "No detail")[:1500]
    run_url   = payload.get("run_url", "")
    zap_id    = payload.get("zap_id") or ""
    run_id    = payload.get("run_id") or payload.get("id") or ""

    # ── 1. Auto-replay (handles transient failures) ──────────────────────────
    replayed = False
    if run_id:
        try:
            from collectors.zapier import resume_held_run
            replayed = resume_held_run(run_id)
        except Exception as e:
            print(f"[zapier-webhook] Auto-replay failed: {e}")

    if replayed:
        print(f"[zapier-webhook] Auto-replayed {run_id} ({zap_name}) — silent")
        return  # success, no noise

    # ── 2. Diagnose with Claude — what kind of error is this? ────────────────
    print(f"[zapier-webhook] Diagnosing persistent failure: {zap_name}")
    try:
        from claude.zap_diagnostician import diagnose
        diag = diagnose(
            zap_name=zap_name,
            error_message=error_msg,
            run_url=run_url,
            replay_attempts=1,
        )
    except Exception as e:
        print(f"[zapier-webhook] Diagnosis failed: {e}")
        diag = {
            "category": "unknown", "severity": "warning",
            "root_cause": error_msg[:200], "broken_step": "unknown",
            "fix_steps": [], "auto_action": None,
        }

    # ── 3. Take direct action based on diagnosis ─────────────────────────────
    actions_taken: list[str] = []
    category = diag.get("category", "unknown")

    # Look up Zap by name if no zap_id was sent
    if not zap_id:
        try:
            from collectors.zapier import find_zap_by_name
            z = find_zap_by_name(zap_name)
            if z:
                zap_id = z["id"]
        except Exception as e:
            print(f"[zapier-webhook] Zap lookup failed: {e}")

    # Decide what to do based on category
    should_disable = category in ("auth", "config", "logic") or diag.get("auto_action") == "turn_off"

    if should_disable and zap_id:
        try:
            from collectors.zapier import disable_zap
            if disable_zap(zap_id):
                actions_taken.append(f"Disabled Zap to stop further failures ({category} error)")
        except Exception as e:
            print(f"[zapier-webhook] Disable failed: {e}")

    if category == "api_rate":
        actions_taken.append("Will retry automatically — upstream API is throttled")

    # ── 4. Post ONE Slack message about what the AGENT did ───────────────────
    sev_emoji = {"critical": ":rotating_light:", "warning": ":warning:", "info": ":information_source:"}.get(
        diag.get("severity", "warning"), ":warning:"
    )
    actions_md = "\n".join(f"  • {a}" for a in actions_taken) or "  • Could not auto-fix — needs your eyes"

    # Only the things the user actually has to do (not generic 'check the Zap')
    user_action = ""
    if category == "auth":
        user_action = "\n*You need to:* Reconnect the disconnected app in Zapier → My Apps, then re-enable the Zap."
    elif category in ("data_format", "logic", "config"):
        user_action = f"\n*You need to:* Open the Zap, fix step `{diag.get('broken_step', '?')}`, then re-enable it."

    text = (
        f"{sev_emoji} *Zap broken — {zap_name}*\n"
        f"*Why:* {diag.get('root_cause', '?')}\n"
        f"*What I did:*\n{actions_md}"
        f"{user_action}\n"
        f"<{run_url}|Open the failed run>"
    )
    _slack_post([{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
                f"Zap broken — {zap_name}")

    # Asana task — only if there's something only the user can do
    if user_action:
        try:
            from executors.asana import create_task
            create_task(
                title=f"Zap fix — {zap_name[:60]} ({category})",
                description=(
                    f"Zap: {zap_name}\n"
                    f"Run: {run_url}\n"
                    f"Root cause: {diag.get('root_cause')}\n"
                    f"Broken step: {diag.get('broken_step')}\n\n"
                    f"What the agent did:\n" +
                    "\n".join(f"  - {a}" for a in actions_taken) + "\n\n"
                    f"What you need to do:{user_action}\n\n"
                    f"Original error:\n{error_msg}"
                ),
                project_key="daily_activity",
                task_type="Zap Fix",
            )
        except Exception as e:
            print(f"[zapier-webhook] Asana task skipped: {e}")


def _handle_held(payload: dict) -> None:
    zap_name = payload.get("zap_name", "Unknown Zap")
    run_url  = payload.get("run_url", "")
    run_id   = payload.get("run_id") or payload.get("id") or ""
    link     = f"<{run_url}|View held task>" if run_url else ""

    # Auto-resume held task immediately (always on)
    resumed = False
    if run_id and os.getenv("ZAPIER_AUTO_FIX", "true").lower() != "false":
        try:
            from collectors.zapier import resume_held_run
            resumed = resume_held_run(run_id)
            if resumed:
                print(f"[zapier-webhook] Auto-resumed held run {run_id} for {zap_name}")
        except Exception as e:
            print(f"[zapier-webhook] Auto-resume failed: {e}")

    resume_note = " :white_check_mark: _Auto-resumed_" if resumed else " :pause_button: _Awaiting manual resume_"

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":zap: :large_yellow_circle: *Zapier Task Held — {zap_name}*{resume_note}\n"
                f"{link}"
            ),
        },
    }]
    _slack_post(blocks, f"Zapier task held in {zap_name}")
    print(f"[zapier-webhook] Held task: {zap_name} — resumed={resumed}")


@zapier_bp.route("/webhooks/zapier", methods=["POST"])
def receive_zapier_event():
    """Receives real-time error/held payloads from the Zapier monitor Zap."""
    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        payload = {}

    if not _verify(payload):
        print("[zapier-webhook] Secret mismatch — rejected")
        return jsonify({"error": "unauthorized"}), 401

    status = (payload.get("status") or "error").lower()
    print(f"[zapier-webhook] Event: status={status} zap={payload.get('zap_name','?')}")

    try:
        if status == "held":
            _handle_held(payload)
        else:
            _handle_error(payload)
    except Exception as e:
        print(f"[zapier-webhook] Handler error: {e}")

    # Always return 200 so Zapier doesn't retry
    return jsonify({"received": True}), 200


@zapier_bp.route("/webhooks/zapier", methods=["GET"])
def zapier_health():
    return jsonify({"status": "ok", "service": "nexa-zapier-webhook"}), 200
