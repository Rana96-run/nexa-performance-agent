"""Slack ping — the ONLY way bot messages should leave the system.

Design rule (confirmed 2026-05-18): Slack is a REMINDER, never a content channel.
Every bot post = 1 line + dashboard URL. All detail lives in BQ / Hex / Asana.

NEVER:
  - Inline tables (```...``` blocks with rows of data)
  - Multi-paragraph bodies
  - "Check: scheduler running? recent syncs? views materialized?" debugging questions
  - Numbered investigation steps
  - Raw JSON / dict dumps

ALWAYS:
  - One-line headline starting with an emoji status (✅ ⚠️ 🚨 ℹ️)
  - Followed by the dashboard URL (or Asana URL, or wherever the detail lives)
  - That's it.

Good:
  ⚠️ BQ↔HubSpot drift detected (May 14–16). See dashboard → https://...
  🚨 9 social campaigns have ad-level pause candidates. See Asana → https://...
  ✅ Daily reconciliation passed.

Bad:
  🚨 BQ ↔ HubSpot daily check — 2026-05-18
  Drift detected (>5.0% AND >5 leads).
  ```
  date            BQ    HS   diff      %
  ...
  ```
  Check: scheduler running? ...
"""
from __future__ import annotations
import os
from typing import Literal

# Status icons
ICON = {
    "ok":      "✅",
    "info":    "ℹ️",
    "warn":    "⚠️",
    "alert":   "🚨",
}

# Default destinations — most pings go to the dashboard
def _dashboard_url() -> str:
    return os.getenv("ACTIVITY_DASHBOARD_URL", "https://nexa-web-production-6a6b.up.railway.app/")


def post_ping(channel: str, status: Literal["ok", "info", "warn", "alert"],
              headline: str, link: str | None = None) -> bool:
    """Post a single-line ping to Slack.

    Args:
        channel:  Slack channel ID or #name
        status:   one of ok|info|warn|alert (sets the emoji)
        headline: ONE short sentence — NEVER multi-line. No data tables. No JSON.
                  Soft cap: 120 chars. Anything longer goes to the dashboard.
        link:     URL where the detail lives. Defaults to ACTIVITY_DASHBOARD_URL.

    Returns True on success.
    """
    if not channel:
        print(f"[ping] no channel — skipping: {headline[:60]}")
        return False
    if "\n" in headline:
        # Hard rule: pings are one line. Collapse newlines silently rather than crash.
        headline = headline.replace("\n", " ").strip()
    if len(headline) > 240:
        # Defensive trim
        headline = headline[:235] + " …"

    text = f"{ICON.get(status, 'ℹ️')} {headline} → {link or _dashboard_url()}"

    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN
        WebClient(token=SLACK_BOT_TOKEN).chat_postMessage(
            channel=channel, text=text, unfurl_links=False, unfurl_media=False,
        )
        return True
    except Exception as e:
        print(f"[ping] post failed: {e}")
        return False
