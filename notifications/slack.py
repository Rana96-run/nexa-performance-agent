import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL


_raw_client = WebClient(token=SLACK_BOT_TOKEN)


# ── QA gate wrapper around chat_postMessage ───────────────────────────────────
# Every Slack post in this codebase goes through this `client` symbol. Wrapping
# chat_postMessage forces every outbound message through the QA gate. The gate
# auto-retries once on transient failures and hard-blocks on persistent ones.
# Disable for tests: QA_GATE_DISABLED=1
class _GatedSlackClient:
    """Proxy that delegates everything to the real WebClient except
    chat_postMessage, which is gated by QA verification."""

    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, name):
        return getattr(self._raw, name)

    def chat_postMessage(self, **kwargs):
        try:
            from qa.gate import gate
            text = kwargs.get("text") or ""
            # If blocks are provided, also extract text from them for verification
            for blk in (kwargs.get("blocks") or []):
                if isinstance(blk, dict):
                    inner = blk.get("text", {})
                    if isinstance(inner, dict):
                        text += "\n" + (inner.get("text") or "")
            gate.verify_slack(text=text, channel=kwargs.get("channel", ""))
        except ImportError as ie:
            # Log explicitly so silent bypass is visible in Railway logs.
            # The gate MUST be present in production — if this fires, investigate.
            print(f"[qa-gate] BYPASS WARNING: gate module unavailable ({ie}) — QA verification skipped")
        return self._raw.chat_postMessage(**kwargs)


client = _GatedSlackClient(_raw_client)

# ── Pending approval store ────────────────────────────────────────────────────
# Persists ts → metadata so the events endpoint can look up what to execute.
# Stored in memory/ (alongside pending_keyword_approvals.json) so it survives
# process restarts within a deploy. NOTE: Railway redeploys wipe the filesystem —
# if a redeploy happens between the nightly post (03:00) and the morning ✅,
# the file is lost and the reaction silently does nothing. Mitigation: avoid
# pushing to main between 03:00–08:00 Riyadh. Long-term fix: Railway Volume.

_PENDING_FILE = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "memory"))) / "pending_approvals.json"


def post_as_role(role: str, channel: str, text: str, **kwargs) -> dict | None:
    """
    Post a Slack message as the named agent role.

    Sets username + icon_emoji from AGENT_IDENTITY so every message
    shows which agent sent it — e.g. "Nexa · Campaign Manager" with :mega:.

    Usage:
        post_as_role("campaign_creator", SLACK_CHANNEL_APPROVAL, "My message")
        post_as_role("health_monitor",   SLACK_CHANNEL_NOTIFY,   "Connector down", thread_ts=ts)

    All extra kwargs are forwarded to chat_postMessage unchanged.
    Returns the full Slack API response dict, or None on failure.
    """
    from config import agent_identity
    identity = agent_identity(role)
    try:
        return client.chat_postMessage(
            channel=channel,
            text=text,
            username=identity["slack_name"],
            icon_emoji=identity["slack_emoji"],
            **kwargs,
        )
    except SlackApiError as e:
        print(f"[slack] post_as_role({role}) failed: {e}")
        return None


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
    window_days: int | None = None,
    channel_summary: list | None = None,
) -> str | None:
    """
    THE ONE #approvals message.

    Minimal format:
      Nexa · {date}  |  {dashboard_url}

      PERFORMANCE
      {channel}   ${spend}  ·  {leads} leads  ·  ${cpql} CPQL   {icon}

      ACTIONS  —  ✅ executes all  ·  ❌ skips all
      ↗  {campaign}   +{pct}% budget  (${old} → ${new})
      ⏸  {campaign}   pause           (${cpql} CPQL · {days}d)

      REVIEW ONLY  (Asana tasks created)
      ⚡  {flag}  —  {asana_url}

    ✅ = execute all scale + pause  ·  ❌ = skip all
    Returns the Slack message ts, or None on failure.
    """
    from notifications.quiet import is_quiet, quiet_log

    if not scale_findings and not pause_findings and not review_findings:
        return None

    if window_days is None:
        try:
            from config import DAYS_FOR_PAUSE_DECISION
            window_days = DAYS_FOR_PAUSE_DECISION
        except Exception:
            window_days = 14

    _now = datetime.now(timezone.utc)
    today_label = f"{_now.strftime('%b')} {_now.day}"

    # ── Dashboard URL ─────────────────────────────────────────────────────────
    try:
        from config import ACTIVITY_DEST_URL
        dash_url = ACTIVITY_DEST_URL
    except Exception:
        dash_url = "https://nexa-web-production-6a6b.up.railway.app/activity"

    lines = [f"*Nexa · {today_label}*  |  {dash_url}"]

    # ── PERFORMANCE block (one line per channel, sorted by spend desc) ────────
    _CPQL_SCALE   = 85    # below → ✅
    _CPQL_WARNING = 130   # above → 🔴, between → ⚠️

    if channel_summary:
        lines.append("\n*PERFORMANCE*")
        for ch in sorted(channel_summary, key=lambda x: x.get("spend", 0), reverse=True):
            name   = ch.get("channel", "?").title()
            spend  = ch.get("spend", 0)
            leads  = ch.get("leads", 0)
            cpql   = ch.get("cpql")
            if cpql is None:
                icon = "—"
            elif cpql < _CPQL_SCALE:
                icon = "✅"
            elif cpql < _CPQL_WARNING:
                icon = "⚠️"
            else:
                icon = "🔴"
            cpql_str = f"${cpql:.0f} CPQL" if cpql is not None else "no leads"
            lines.append(
                f"{name:<10}  ${spend:.0f}  ·  {leads} leads  ·  {cpql_str}   {icon}"
            )

    # ── ACTIONS block ─────────────────────────────────────────────────────────
    executable_findings = []
    action_lines = []

    for f in scale_findings:
        avg   = f.get("avg_spend")
        new_b = f.get("new_budget")
        budget_str = f"  (${avg:.0f} → ${new_b:.0f}/day)" if avg and new_b else ""
        action_lines.append(f"↗  `{f.get('campaign', '?')}`   +25% budget{budget_str}")
        executable_findings.append(f)

    for f in pause_findings:
        cpql    = f.get("cpql")
        cpql_str = f"${cpql:.0f} CPQL" if cpql is not None else "high CPQL"
        days_str = f"{window_days}d"
        action_lines.append(f"⏸  `{f.get('campaign', '?')}`   pause   ({cpql_str} · {days_str})")
        executable_findings.append(f)

    if action_lines:
        lines.append("\n*ACTIONS*  —  ✅ executes all  ·  ❌ skips all")
        lines.extend(action_lines)

    # ── REVIEW ONLY block ─────────────────────────────────────────────────────
    review_lines = []
    for f in review_findings:
        label = "Junk leads" if f.get("junk_leads") else f.get("action", "review").title()
        asana = f.get("asana_url", "")
        asana_part = f"  —  {asana}" if asana else ""
        review_lines.append(f"⚡  {label}: `{f.get('campaign', '?')}`{asana_part}")

    if review_lines:
        lines.append("\n*REVIEW ONLY*  (Asana tasks created)")
        lines.extend(review_lines)

    full_text = "\n".join(lines)

    if is_quiet():
        quiet_log("nightly-approvals-digest", SLACK_CHANNEL_APPROVAL, full_text)
        return None

    try:
        response = post_as_role(
            "performance_audit", SLACK_CHANNEL_APPROVAL, full_text
        ) or {}
        ts = response.get("ts", "")
        if not ts:
            return None
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
                }
                for f in executable_findings
            ],
        })
        try:
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="daily_digest",
                action="posted_approvals_digest",
                status="success",
                details={
                    "scale":  len(scale_findings),
                    "pause":  len(pause_findings),
                    "review": len(review_findings),
                    "ts":     ts,
                    "format": "minimal_v2",
                },
            )
        except Exception:
            pass
        return ts
    except SlackApiError as e:
        print(f"[slack] post_nightly_approvals_digest failed: {e}")
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
        # Do NOT pre-add reactions — if the bot adds white_check_mark, check_approval()
        # immediately sees it and auto-executes. A human must add the reaction manually.
        # (Removed 2026-05-25 after agent-weekly auto-executed a pause without human approval.)

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
