import re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL


client = WebClient(token=SLACK_BOT_TOKEN)


def post_approval_request(analysis: dict) -> str:
    """
    Post Claude's decisions to Slack for approval.
    Returns the message timestamp (ts) to track approval reaction.
    """
    decision = analysis.get("decision", {})
    raw = analysis.get("raw_response", "")

    # Extract the Slack draft from Claude's raw response
    slack_section = extract_slack_draft(raw)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Daily Performance Check -- Approval Required*\n\n{slack_section}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Action proposed:* `{decision.get('action', 'N/A')}`\n"
                        f"*Channel:* {decision.get('channel', 'N/A')}\n"
                        f"*Campaign:* {decision.get('campaign', 'N/A')}\n"
                        f"*KPI:* {decision.get('kpi', 'N/A')} = {decision.get('value', 'N/A')}\n"
                        f"*Confidence:* {decision.get('confidence', 'N/A')}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "React with check mark to *approve* this action, or X to *reject* it.\n"
                        "_No action will be taken until you respond._"
            }
        }
    ]

    try:
        response = client.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            blocks=blocks,
            text="Daily performance check -- approval required"
        )
        return response["ts"]  # message timestamp = approval tracking ID
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
