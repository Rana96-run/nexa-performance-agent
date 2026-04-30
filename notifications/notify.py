"""
Unified notification wrapper.

Honors config.NOTIFY_VIA:
  'slack'  -> Slack only
  'email'  -> Email only (current default while Slack is being set up)
  'both'   -> Slack first, email as audit trail

Channel split:
  'notify'   -> summaries, alerts, reminders  (SLACK_CHANNEL_NOTIFY)
  'approval' -> approval requests             (SLACK_CHANNEL_APPROVAL)

Returns a dict:
  { "slack_ts": str|None, "email_sent": bool, "channel_used": "slack"|"email"|"both"|"none" }
Approval polling uses 'slack_ts'. When Slack is disabled, approvals are
emailed instead and auto-execution is skipped (approve via Asana task).
"""
from typing import Optional
from datetime import datetime, timezone, timedelta
from config import (
    NOTIFY_VIA, SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL,
    SLACK_CHANNEL_HEALTH,
)
from notifications import email as email_mod

try:
    from notifications.slack import client as slack_client, post_approval_request as slack_approval
    SLACK_OK = True
except Exception as e:
    print(f"[notify] Slack client unavailable: {e}")
    slack_client = None
    SLACK_OK = False


from notifications.quiet import is_quiet, quiet_log


def _slack_post(channel: str, text: str, blocks=None) -> Optional[str]:
    if is_quiet():
        quiet_log("notify", channel, text)
        return None
    if not (SLACK_OK and slack_client and channel):
        return None
    try:
        resp = slack_client.chat_postMessage(channel=channel, text=text, blocks=blocks)
        return resp["ts"]
    except Exception as e:
        print(f"[notify] Slack post failed: {e}")
        return None


def send_summary(subject: str, body_text: str, body_html: str | None = None,
                 event_type: str = "daily_summary", meta: dict | None = None) -> dict:
    """Non-approval notification (summary, alert, reminder)."""
    ts = None
    mailed = False

    if NOTIFY_VIA in ("slack", "both"):
        ts = _slack_post(SLACK_CHANNEL_NOTIFY, f"*{subject}*\n{body_text}")

    if NOTIFY_VIA in ("email", "both"):
        html = body_html or f"<p>{body_text.replace(chr(10), '<br>')}</p>"
        try:
            mailed = email_mod.send(event_type, subject, html, meta=meta)
        except Exception as e:
            print(f"[notify] Email failed: {e}")

    return {"slack_ts": ts, "email_sent": mailed, "channel_used": _label(ts, mailed)}


def send_approval_request(analysis: dict) -> dict:
    """Approval-required notification. Returns slack_ts for polling (or None if email-only)."""
    decision = analysis.get("decision", {}) or {}
    subject = f"Approval needed: {decision.get('action','?')} on {decision.get('channel','?')}"
    body = (
        f"Action: {decision.get('action','N/A')}\n"
        f"Channel: {decision.get('channel','N/A')}\n"
        f"Campaign: {decision.get('campaign','N/A')}\n"
        f"KPI: {decision.get('kpi','N/A')} = {decision.get('value','N/A')}\n"
        f"Confidence: {decision.get('confidence','N/A')}\n"
        f"Reason: {decision.get('reason','N/A')}"
    )

    ts = None
    mailed = False

    if NOTIFY_VIA in ("slack", "both") and SLACK_OK:
        if is_quiet():
            quiet_log("notify", "approval-channel", body)
        else:
            try:
                ts = slack_approval(analysis)
            except Exception as e:
                print(f"[notify] Slack approval post failed: {e}")

    if NOTIFY_VIA in ("email", "both"):
        html = (
            f"<p><b>Approval needed</b></p>"
            f"<pre style='background:#f5f7fa;padding:12px;border-radius:6px'>{body}</pre>"
            f"<p>While Slack is being set up, approve/reject by updating the Asana task status.</p>"
        )
        try:
            mailed = email_mod.send("approval_needed", subject, html,
                                    meta={"Action": decision.get("action"),
                                          "Channel": decision.get("channel"),
                                          "Confidence": decision.get("confidence")})
        except Exception as e:
            print(f"[notify] Email approval failed: {e}")

    return {"slack_ts": ts, "email_sent": mailed, "channel_used": _label(ts, mailed)}


def post_to_slack(text: str, channel: str | None = None) -> Optional[str]:
    """
    Post a plain-text message to Slack.
    Defaults to SLACK_CHANNEL_NOTIFY if no channel is specified.
    Returns the Slack message timestamp (ts) or None on failure.
    """
    target = channel or SLACK_CHANNEL_NOTIFY
    return _slack_post(target, text)


def _label(ts, mailed):
    if ts and mailed: return "both"
    if ts: return "slack"
    if mailed: return "email"
    return "none"


# ---------------------------------------------------------------------------
# Heartbeat — one-liner beacon posted at the end of every scheduler run.
# If you stop seeing heartbeats, something broke. Silent failures are the
# enemy; this turns them into visible ones.
# ---------------------------------------------------------------------------

# Riyadh time for the beacon — matches the team's working hours.
_RIYADH = timezone(timedelta(hours=3))


def send_heartbeat(source: str, status: str = "ok",
                   detail: str = "", duration_s: float | None = None) -> bool:
    """Post a health beacon to Slack — but ONLY on failure.

    Success and "started" statuses are logged to console only; they are noise
    in the main channel. Only failures get a Slack message so every alert means
    something went wrong.

    Args:
        source     — e.g. "bq-refresh", "operational-scheduler", "slack-listener"
        status     — "ok" | "failed" | "started"
        detail     — free-form tail, e.g. "collector crashed"
        duration_s — how long the run took, seconds (optional)

    Returns True if a Slack message was sent. Never raises.
    """
    dur  = f" ({duration_s:.1f}s)" if duration_s is not None else ""
    when = datetime.now(_RIYADH).strftime("%Y-%m-%d %H:%M")
    log  = f"[heartbeat] {source} {status}{dur} — {when} Riyadh"
    if detail:
        log += f" | {detail}"
    print(log)

    # Only alert on failure — success is silence.
    if status != "failed":
        return False

    if not (SLACK_OK and slack_client and SLACK_CHANNEL_HEALTH):
        return False

    body = f":x: *{source}* failed{dur} — {when} Riyadh"
    if detail:
        body += f"\n> {detail}"
    if is_quiet():
        quiet_log("heartbeat", SLACK_CHANNEL_HEALTH, body)
        return False
    try:
        slack_client.chat_postMessage(channel=SLACK_CHANNEL_HEALTH, text=body)
        return True
    except Exception as e:
        print(f"[heartbeat] Slack post failed: {e}")
        return False
