#!/usr/bin/env python3
"""
Slack MCP Server for Nexa Performance Agent.

Exposes the project's custom Slack app as MCP tools so Claude / Cowork agents
can post messages, reply to threads, add reactions, and read channel history —
using the bot token already stored in the local .env / Railway vars.

Transport : stdio (local Cowork plugin)
Auth      : SLACK_BOT_TOKEN env var (xoxb-... token from the custom Slack app)
"""

from __future__ import annotations

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
mcp = FastMCP("slack_mcp")

# ---------------------------------------------------------------------------
# Config — read from env vars injected by installer / Railway
# ---------------------------------------------------------------------------
_BOT_TOKEN       = os.getenv("SLACK_BOT_TOKEN", "")
_CHANNEL_HEALTH  = os.getenv("SLACK_CHANNEL_HEALTH", "")
_CHANNEL_APPROVAL = os.getenv("SLACK_CHANNEL_APPROVAL", "")
_CHANNEL_NOTIFY  = os.getenv("SLACK_CHANNEL_NOTIFY", "")

_SLACK_API = "https://slack.com/api"


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------
async def _slack_post(endpoint: str, payload: dict) -> dict:
    """POST to a Slack API endpoint and return parsed JSON."""
    if not _BOT_TOKEN:
        raise RuntimeError(
            "SLACK_BOT_TOKEN is not set. Run the installer or set the env var."
        )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_SLACK_API}/{endpoint}",
            headers={
                "Authorization": f"Bearer {_BOT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def _slack_get(endpoint: str, params: dict) -> dict:
    """GET from a Slack API endpoint and return parsed JSON."""
    if not _BOT_TOKEN:
        raise RuntimeError(
            "SLACK_BOT_TOKEN is not set. Run the installer or set the env var."
        )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_SLACK_API}/{endpoint}",
            headers={"Authorization": f"Bearer {_BOT_TOKEN}"},
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


def _check_ok(data: dict) -> str | None:
    """Return None if ok=True, else a formatted error string."""
    if not data.get("ok"):
        error = data.get("error", "unknown_error")
        detail = data.get("response_metadata", {})
        return f"Error: Slack API returned ok=false — {error}. Detail: {detail}"
    return None


def _resolve_channel(channel: str) -> str:
    """
    Accept a channel ID (C...), channel name (#general), or one of the
    named shortcuts: 'health', 'approval', 'notify'.
    Returns the raw channel ID/name to pass to the Slack API.
    """
    shortcuts = {
        "health":   _CHANNEL_HEALTH,
        "approval": _CHANNEL_APPROVAL,
        "notify":   _CHANNEL_NOTIFY,
    }
    return shortcuts.get(channel.lower().lstrip("#"), channel)


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------
class PostMessageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    channel: str = Field(
        ...,
        description=(
            "Channel to post to. Accepts a channel ID (e.g. 'C0ARMQKK8GK'), "
            "channel name (e.g. '#general'), or a named shortcut: "
            "'health' (SLACK_CHANNEL_HEALTH), "
            "'approval' (SLACK_CHANNEL_APPROVAL), "
            "'notify' (SLACK_CHANNEL_NOTIFY)."
        ),
        min_length=1,
    )
    text: str = Field(
        ...,
        description=(
            "Message text. Supports Slack mrkdwn formatting: "
            "*bold*, _italic_, `code`, ```block```, >quote, "
            "and <URL|label> for links. Keep under 40 000 chars."
        ),
        min_length=1,
        max_length=40_000,
    )
    unfurl_links: Optional[bool] = Field(
        default=False,
        description="Whether Slack should unfurl links in the message. Default False.",
    )


class ReplyToThreadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    channel: str = Field(
        ...,
        description="Channel ID or shortcut (same as post_message).",
        min_length=1,
    )
    thread_ts: str = Field(
        ...,
        description=(
            "Timestamp of the parent message to reply to "
            "(e.g. '1715000000.123456'). Found in the 'ts' field of messages."
        ),
        min_length=1,
    )
    text: str = Field(
        ...,
        description="Reply text. Supports Slack mrkdwn formatting.",
        min_length=1,
        max_length=40_000,
    )


class AddReactionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    channel: str = Field(
        ...,
        description="Channel ID or shortcut where the message lives.",
        min_length=1,
    )
    timestamp: str = Field(
        ...,
        description="Message timestamp (ts) to react to (e.g. '1715000000.123456').",
        min_length=1,
    )
    emoji: str = Field(
        ...,
        description=(
            "Emoji name WITHOUT colons (e.g. 'white_check_mark', 'x', 'eyes'). "
            "Must be a valid Slack emoji name."
        ),
        min_length=1,
        max_length=100,
    )


class GetChannelHistoryInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    channel: str = Field(
        ...,
        description="Channel ID or shortcut to read from.",
        min_length=1,
    )
    limit: Optional[int] = Field(
        default=20,
        description="Number of messages to return (1–100). Default 20.",
        ge=1,
        le=100,
    )
    oldest: Optional[str] = Field(
        default=None,
        description=(
            "Only return messages after this Unix timestamp (e.g. '1715000000'). "
            "Useful for reading messages since a specific time."
        ),
    )


class GetThreadRepliesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    channel: str = Field(
        ...,
        description="Channel ID or shortcut where the thread lives.",
        min_length=1,
    )
    thread_ts: str = Field(
        ...,
        description="Timestamp of the parent message (e.g. '1715000000.123456').",
        min_length=1,
    )
    limit: Optional[int] = Field(
        default=50,
        description="Max replies to return (1–200). Default 50.",
        ge=1,
        le=200,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="slack_post_message",
    annotations={
        "title": "Post Slack Message",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def slack_post_message(params: PostMessageInput) -> str:
    """
    Post a new message to a Slack channel using the project's custom Slack app.

    Use this to send anomaly alerts, daily digests, approval requests, or any
    other notification. Supports full Slack mrkdwn formatting.

    Named channel shortcuts (configured via env vars):
      - 'health'   → SLACK_CHANNEL_HEALTH   (anomaly alerts, health pings)
      - 'approval' → SLACK_CHANNEL_APPROVAL (approval requests with ✅/❌)
      - 'notify'   → SLACK_CHANNEL_NOTIFY   (general notifications)

    Args:
        params (PostMessageInput):
            - channel (str): Channel ID, name, or shortcut ('health'/'approval'/'notify').
            - text (str): Message content with optional mrkdwn formatting.
            - unfurl_links (bool): Whether to unfurl URLs. Default False.

    Returns:
        str: JSON with 'ts' (message timestamp) and 'channel' on success.
             'ts' can be used later to reply to this message as a thread.
             On error returns "Error: ...".

    Examples:
        - Post anomaly alert → channel='health', text='🚨 *Anomaly detected...*'
        - Post approval request → channel='approval', text='...'
        - Reply to a specific message → use slack_reply_to_thread with the returned 'ts'
    """
    try:
        channel = _resolve_channel(params.channel)
        data = await _slack_post("chat.postMessage", {
            "channel":      channel,
            "text":         params.text,
            "unfurl_links": params.unfurl_links,
        })
        if err := _check_ok(data):
            return err
        return json.dumps({
            "ok":      True,
            "ts":      data.get("ts"),
            "channel": data.get("channel"),
        })
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(
    name="slack_reply_to_thread",
    annotations={
        "title": "Reply to Slack Thread",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def slack_reply_to_thread(params: ReplyToThreadInput) -> str:
    """
    Post a reply inside an existing Slack thread.

    Use this to add follow-up information to an existing message — for example,
    posting recommendations as a reply to a main daily digest message.

    Args:
        params (ReplyToThreadInput):
            - channel (str): Channel ID or shortcut where the thread lives.
            - thread_ts (str): The 'ts' of the parent message to reply to.
            - text (str): Reply content with optional mrkdwn formatting.

    Returns:
        str: JSON with 'ts' of the reply on success. On error returns "Error: ...".
    """
    try:
        channel = _resolve_channel(params.channel)
        data = await _slack_post("chat.postMessage", {
            "channel":   channel,
            "text":      params.text,
            "thread_ts": params.thread_ts,
        })
        if err := _check_ok(data):
            return err
        return json.dumps({
            "ok":      True,
            "ts":      data.get("ts"),
            "channel": data.get("channel"),
        })
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(
    name="slack_add_reaction",
    annotations={
        "title": "Add Slack Reaction",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def slack_add_reaction(params: AddReactionInput) -> str:
    """
    Add an emoji reaction to a Slack message.

    Use this after reading the approval channel to acknowledge a message,
    or to mark a digest as seen.

    Args:
        params (AddReactionInput):
            - channel (str): Channel ID or shortcut where the message lives.
            - timestamp (str): The 'ts' of the message to react to.
            - emoji (str): Emoji name without colons (e.g. 'white_check_mark', 'x').

    Returns:
        str: '{"ok": true}' on success. On error returns "Error: ...".
    """
    try:
        channel = _resolve_channel(params.channel)
        data = await _slack_post("reactions.add", {
            "channel":   channel,
            "timestamp": params.timestamp,
            "name":      params.emoji,
        })
        if err := _check_ok(data):
            # already_reacted is harmless — treat as success
            if "already_reacted" in str(data.get("error", "")):
                return json.dumps({"ok": True, "note": "already_reacted"})
            return err
        return json.dumps({"ok": True})
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(
    name="slack_get_channel_history",
    annotations={
        "title": "Get Slack Channel History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def slack_get_channel_history(params: GetChannelHistoryInput) -> str:
    """
    Fetch recent messages from a Slack channel.

    Use this to check what was posted in the approval channel, read the latest
    digest, or look for ✅/❌ reactions on approval messages.

    Args:
        params (GetChannelHistoryInput):
            - channel (str): Channel ID or shortcut to read from.
            - limit (int): Number of messages to return (1–100). Default 20.
            - oldest (str, optional): Only return messages after this Unix timestamp.

    Returns:
        str: JSON array of message objects, each with:
             - ts (str): Message timestamp (use as thread_ts to reply)
             - user (str): User ID of the sender
             - text (str): Message text
             - reactions (list): Reactions on this message (name + count)
             - reply_count (int): Number of thread replies
        On error returns "Error: ...".
    """
    try:
        channel = _resolve_channel(params.channel)
        query: dict = {"channel": channel, "limit": params.limit}
        if params.oldest:
            query["oldest"] = params.oldest

        data = await _slack_get("conversations.history", query)
        if err := _check_ok(data):
            return err

        messages = [
            {
                "ts":          m.get("ts"),
                "user":        m.get("user", m.get("bot_id", "unknown")),
                "text":        m.get("text", ""),
                "reactions":   [
                    {"name": r["name"], "count": r["count"]}
                    for r in m.get("reactions", [])
                ],
                "reply_count": m.get("reply_count", 0),
            }
            for m in data.get("messages", [])
        ]
        return json.dumps({
            "channel":    channel,
            "count":      len(messages),
            "has_more":   data.get("has_more", False),
            "messages":   messages,
        }, indent=2)
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


@mcp.tool(
    name="slack_get_thread_replies",
    annotations={
        "title": "Get Slack Thread Replies",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def slack_get_thread_replies(params: GetThreadRepliesInput) -> str:
    """
    Fetch all replies in a Slack thread.

    Use this to read the full conversation in an approval thread, or to check
    if a ✅ or ❌ reaction/reply was made on a specific digest message.

    Args:
        params (GetThreadRepliesInput):
            - channel (str): Channel ID or shortcut where the thread lives.
            - thread_ts (str): Timestamp of the parent message.
            - limit (int): Max replies to return (1–200). Default 50.

    Returns:
        str: JSON array of reply objects (same schema as get_channel_history messages).
             The first item is always the parent message.
        On error returns "Error: ...".
    """
    try:
        channel = _resolve_channel(params.channel)
        data = await _slack_get("conversations.replies", {
            "channel":   channel,
            "ts":        params.thread_ts,
            "limit":     params.limit,
        })
        if err := _check_ok(data):
            return err

        messages = [
            {
                "ts":        m.get("ts"),
                "user":      m.get("user", m.get("bot_id", "unknown")),
                "text":      m.get("text", ""),
                "reactions": [
                    {"name": r["name"], "count": r["count"]}
                    for r in m.get("reactions", [])
                ],
            }
            for m in data.get("messages", [])
        ]
        return json.dumps({
            "thread_ts": params.thread_ts,
            "count":     len(messages),
            "has_more":  data.get("has_more", False),
            "messages":  messages,
        }, indent=2)
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()  # stdio transport
