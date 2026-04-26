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
    run_id    = payload.get("run_id") or payload.get("id") or ""

    # 1. Try to auto-replay the errored run (fixes transient failures)
    replayed = False
    if run_id:
        try:
            from collectors.zapier import resume_held_run
            replayed = resume_held_run(run_id)
        except Exception as e:
            print(f"[zapier-webhook] Auto-replay failed: {e}")

    if replayed:
        print(f"[zapier-webhook] Auto-replayed {run_id} for {zap_name} — silent (only escalates if it fails again)")
        return  # transient fix worked, no Slack noise

    # 2. Auto-replay didn't help (or no run_id) → run a Claude-powered diagnosis
    #    and post ONE actionable message with specific fix steps.
    print(f"[zapier-webhook] Diagnosing persistent failure: {zap_name}")
    try:
        from claude.zap_diagnostician import diagnose, format_for_slack
        diag = diagnose(
            zap_name=zap_name,
            error_message=error_msg,
            run_url=run_url,
            replay_attempts=1,
        )
        blocks, fallback_text = format_for_slack(diag, zap_name, run_url)
        _slack_post(blocks, fallback_text)

        # Asana task with the EXACT fix steps Claude generated — not generic
        try:
            from executors.asana import create_task
            steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(diag.get("fix_steps", [])))
            create_task(
                title=f"Zap broken — {zap_name[:60]} ({diag.get('category', 'unknown')})",
                description=(
                    f"Zap: {zap_name}\n"
                    f"Run: {run_url}\n"
                    f"Category: {diag.get('category')}  |  Severity: {diag.get('severity')}\n"
                    f"Broken step: {diag.get('broken_step')}\n\n"
                    f"Root cause: {diag.get('root_cause')}\n\n"
                    f"Fix steps:\n{steps_text}\n\n"
                    f"Original error:\n{error_msg}"
                ),
                project_key="daily_activity",
                task_type="Zap Fix",
            )
        except Exception as e:
            print(f"[zapier-webhook] Asana task skipped: {e}")
    except Exception as e:
        print(f"[zapier-webhook] Diagnosis failed: {e}")
        # Fallback so we never silently swallow a persistent failure
        _slack_post([{
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                f":warning: *Zap broken — {zap_name}*\n"
                f"```{error_msg[:300]}```\n"
                f"<{run_url}|Open run>"
            )},
        }], f"Zap broken — {zap_name}")


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
