"""
notifications/quiet.py
======================
Single kill-switch for ALL Slack output across the agent.

Set env var `NEXA_QUIET=true` to mute every channel poster (daily summary,
report-ready ping, spike alerts, heartbeats, approval requests, webhook
alerts, health checks, Zap diagnoses).  Used during debugging or backfills
so the team doesn't get spammed with stale numbers.

Set NEXA_QUIET=false (or remove the var) to resume normal posting.

Every direct Slack poster MUST gate on `is_quiet()` before calling
`chat_postMessage` — otherwise stale-data spam leaks out during dev work.
"""
from __future__ import annotations

import os
import functools


def is_quiet() -> bool:
    return os.getenv("NEXA_QUIET", "").lower() in ("true", "1", "yes", "on")


def quiet_log(prefix: str, target: str, body: str = "") -> None:
    """Print what would have been posted, when quiet mode is on."""
    snippet = body.replace("\n", " ")[:120]
    print(f"[{prefix}] QUIET — skipped Slack post to {target}: {snippet}")
