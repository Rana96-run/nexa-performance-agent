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

_SECRET = os.getenv("ZAPIER_WEBHOOK_SECRET", "")
_SLACK  = WebClient(token=SLACK_BOT_TOKEN)


def _verify(payload: dict) -> bool:
    if not _SECRET:
        return True  # no secret configured → open (rely on obscurity of URL)
    return payload.get("secret") == _SECRET


def _slack_post(blocks: list, text: str) -> None:
    try:
        _SLACK.chat_postMessage(
            channel=SLACK_CHANNEL_NOTIFY, blocks=blocks, text=text
        )
    except SlackApiError as e:
        print(f"[zapier-webhook] Slack error: {e}")


def _handle_error(payload: dict) -> None:
    zap_name  = payload.get("zap_name", "Unknown Zap")
    error_msg = (payload.get("error_message") or "No detail")[:300]
    run_url   = payload.get("run_url", "")
    zap_url   = payload.get("zap_url", "")

    link = f"<{run_url}|View run>" if run_url else (f"<{zap_url}|Open Zap>" if zap_url else "")

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":zap: :red_circle: *Zapier Error — {zap_name}*\n"
                f"```{error_msg}```\n"
                f"{link}"
            ),
        },
    }]
    _slack_post(blocks, f"Zapier error in {zap_name}")
    print(f"[zapier-webhook] Error alert: {zap_name} — {error_msg[:80]}")

    # Create Asana task for the error
    try:
        from executors.asana import create_task
        create_task(
            title=f"Zapier error — {zap_name[:70]}",
            description=(
                f"Zap: {zap_name}\n"
                f"Error: {error_msg}\n"
                f"Run: {run_url}\n"
                f"Action: Fix the failing step in Zapier."
            ),
            project_key="daily_activity",
            task_type="Zapier Error",
        )
    except Exception as e:
        print(f"[zapier-webhook] Asana task skipped: {e}")


def _handle_held(payload: dict) -> None:
    zap_name = payload.get("zap_name", "Unknown Zap")
    run_url  = payload.get("run_url", "")
    link     = f"<{run_url}|View held task>" if run_url else ""

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":zap: :large_yellow_circle: *Zapier Task On Hold — {zap_name}*\n"
                f"A task is waiting for review before it can continue.\n"
                f"{link}"
            ),
        },
    }]
    _slack_post(blocks, f"Zapier task held in {zap_name}")
    print(f"[zapier-webhook] Held task: {zap_name}")

    # Auto-resume if configured
    run_id = payload.get("run_id")
    if run_id and os.getenv("ZAPIER_AUTO_RESUME", "false").lower() == "true":
        try:
            from collectors.zapier import resume_held_run
            if resume_held_run(run_id):
                print(f"[zapier-webhook] Auto-resumed held run {run_id}")
        except Exception as e:
            print(f"[zapier-webhook] Auto-resume failed: {e}")


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
