"""
reports/app.py
==============
Flask server that:
  GET  /health                 -> 200 OK (Railway health check)
  GET  /                       -> 301 → Hex performance dashboard
  GET  /paid-performance/*     -> 301 → Hex performance dashboard
  GET  /reports/*              -> 301 → Hex performance dashboard
  POST /api/refresh            -> kick off BQ data refresh in background
  GET  /api/refresh/status     -> poll refresh progress
  POST /slack/events           -> Slack Events API (reaction_added → approve/reject)
  POST /hubspot/webhook        -> HubSpot lead webhooks (via hubspot_bp blueprint)

Both dashboards live in Hex (read from BigQuery — persistent, survives redeploys):
  Performance → qoyod-marketing-performance  (paid media KPIs)
  Activity    → nexa-agent-activity          (agent_activity_log BQ table)

Deploy on Railway (single dyno). Railway runs the agent — Hex serves the dashboards.
"""
from __future__ import annotations

import os
from datetime import datetime

from flask import Flask, jsonify, redirect, request, Response
from collectors.hubspot_webhook import hubspot_bp

app = Flask(__name__)
app.register_blueprint(hubspot_bp)


# ─── Static report pages ──────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


_REFRESH_STATUS: dict = {"running": False, "started_at": None,
                          "finished_at": None, "result": None, "error": None}


def _do_refresh(days: int | None, backfill: bool):
    """
    Run BQ refresh, recording status to _REFRESH_STATUS for polling.
    HTML report generation removed — Hex dashboard replaces it.
    """
    from datetime import datetime as _dt
    from reporting_scheduler import run_refresh

    _REFRESH_STATUS.update({
        "running": True, "started_at": _dt.utcnow().isoformat() + "Z",
        "finished_at": None, "result": None, "error": None,
    })
    try:
        if days:
            results = run_refresh(days=days)
        else:
            results = run_refresh(incremental=not backfill)
        _REFRESH_STATUS["result"] = {
            "collectors": {k: ("ok" if v[0] else "fail") for k, v in results.items()},
            "note": "HTML report deprecated — view dashboard at Hex DASHBOARD_URL",
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        _REFRESH_STATUS["error"] = str(e)
    finally:
        from datetime import datetime as _dt
        _REFRESH_STATUS["finished_at"] = _dt.utcnow().isoformat() + "Z"
        _REFRESH_STATUS["running"] = False



@app.route("/api/refresh", methods=["POST", "GET"])
def refresh_bq():
    """
    Kick off a BigQuery refresh + view rebuild + report regen.
    Runs in the background so the HTTP response returns immediately.
    Poll /api/refresh/status to check progress.

    Query params:
      ?days=N       Backfill last N days for every collector (e.g. 14, 30).
      ?backfill=1   Full historical backfill (very slow).
      Without args  Incremental refresh — last 2 days only.
    """
    import threading
    expected = os.getenv("REGEN_TOKEN")
    if expected and request.args.get("token") != expected:
        return jsonify({"error": "unauthorized"}), 401
    if _REFRESH_STATUS.get("running"):
        return jsonify({"queued": False, "reason": "another refresh is already running",
                        "status": _REFRESH_STATUS}), 409

    backfill = request.args.get("backfill") == "1"
    days_arg = request.args.get("days")
    days = int(days_arg) if days_arg and days_arg.isdigit() else None
    threading.Thread(target=_do_refresh, args=(days, backfill), daemon=True).start()
    return jsonify({
        "queued": True,
        "mode": "backfill" if backfill else (f"days={days}" if days else "incremental"),
        "poll": "/api/refresh/status",
    })


@app.route("/api/refresh/status")
def refresh_status():
    return jsonify(_REFRESH_STATUS)



_HEX_DASHBOARD = (
    os.getenv(
        "DASHBOARD_URL",
        "https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/"
        "Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest",
    )
)


@app.route("/")
@app.route("/paid-performance/latest")
@app.route("/paid-performance/<report_date>")
@app.route("/reports/latest")
@app.route("/reports/<report_date>")
def dashboard_redirect(**kwargs):
    """All old HTML report URLs → Hex performance dashboard (permanent redirect)."""
    return redirect(_HEX_DASHBOARD, code=301)



# ─── Removed: /api/report (HTML report custom date-range API) ────────────────
# Hex dashboard replaces the HTML report. Route removed 2026-05-04.


# ─── Slack Events API ─────────────────────────────────────────────────────────

def _verify_slack_signature(raw_body: bytes, headers) -> bool:
    """
    Verify Slack request signature using the raw body bytes.
    Must receive raw body BEFORE any json parsing — calling get_json() first
    consumes the stream and makes get_data() return empty, breaking the HMAC.
    """
    import hashlib, hmac as _hmac, time as _time
    secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not secret:
        return True  # no secret configured — skip (dev / first-run)
    ts  = headers.get("X-Slack-Request-Timestamp", "")
    sig = headers.get("X-Slack-Signature", "")
    if not ts or not sig:
        return False
    try:
        if abs(_time.time() - float(ts)) > 300:
            return False  # replay-attack window
    except ValueError:
        return False
    basestring = f"v0:{ts}:{raw_body.decode('utf-8')}".encode()
    expected   = "v0=" + _hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, sig)


def _handle_reaction(event: dict):
    """
    Called in a background thread when ✅ or ❌ is added to an approval message.
    Looks up the ts in pending_approvals.json, executes if approved, then replies in thread.
    """
    reaction = event.get("reaction", "")
    item     = event.get("item", {})
    msg_ts   = item.get("ts", "")

    if reaction not in ("white_check_mark", "x"):
        return

    try:
        from notifications.slack import get_pending_approval, remove_pending_approval
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
        wc   = WebClient(token=SLACK_BOT_TOKEN)
        meta = get_pending_approval(msg_ts)
        if not meta:
            return  # not one of our messages

        action = meta.get("action", "")
        # Build a human-readable label for the reaction reply
        if action == "batch_scale_pause":
            findings = meta.get("findings", [])
            camp = f"{len(findings)} campaign(s)"
        else:
            camp = meta.get("campaign", "") or ", ".join(meta.get("campaigns", [])[:3])
        user   = event.get("user", "")

        if reaction == "white_check_mark":
            exec_result = _execute_approved_action(meta)
            try:
                from logs.activity_logger import log_activity_async
                log_activity_async(role="slack_approval",
                                   action=f"approved: {action} on {camp[:60]}",
                                   status="approved", channel=meta.get("channel", ""),
                                   campaign_name=camp,
                                   details={"user": user, "result": exec_result[:200]})
            except Exception:
                pass
            # Update Asana for each finding in a batch, or the single asana_gid
            gids = [f.get("asana_gid") for f in meta.get("findings", []) if f.get("asana_gid")]
            if not gids and meta.get("asana_gid"):
                gids = [meta["asana_gid"]]
            for gid in gids:
                try:
                    import asana as asana_sdk
                    cfg = asana_sdk.Configuration()
                    cfg.access_token = os.getenv("ASANA_ACCESS_TOKEN", "")
                    ac  = asana_sdk.ApiClient(cfg)
                    asana_sdk.StoriesApi(ac).create_story_for_task(
                        gid,
                        {"data": {"text": f"[Nexa] Approved by <@{user}>. Result: {exec_result[:200]}"}},
                    )
                except Exception as e:
                    print(f"[events] Asana comment failed for {gid}: {e}")
            reply = f"✅ *Approved* by <@{user}>\n{exec_result}"
        else:
            reply = f"❌ *Rejected* by <@{user}>\n`{camp}` — no changes made."
            try:
                from logs.activity_logger import log_activity_async
                log_activity_async(role="slack_approval",
                                   action=f"rejected: {action} on {camp[:60]}",
                                   status="rejected", channel=meta.get("channel", ""),
                                   campaign_name=camp,
                                   details={"user": user})
            except Exception:
                pass

        wc.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            thread_ts=msg_ts,
            text=reply,
        )
        remove_pending_approval(msg_ts)
        print(f"[events] Reaction '{reaction}' by {user} for {camp[:50]!r}")
    except Exception as e:
        print(f"[events] reaction handler error: {e}")


def _execute_approved_action(meta: dict) -> str:
    """
    Execute a scale or pause that was approved via yes/no reply.
    Returns a human-readable result string.
    """
    action      = meta.get("action", "").lower()
    channel     = meta.get("channel", "")
    campaign    = meta.get("campaign", "")
    campaign_id = meta.get("campaign_id", "")
    account_id  = meta.get("account_id", "")
    new_budget  = meta.get("new_budget")

    if action == "scale":
        if not campaign_id or not new_budget:
            return f"Could not execute — missing campaign_id or budget. Scale `{campaign}` manually to ${new_budget:.0f}/day." if new_budget else f"Scale `{campaign}` manually (+25%)."
        try:
            if channel == "google_ads":
                from executors.google_ads import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget, customer_id=account_id)
            elif channel == "meta":
                from executors.meta import update_campaign_budget
                update_campaign_budget(campaign_id, new_budget)
            elif channel == "snapchat":
                from executors.snapchat import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget, account_id=account_id)
            elif channel == "tiktok":
                from executors.tiktok import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget, advertiser_id=account_id)
            elif channel == "linkedin":
                from executors.linkedin import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget)
            else:
                return f"Channel `{channel}` not supported for auto-scale. Set budget to ${new_budget:.0f}/day manually."
            return f"Budget increased to ${new_budget:.0f}/day (+25%). Done."
        except Exception as e:
            return f"Scale execution failed: {e}. Set to ${new_budget:.0f}/day manually."

    elif action == "pause":
        if not campaign_id:
            return f"Could not execute — no campaign_id. Pause `{campaign}` manually."
        try:
            if channel == "google_ads":
                from executors.google_ads import pause_campaign
                pause_campaign(campaign_id, customer_id=account_id)
            elif channel == "meta":
                from executors.meta import pause_campaign
                pause_campaign(campaign_id)
            elif channel == "snapchat":
                from executors.snapchat import pause_campaign
                pause_campaign(campaign_id, account_id=account_id)
            elif channel == "tiktok":
                from executors.tiktok import pause_campaign
                pause_campaign(campaign_id, advertiser_id=account_id)
            elif channel == "linkedin":
                from executors.linkedin import pause_campaign
                pause_campaign(campaign_id)
            else:
                return f"Channel `{channel}` not supported for auto-pause. Pause `{campaign}` manually."
            return f"Campaign paused. Done."
        except Exception as e:
            return f"Pause execution failed: {e}. Pause `{campaign}` manually."

    elif action == "batch_scale_pause":
        results = []
        for f in meta.get("findings", []):
            sub = _execute_approved_action(f)
            results.append(f"`{f.get('campaign', '?')}`: {sub}")
        return "\n".join(results) if results else "Nothing to execute."

    return "Acknowledged — Asana tasks updated."


def _handle_thread_reply(event: dict):
    """
    Called in a background thread when a message is posted in the approval channel.
    Looks for yes/no replies to pending approval messages and executes accordingly.
    """
    # Only process thread replies (has thread_ts and it differs from the message ts)
    thread_ts = event.get("thread_ts", "")
    msg_ts    = event.get("ts", "")
    if not thread_ts or thread_ts == msg_ts:
        return  # top-level message, not a reply

    text = (event.get("text") or "").strip().lower()
    if text not in ("yes", "no"):
        return  # not a yes/no reply

    try:
        from notifications.slack import get_pending_approval, remove_pending_approval
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
        wc   = WebClient(token=SLACK_BOT_TOKEN)
        meta = get_pending_approval(thread_ts)
        if not meta:
            return  # not one of our approval messages

        action = meta.get("action", "")
        camp   = meta.get("campaign", "") or ", ".join(meta.get("campaigns", [])[:3])
        user   = event.get("user", "")

        if text == "yes":
            exec_result = _execute_approved_action(meta)
            # Add Asana comment if gid is stored
            asana_gid = meta.get("asana_gid", "")
            if asana_gid:
                try:
                    import asana as asana_sdk
                    cfg = asana_sdk.Configuration()
                    cfg.access_token = os.getenv("ASANA_ACCESS_TOKEN", "")
                    ac  = asana_sdk.ApiClient(cfg)
                    asana_sdk.StoriesApi(ac).create_story_for_task(
                        asana_gid,
                        {"data": {"text": f"[Nexa] Approved by <@{user}>. Result: {exec_result}"}},
                    )
                except Exception as e:
                    print(f"[events] Asana comment failed: {e}")
            reply = f"✅ *Approved* by <@{user}>\n{exec_result}"
        else:
            reply = f"❌ *Skipped* by <@{user}>\n`{camp}` — no changes made."

        wc.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            thread_ts=thread_ts,
            text=reply,
        )
        remove_pending_approval(thread_ts)
        print(f"[events] Reply '{text}' by {user} for {camp[:50]!r}")
    except Exception as e:
        print(f"[events] thread reply handler error: {e}")


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Slack Events API endpoint.
    1. URL verification (one-time during Events setup)
    2. reaction_added on approval messages → approve/reject
    """
    import json as _json

    # Read raw body ONCE — must happen before any get_json() call
    raw_body = request.get_data()
    try:
        payload = _json.loads(raw_body) if raw_body else {}
    except Exception:
        payload = {}
    event_type = payload.get("type", "")

    # URL verification: respond immediately, no signature check needed
    if event_type == "url_verification":
        return jsonify({"challenge": payload.get("challenge", "")})

    # All other events: verify signature using the already-read raw body
    if not _verify_slack_signature(raw_body, request.headers):
        return jsonify({"error": "invalid signature"}), 403

    if event_type == "event_callback":
        event      = payload.get("event", {})
        event_kind = event.get("type", "")

        if event_kind == "reaction_added":
            import threading
            threading.Thread(target=_handle_reaction, args=(event,), daemon=True).start()

    # Always respond 200 immediately (Slack requires < 3s)
    return Response("", status=200)


# ─── Startup: warn if pending approvals were lost on redeploy ─────────────────

def _check_pending_on_startup():
    """Log any surviving pending approvals so we know the state on boot."""
    try:
        from notifications.slack import _load_pending
        pending = _load_pending()
        if pending:
            print(f"[startup] {len(pending)} pending approval(s) survived redeploy: "
                  f"{list(pending.keys())}")
        else:
            print("[startup] No pending approvals on disk.")
    except Exception as e:
        print(f"[startup] Could not read pending approvals: {e}")

_check_pending_on_startup()


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
