import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL


client = WebClient(token=SLACK_BOT_TOKEN)

# ── Pending approval store ────────────────────────────────────────────────────
# Persists ts → metadata so the events endpoint can look up what to execute.

_PENDING_FILE = Path(os.getenv("DATA_DIR", "/tmp")) / "pending_approvals.json"


def _load_pending() -> dict:
    if _PENDING_FILE.exists():
        try:
            return json.loads(_PENDING_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_pending(data: dict):
    try:
        _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PENDING_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"[approval-store] write failed: {e}")


def save_pending_approval(ts: str, metadata: dict):
    """Persist approval message ts + execution metadata for later reaction lookup."""
    data = _load_pending()
    data[ts] = {**metadata, "posted_at": datetime.now(timezone.utc).isoformat()}
    _save_pending(data)


def remove_pending_approval(ts: str):
    """Remove a resolved (approved/rejected) approval entry."""
    data = _load_pending()
    data.pop(ts, None)
    _save_pending(data)


def get_pending_approval(ts: str) -> dict | None:
    return _load_pending().get(ts)


def post_approval_request(analysis: dict, execution_metadata: dict | None = None) -> str:
    """
    Post Claude's decisions to Slack for approval — concise, scannable layout.
    Returns the message timestamp (ts) to track approval reaction.
    execution_metadata: extra data (account_id, campaign_id, etc.) needed to
    execute the action on approval. Persisted to pending_approvals.json.
    """
    from notifications.quiet import is_quiet, quiet_log

    decision = analysis.get("decision", {}) or {}
    action     = decision.get("action", "?").upper()
    channel    = decision.get("channel", "?")
    campaign   = decision.get("campaign", "")
    kpi        = decision.get("kpi", "?")
    value      = decision.get("value", "?")
    threshold  = decision.get("threshold", "")
    reason     = decision.get("reason", "") or decision.get("decision", "")
    confidence = decision.get("confidence", "?")

    # ── Header (one line, scannable) ────────────────────────────────────────
    header = f"*{action}* · {channel}"
    if campaign:
        header += f" · `{campaign}`"

    # ── Why (the proof) ────────────────────────────────────────────────────
    proof_lines = []
    if kpi != "?":
        proof_lines.append(f"*{kpi}* = `{value}`" + (f" (threshold {threshold})" if threshold else ""))
    if reason:
        proof_lines.append(f"_{reason}_")
    proof_lines.append(f"Confidence: {confidence}")
    proof_text = "\n".join(proof_lines)

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": proof_text}},
        {"type": "context", "elements": [
            {"type": "mrkdwn",
             "text": "React with :white_check_mark: to approve or :x: to reject"},
        ]},
    ]
    fallback_text = f"Approval: {action} {channel} {campaign}".strip()

    if is_quiet():
        quiet_log("approval", SLACK_CHANNEL_APPROVAL, fallback_text)
        return None
    try:
        response = client.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            blocks=blocks, text=fallback_text,
        )
        ts = response["ts"]
        # Pre-add both reactions so the user just clicks an existing one
        for emoji in ("white_check_mark", "x"):
            try:
                client.reactions_add(
                    channel=SLACK_CHANNEL_APPROVAL,
                    name=emoji,
                    timestamp=ts,
                )
            except SlackApiError:
                pass  # reaction already exists or missing scope — non-fatal

        # Persist for the events endpoint to look up on reaction
        meta = {
            "action":    decision.get("action", ""),
            "channel":   decision.get("channel", ""),
            "campaign":  decision.get("campaign", ""),
            "reason":    decision.get("reason", ""),
        }
        if execution_metadata:
            meta.update(execution_metadata)
        save_pending_approval(ts, meta)
        return ts
    except SlackApiError as e:
        print(f"Slack error: {e}")
        return None


def check_approval(message_ts: str) -> str:
    """
    Check if the message was approved or rejected via emoji reaction.
    Returns: 'approved', 'rejected', or 'pending'
    """
    try:
        response = client.reactions_get(
            channel=SLACK_CHANNEL_APPROVAL,
            timestamp=message_ts
        )
        reactions = response.get("message", {}).get("reactions", [])
        reaction_names = [r["name"] for r in reactions]

        if "white_check_mark" in reaction_names:
            return "approved"
        elif "x" in reaction_names:
            return "rejected"
        return "pending"
    except SlackApiError as e:
        print(f"Slack error: {e}")
        return "pending"


def extract_slack_draft(raw_response: str) -> str:
    """Pull the Slack Draft section from Claude's response."""
    match = re.search(
        r'(?:Slack Draft|##\s*Slack Draft)(.*?)(?=##|\Z)',
        raw_response,
        re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return raw_response[:500]  # fallback: first 500 chars
