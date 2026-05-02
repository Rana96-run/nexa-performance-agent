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


def post_nightly_approvals_digest(
    scale_findings: list,
    pause_findings: list,
    review_findings: list,
) -> str | None:
    """
    THE ONE #approvals message per night.

    Covers everything in a single post:
      - Scale candidates  (✅ executes +25% budget)
      - Pause candidates  (✅ executes pause)
      - Review summary    (optimize / junk / drilldown — tasks already in Asana)

    ✅ = execute all scale + pause actions  ·  ❌ = skip all
    Returns the Slack message ts, or None on failure.
    """
    from notifications.quiet import is_quiet, quiet_log

    if not scale_findings and not pause_findings and not review_findings:
        return None

    today = datetime.now(timezone.utc).strftime("%b %-d")
    lines = [f":arrows_counterclockwise: *Nightly approvals — {today}*"]

    executable_findings = []

    if scale_findings:
        lines.append("\n*Scale ↑* (+25% budget)")
        for f in scale_findings:
            cpql  = f"CPQL ${f['cpql']:.0f}" if f.get("cpql") else "CPQL N/A"
            avg   = f.get("avg_spend")
            new_b = f.get("new_budget")
            budget = f"  ·  ${avg:.0f}→${new_b:.0f}/day" if avg and new_b else ""
            lines.append(f"  • `{f.get('campaign', '?')}`  {cpql}{budget}")
        executable_findings.extend(scale_findings)

    if pause_findings:
        lines.append("\n*Pause ⏸*")
        for f in pause_findings:
            cpql = f"CPQL ${f['cpql']:.0f}" if f.get("cpql") else "CPQL N/A"
            qual = f"{f.get('qual_rate', 0):.0f}%"
            lines.append(f"  • `{f.get('campaign', '?')}`  {cpql}  ·  qual {qual}")
        executable_findings.extend(pause_findings)

    if review_findings:
        # Summarise review items — counts only, no names (tasks are in Asana)
        counts: dict[str, int] = {}
        for f in review_findings:
            tag = "Junk" if f.get("junk_leads") else f.get("action", "?").title()
            counts[tag] = counts.get(tag, 0) + 1
        review_line = "  ·  ".join(f"{tag} ×{n}" for tag, n in sorted(counts.items()))
        lines.append(f"\n*Review → Asana*  {review_line}")

    if executable_findings:
        lines.append("\nReact :white_check_mark: to execute scale/pause  ·  :x: to skip all")
    else:
        lines.append("\nReact :white_check_mark: to acknowledge  ·  :x: to dismiss")

    full_text = "\n".join(lines)

    if is_quiet():
        quiet_log("nightly-approvals-digest", SLACK_CHANNEL_APPROVAL, full_text)
        return None

    try:
        response = client.chat_postMessage(channel=SLACK_CHANNEL_APPROVAL, text=full_text)
        ts = response["ts"]
        for emoji in ("white_check_mark", "x"):
            try:
                client.reactions_add(channel=SLACK_CHANNEL_APPROVAL, name=emoji, timestamp=ts)
            except SlackApiError:
                pass
        save_pending_approval(ts, {
            "action":   "batch_scale_pause",
            "findings": [
                {
                    "action":      f.get("action"),
                    "channel":     f.get("channel"),
                    "campaign":    f.get("campaign"),
                    "campaign_id": f.get("campaign_id", ""),
                    "account_id":  f.get("account_id", ""),
                    "new_budget":  f.get("new_budget"),
                    "asana_gid":   f.get("asana_gid", ""),
                }
                for f in executable_findings
            ],
        })
        return ts
    except SlackApiError as e:
        print(f"[nightly-approvals-digest] Slack error: {e}")
        return None


# Keep old names as aliases so any external callers don't break silently.
def post_scale_pause_digest(scale_findings: list, pause_findings: list) -> str | None:
    return post_nightly_approvals_digest(scale_findings, pause_findings, [])


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
    """Deprecated alias — use post_nightly_approvals_digest."""
    return post_nightly_approvals_digest([], [], findings)


def _post_approval_digest_real(findings: list[dict]) -> str | None:
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
