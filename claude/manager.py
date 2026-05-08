"""
Manager: routes a trigger (daily/weekly/monthly/quarterly/on_demand) to the
right set of role agents, invokes each with its own system prompt, and returns
a list of per-role decisions for the orchestrator to act on.
"""
import anthropic
import json
import re
import time
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from claude.roles import load_prompt, roles_for_trigger
from logs.activity_logger import log_activity_async
from executors.cost_tracking import extract_anthropic_usage, llm_cost_usd


def run_role(role: str, trigger: str, data: dict) -> dict:
    """Invoke a single role agent and return its structured decision.

    Logs Anthropic token usage + USD cost to agent_activity_log under
    role='llm_cadence', action='llm_role_ran'. Tracking is silent on failure
    so the role still returns its decision even if logging breaks.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_prompt(role)

    # Append a short summary of role-relevant Drive assets so Claude can
    # reference them by name (creative briefs, brand guidelines, campaign
    # asset folders, etc.).  Indexed nightly by analysers.drive_knowledge.
    try:
        from analysers.drive_knowledge import summarise_for_role
        drive_section = summarise_for_role(role)
        if drive_section:
            system_prompt = system_prompt + "\n\n---\n\n" + drive_section
    except Exception as e:
        print(f"[manager] drive context skipped for {role}: {e}")

    user_message = (
        f"Trigger: {trigger}\n"
        f"Date: {data.get('date')}\n\n"
        f"Run your role's decision framework against this data. "
        f"Return Summary, Slack Draft, Asana Task Draft (if needed), and JSON.\n\n"
        f"Performance data:\n{json.dumps(data, indent=2, default=str)}"
    )

    t0 = time.time()
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    duration_s = time.time() - t0

    # ── Log token consumption ────────────────────────────────────────────────
    tokens_in, tokens_out = extract_anthropic_usage(message)
    cost = llm_cost_usd(tokens_in, tokens_out)
    try:
        log_activity_async(
            role="llm_cadence",
            action="llm_role_ran",
            status="success",
            details={"role_invoked": role, "trigger": trigger, "model": CLAUDE_MODEL},
            duration_s=duration_s,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
    except Exception:
        pass  # never let logging break the role

    raw = message.content[0].text
    return {"role": role, "raw_response": raw, "decision": _extract_json(raw)}


def run_trigger(trigger: str, data: dict) -> list:
    """Invoke every role routed to this trigger. Returns list of role results."""
    roles = roles_for_trigger(trigger)
    if not roles:
        print(f"[manager] No roles configured for trigger '{trigger}'")
        return []

    results = []
    for role in roles:
        print(f"[manager] invoking role: {role}")
        try:
            results.append(run_role(role, trigger, data))
        except Exception as e:
            print(f"[manager] role {role} failed: {e}")
    return results


def _extract_json(text: str) -> dict:
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}
