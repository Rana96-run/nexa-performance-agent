"""
Entry point for the Qoyod Performance Agent.

Usage:
    python main.py                 # defaults to daily
    python main.py daily
    python main.py weekly
    python main.py monthly
    python main.py quarterly
    python main.py on_demand

Flow:
    1. Collect data (scoped per cadence)
    2. Manager routes to role agents (claude/manager.py)
    3. For each role result:
         - always create Asana task
         - channel mutations -> Slack approval -> execute
         - everything else  -> Slack summary
"""
import bootstrap  # noqa: F401  -- materializes GOOGLE creds from env if needed
import sys
from datetime import date
from collectors.google_ads import get_campaign_performance, get_keyword_performance
from collectors.meta import get_ad_performance
from collectors.hubspot import get_sql_count
from claude.manager import run_trigger
from notifications.approval import wait_for_approval
from notifications.notify import send_summary, send_approval_request
from config import NOTIFY_VIA
from executors import google_ads as gads_exec
from executors import meta as meta_exec
from executors.asana import create_task


CADENCE_DAYS = {
    "daily": 4,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "on_demand": 4,
}


def collect(cadence: str) -> dict:
    days = CADENCE_DAYS.get(cadence, 4)
    print(f"[collect] pulling data for {cadence} ({days}d)")
    return {
        "date": str(date.today()),
        "cadence": cadence,
        "google_ads": {
            "campaigns": get_campaign_performance(days=days),
            "keywords":  get_keyword_performance(days=max(days, 14)),
        },
        "meta":    {"ads": get_ad_performance(days=days)},
        "hubspot": get_sql_count(days=days),
    }


def run_cadence(cadence: str):
    today = str(date.today())
    print(f"[{today}] === {cadence.upper()} cadence ===")

    data = collect(cadence)
    results = run_trigger(cadence, data)

    for res in results:
        handle_role_result(cadence, res)

    print(f"[{today}] {cadence} cadence complete.")


def handle_role_result(cadence: str, res: dict):
    role = res["role"]
    decision = res.get("decision") or {}
    action = (decision.get("action") or "").lower()
    print(f"[{role}] action={action!r} confidence={decision.get('confidence')}")

    # 1) Always create an Asana task
    project_key_map = {
        "Daily Activity": "daily_activity",
        "Optimization": "optimization",
        "Campaigns Performance Hub": "campaigns_hub",
        "Seasonal Campaigns": "seasonal",
    }
    project_key = project_key_map.get(
        decision.get("asana_project", "Daily Activity"), "daily_activity"
    )
    create_task(
        title=f"[{cadence}/{role}] {decision.get('channel', '')} -- {decision.get('decision', '')}",
        description=(
            f"KPI: {decision.get('kpi')} = {decision.get('value')}\n"
            f"Threshold: {decision.get('threshold')}\n"
            f"Reason: {decision.get('reason')}\n"
            f"Confidence: {decision.get('confidence')}\n"
            f"Notes: {decision.get('notes')}"
        ),
        project_key=project_key,
        task_type=decision.get("asana_task_type", "Recommendation"),
    )

    # 2) Slack
    channel_actions = ("pause", "exclude", "adjust", "scale", "pause-and-replace")
    if action in channel_actions:
        print(f"[{role}] channel action -- requesting approval via {NOTIFY_VIA}")
        result = send_approval_request(res)
        ts = result.get("slack_ts")
        if ts:
            approval = wait_for_approval(ts, timeout_minutes=60)
            print(f"[{role}] approval: {approval}")
            if approval == "approved":
                execute_channel_action(decision)
        else:
            # Email-only path: auto-execution disabled; approve via Asana task.
            print(f"[{role}] no Slack ts -- skipping auto-exec, manual approval via Asana.")
    else:
        post_summary(cadence, res)


def execute_channel_action(decision: dict):
    action = (decision.get("action") or "").lower()
    channel = (decision.get("channel") or "").lower()
    entity = (decision.get("entity") or "").lower()

    if action.startswith("pause"):
        if "google" in channel:
            resource = decision.get("notes", "")
            if "keyword" in entity and resource:
                gads_exec.pause_keyword(resource)
            elif "ad" in entity and resource:
                gads_exec.pause_ad(resource)
        elif "meta" in channel:
            ad_id = decision.get("notes", "")
            if ad_id:
                meta_exec.pause_ad(ad_id)


def post_summary(cadence: str, res: dict):
    decision = res.get("decision") or {}
    subject = f"{cadence.title()} check — {res['role']}"
    body = (
        f"Channel: {decision.get('channel', 'N/A')}\n"
        f"Finding: {decision.get('reason', 'N/A')}\n"
        f"Recommendation: {decision.get('decision', 'N/A')}\n"
        f"Confidence: {decision.get('confidence', 'N/A')}"
    )
    event_map = {"daily": "daily_summary", "weekly": "weekly_review",
                 "monthly": "monthly_review", "quarterly": "monthly_review",
                 "on_demand": "daily_summary"}
    send_summary(subject, body, event_type=event_map.get(cadence, "daily_summary"),
                 meta={"Role": res["role"], "Cadence": cadence,
                       "Confidence": decision.get("confidence", "N/A")})


if __name__ == "__main__":
    cadence = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cadence not in CADENCE_DAYS:
        sys.exit(f"Unknown cadence: {cadence}. Use one of {list(CADENCE_DAYS)}")
    run_cadence(cadence)
