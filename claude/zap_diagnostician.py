"""
claude/zap_diagnostician.py
============================
Uses Claude API to diagnose Zapier failures and generate ACTIONABLE fix steps.

Called by zapier_webhook when a run can't be auto-replayed (transient retry
already failed). Returns a structured diagnosis: root cause + step-by-step
fix instructions tailored to the specific error.

Output shape:
    {
        "category":   "auth" | "data_format" | "api_rate" | "logic" | "config" | "unknown",
        "severity":   "critical" | "warning" | "info",
        "root_cause": "<one-sentence summary>",
        "broken_step": "<step name or number, or 'unknown'>",
        "fix_steps":  ["1. Open Zap...", "2. Click step 3 'Send Email'...", ...],
        "auto_fixable": true | false,    # can our agent take action?
        "auto_action": "turn_off" | "skip_run" | None,
    }
"""
from __future__ import annotations

import json
import re
from typing import Optional

import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


_DIAGNOSIS_PROMPT = """\
You are a senior Zapier engineer diagnosing a failed Zap. You have decades \
of experience and have seen every error pattern. Your job is to give the \
user a specific, actionable fix — not a generic "check your Zap".

The Zap details:
- Zap name: {zap_name}
- Run URL: {run_url}
- Error message: {error_message}
- Replay attempts already made: {replay_attempts}

Return ONLY valid JSON in this exact shape:
{{
  "category": "auth | data_format | api_rate | logic | config | unknown",
  "severity": "critical | warning | info",
  "root_cause": "<one sentence describing the actual problem>",
  "broken_step": "<which step failed — use the step name from the error if mentioned, else 'unknown'>",
  "fix_steps": [
    "<concrete step 1, including exact menu paths, field names, expected values>",
    "<concrete step 2>",
    "..."
  ],
  "auto_fixable": <true if we should disable the Zap to stop further failures, else false>,
  "auto_action": "turn_off" | "skip_run" | null
}}

Rules:
- fix_steps MUST be concrete actions a non-engineer can follow (e.g. "Open the Zap, click step 3 'Format Date', change Input to {{step1__date}} ISO 8601").
- If the error is auth-related (token expired, OAuth disconnect), say so explicitly and tell them which app to reconnect.
- If it's a data format issue, name the exact field and show what value is wrong vs what's expected.
- If it's an upstream API outage (5xx, "service unavailable"), set category="api_rate", severity="info", auto_action=null — replay later.
- If you can't tell from the error message, set category="unknown" and ask for the run details URL.
- DO NOT include any text outside the JSON. No markdown, no commentary.
"""


def _extract_json(text: str) -> Optional[dict]:
    """Extract the first JSON object from text, tolerating leading/trailing junk."""
    # Strip code fences if Claude returned markdown despite instructions
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: greedy match the outer braces
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def diagnose(
    zap_name: str,
    error_message: str,
    run_url: str = "",
    replay_attempts: int = 0,
) -> dict:
    """
    Run a single Claude call to diagnose a Zap failure.
    Falls back to a generic diagnosis if Claude is unavailable or returns junk.
    """
    fallback = {
        "category": "unknown",
        "severity": "warning",
        "root_cause": (error_message or "Unknown failure")[:200],
        "broken_step": "unknown",
        "fix_steps": [
            f"Open the Zap run: {run_url or '(URL not provided)'}",
            "Identify which step failed and read the error in detail",
            "Fix the failing field/connection in that step",
            "Test the step, then re-enable the Zap",
        ],
        "auto_fixable": False,
        "auto_action": None,
    }

    if not ANTHROPIC_API_KEY:
        print("[zap-diag] ANTHROPIC_API_KEY not set — using fallback")
        return fallback

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = _DIAGNOSIS_PROMPT.format(
            zap_name=zap_name or "(no name)",
            run_url=run_url or "(no URL)",
            error_message=(error_message or "(empty)")[:1500],
            replay_attempts=replay_attempts,
        )
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""
        parsed = _extract_json(text)
        if not parsed:
            print(f"[zap-diag] Failed to parse Claude output, using fallback. Raw: {text[:200]}")
            return fallback
        # Light validation: ensure the keys we rely on exist
        for k in ("category", "severity", "root_cause", "fix_steps", "auto_fixable"):
            parsed.setdefault(k, fallback[k])
        parsed.setdefault("broken_step", "unknown")
        parsed.setdefault("auto_action", None)
        return parsed
    except Exception as e:
        print(f"[zap-diag] Claude call failed: {e}")
        return fallback


def format_for_slack(diag: dict, zap_name: str, run_url: str) -> tuple[list, str]:
    """Build Slack blocks + fallback text from a diagnosis dict."""
    sev_emoji = {"critical": ":rotating_light:", "warning": ":warning:", "info": ":information_source:"}
    cat_emoji = {
        "auth": ":lock:", "data_format": ":input_numbers:", "api_rate": ":hourglass:",
        "logic": ":brain:", "config": ":wrench:", "unknown": ":grey_question:",
    }
    sev = diag.get("severity", "warning")
    cat = diag.get("category", "unknown")
    icon = sev_emoji.get(sev, ":warning:")
    cat_icon = cat_emoji.get(cat, ":grey_question:")

    fix_steps = diag.get("fix_steps") or []
    steps_md = "\n".join(f"  • {s}" for s in fix_steps[:8])

    broken = diag.get("broken_step", "unknown")
    if broken and broken != "unknown":
        broken_md = f"*Broken step:* `{broken}`\n"
    else:
        broken_md = ""

    link = f"<{run_url}|Open the failed run>" if run_url else ""

    text = (
        f"{icon} *Zap broken — {zap_name}*  {cat_icon} `{cat}`\n"
        f"*Root cause:* {diag.get('root_cause', '?')}\n"
        f"{broken_md}"
        f"*How to fix:*\n{steps_md}\n"
        f"{link}"
    )

    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }]
    return blocks, f"Zap broken — {zap_name}: {diag.get('root_cause', '?')[:80]}"
