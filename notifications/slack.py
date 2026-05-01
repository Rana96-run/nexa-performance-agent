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


def post_action_approval(finding: dict, avg_spend: float | None = None) -> str | None:
    """
    Post ONE individual approval request for a scale or pause action.
    Each campaign gets its own message so the user can reply yes/no per campaign.
    Returns the Slack message ts, or None on failure.
    """
    from notifications.quiet import is_quiet, quiet_log

    action   = finding.get("action", "").lower()
    campaign = finding.get("campaign", "?")
    channel  = finding.get("channel", "?")
    cpql_str = f"${finding['cpql']:.0f}" if finding.get("cpql") else "N/A"
    cpl_str  = f"${finding['cpl']:.0f}"  if finding.get("cpl")  else "N/A"
    qual_str = f"{finding.get('qual_rate', 0):.0f}%"

    if action == "scale":
        icon   = ":large_green_circle:"
        title  = f"{icon} *Scale approval needed*"
        budget_line = ""
        if avg_spend:
            new_b = round(avg_spend * 1.25, 0)
            budget_line = f"\nBudget: ~${avg_spend:.0f}/day  →  ~${new_b:.0f}/day  (+25%)"
        body = (
            f"Campaign: `{campaign}`\n"
            f"CPQL {cpql_str}  ·  CPL {cpl_str}  ·  qual rate {qual_str}{budget_line}\n"
            f"Both CPQL and CPL are in the scale zone and qual rate is healthy."
        )
        reply_hint = "React :white_check_mark: to increase budget +25%, or :x: to skip."
    else:
        icon  = ":red_circle:"
        title = f"{icon} *Pause approval needed*"
        body  = (
            f"Campaign: `{campaign}`\n"
            f"CPQL {cpql_str}  ·  CPL {cpl_str}  ·  qual rate {qual_str}\n"
            f"Running 14+ days with CPQL above critical threshold."
        )
        reply_hint = "React :white_check_mark: to pause this campaign, or :x: to skip."

    full_text = f"{title}\n{body}\n{reply_hint}"

    if is_quiet():
        quiet_log("action-approval", SLACK_CHANNEL_APPROVAL, full_text)
        return None

    try:
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": reply_hint},
            ]},
        ]
        response = client.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            blocks=blocks,
            text=full_text,
        )
        ts = response["ts"]
        for emoji in ("white_check_mark", "x"):
            try:
                client.reactions_add(channel=SLACK_CHANNEL_APPROVAL, name=emoji, timestamp=ts)
            except SlackApiError:
                pass
        save_pending_approval(ts, {
            "action":      action,
            "channel":     channel,
            "campaign":    campaign,
            "campaign_id": finding.get("campaign_id", ""),
            "account_id":  finding.get("account_id", ""),
            "new_budget":  round(avg_spend * 1.25, 2) if avg_spend else None,
            "asana_gid":   finding.get("asana_gid", ""),
        })
        return ts
    except SlackApiError as e:
        print(f"[action-approval] Slack error: {e}")
        return None


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


def post_approval_digest(findings: list[dict]) -> str | None:
    """
    Post ONE compact digest message for a batch of optimize/junk/drilldown findings.
    One message instead of N — keeps #approvals scannable.

    findings: list of health-finding dicts (same shape as what _send_approval_requests receives).
    Returns the message ts or None on failure.
    """
    from notifications.quiet import is_quiet, quiet_log

    if not findings:
        return None

    # Header line: count + action types present
    action_counts: dict[str, int] = {}
    for f in findings:
        tag = "JUNK-LEADS" if f.get("junk_leads") else f.get("action", "?").upper()
        action_counts[tag] = action_counts.get(tag, 0) + 1
    summary_parts = [f"{n} {a.lower()}" for a, n in sorted(action_counts.items())]
    header = f":warning: *{', '.join(summary_parts)} — review needed*"

    # One line per campaign: channel · name — CPQL · CPL · qual% · reason
    rows = []
    for f in findings:
        cpql_str = f"CPQL ${f['cpql']:.0f}" if f.get("cpql") else "CPQL N/A"
        cpl_str  = f"CPL ${f['cpl']:.0f}"   if f.get("cpl")  else "CPL N/A"
        qual_str = f"qual {f.get('qual_rate', 0):.0f}%"
        reason   = (f.get("note") or "")[:80]
        tag      = " *[JUNK-LEADS]*" if f.get("junk_leads") else ""
        rows.append(
            f"  *{f.get('channel','?')}* · `{f.get('campaign','?')}`{tag}  —  "
            f"{cpql_str} · {cpl_str} · {qual_str}"
            + (f"\n  _{reason}_" if reason else "")
        )

    body = "\n".join(rows)
    footer = "Tasks created in Asana. React :white_check_mark: to acknowledge or :x: to dismiss."
    full_text = f"{header}\n{body}\n{footer}"

    if is_quiet():
        quiet_log("approval-digest", SLACK_CHANNEL_APPROVAL, full_text)
        return None

    try:
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": header}},
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": footer},
            ]},
        ]
        response = client.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            blocks=blocks,
            text=full_text,
        )
        ts = response["ts"]
        save_pending_approval(ts, {
            "action":    "digest",
            "campaigns": [f.get("campaign", "") for f in findings],
        })
        return ts
    except SlackApiError as e:
        print(f"[approval-digest] Slack error: {e}")
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
