"""
Entry point for Nexa — Qoyod Performance Agent.

Usage:
    python main.py                 # defaults to daily
    python main.py daily
    python main.py weekly
    python main.py monthly
    python main.py quarterly
    python main.py on_demand       # skip analysis guard — always runs
    python main.py on_demand --bust  # also wipes data cache first
    python main.py status

Flow:
    1. Guard  — skip if this cadence already ran today (unless on_demand)
    2. Collect — pull data from ALL channels; served from cache if fresh (< 22h)
    3. Analyse — Nexa roles run via Claude API (media_buyer, paid_media_analyst, paid_media_strategist)
    4. Batch  — collect ALL Asana tasks from ALL roles, create them in one go
    5. Slack  — post ONE combined summary to notify channel
    6. Approve — channel mutations go to approval channel; wait for ✅/❌ reaction
    7. Mark   — record cadence as complete so scheduler doesn't double-fire

Channels in analysis: Google Ads · Meta · Snapchat · LinkedIn · Microsoft Ads · HubSpot
"""
from scripts import bootstrap  # noqa: F401  -- materializes GOOGLE creds from env if needed
import sys
from datetime import date
from logs.logger import get_logger, setup_global_logging

setup_global_logging("main")  # captures every print() into logs/nexa_YYYY-MM-DD.log
log = get_logger("main")

from cache.cache_manager import (
    can_run_analysis, mark_analysis_done,
    get_or_fetch, bust_all, cache_status,
)
from collectors.google_ads import get_keyword_performance  # keyword grain (not in BQ)
from collectors.meta import get_ad_performance              # ad grain (not in BQ)
from collectors.hubspot import get_sql_count
from collectors.from_bq import read_campaigns               # campaign grain (single source of truth)
from claude.manager import run_trigger
from notifications.approval import wait_for_approval
from notifications.notify import send_summary, send_approval_request
from config import NOTIFY_VIA, SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL
from executors import google_ads as gads_exec
from executors import meta as meta_exec
from executors.asana import create_task, ensure_channel_sections


CADENCE_DAYS = {
    "daily":     4,
    "weekly":    7,
    "monthly":   30,
    "quarterly": 90,
    "on_demand": 4,
}

PROJECT_KEY_MAP = {
    "Daily Activity":            "daily_activity",
    "Optimization":              "optimization",
    "Campaigns Performance Hub": "campaigns_hub",
    "Seasonal Campaigns":        "seasonal",
}

CADENCE_EMOJI = {
    "daily":     "📊",
    "weekly":    "📈",
    "monthly":   "📅",
    "quarterly": "🏦",
    "on_demand": "⚡",
}


# ---------------------------------------------------------------------------
# Data collection (cached)
# ---------------------------------------------------------------------------

def collect(cadence: str) -> dict:
    days    = CADENCE_DAYS.get(cadence, 4)
    kw_days = max(days, 14)
    print(f"[collect] cadence={cadence}  window={days}d  kw={kw_days}d")
    print(f"[collect] channels: Google Ads · Meta · Snapchat · LinkedIn · Microsoft Ads · HubSpot")

    return {
        "date":    str(date.today()),
        "cadence": cadence,
        # ── Paid channels ────────────────────────────────────────────────────
        # Campaign-level data comes from BigQuery (populated 4×/day by the
        # *_bq.py writers). One source of truth — agent + dashboard agree.
        "google_ads": {
            "campaigns": get_or_fetch(
                f"gads_campaigns_{days}d",
                lambda: read_campaigns("google_ads", days=days),
            ),
            "keywords": get_or_fetch(
                f"gads_keywords_{kw_days}d",
                lambda: get_keyword_performance(days=kw_days),  # live API — BQ has no keyword grain
            ),
        },
        "meta": {
            "ads": get_or_fetch(
                f"meta_ads_{days}d",
                lambda: get_ad_performance(days=days),  # live API — BQ has no ad grain yet
            ),
        },
        "snapchat": {
            "campaigns": get_or_fetch(
                f"snap_campaigns_{days}d",
                lambda: read_campaigns("snapchat", days=days),
            ),
        },
        "linkedin": {
            "campaigns": get_or_fetch(
                f"li_campaigns_{days}d",
                lambda: read_campaigns("linkedin", days=days),
            ),
        },
        "microsoft_ads": {
            "campaigns": get_or_fetch(
                f"ms_campaigns_{days}d",
                lambda: read_campaigns("microsoft_ads", days=days),
            ),
        },
        "tiktok": {
            "campaigns": get_or_fetch(
                f"tiktok_campaigns_{days}d",
                lambda: read_campaigns("tiktok", days=days),
            ),
        },
        # ── CRM ──────────────────────────────────────────────────────────────
        "hubspot": get_or_fetch(
            f"hubspot_sql_{days}d",
            lambda: get_sql_count(days=days),
        ),
    }


# ---------------------------------------------------------------------------
# Task extraction helpers
# ---------------------------------------------------------------------------

def _build_task_description(decision: dict, raw_response: str, cadence: str, role: str) -> str:
    """Build a rich Asana task description from Claude's full response."""
    lines = [
        f"Cadence: {cadence.title()} | Role: {role}",
        f"Date: {date.today()}",
        "",
        f"Channel: {decision.get('channel', 'N/A')}",
        f"Campaign/Asset: {decision.get('campaign', 'N/A')}",
        f"Entity: {decision.get('entity', 'N/A')}",
        "",
        f"KPI: {decision.get('kpi', 'N/A')} = {decision.get('value', 'N/A')}",
        f"Threshold: {decision.get('threshold', 'N/A')}",
        f"Confidence: {decision.get('confidence', 'N/A')}",
        "",
        f"Finding: {decision.get('reason', 'N/A')}",
        f"Decision: {decision.get('decision', 'N/A')}",
        f"Action: {decision.get('action', 'N/A')}",
        "",
        f"Notes: {decision.get('notes', 'N/A')}",
        f"Priority: {decision.get('priority', 'N/A')}",
    ]

    # Attach Claude's full analysis excerpt (first 800 chars after stripping JSON block)
    import re
    clean = re.sub(r"```json.*?```", "", raw_response, flags=re.DOTALL).strip()
    if clean:
        lines += ["", "--- Agent Analysis ---", clean[:800]]

    return "\n".join(lines)


def _extract_tasks(cadence: str, results: list) -> tuple[list, list]:
    """
    Extract all Asana tasks and approval requests from all role results.
    Returns (tasks_to_create, actions_needing_approval).

    tasks_to_create: list of dicts ready for create_task()
    actions_needing_approval: list of result dicts whose action is a channel mutation
    """
    tasks     = []
    approvals = []

    channel_actions = {"pause", "exclude", "adjust", "scale", "pause-and-replace",
                       "refresh", "launch", "fix", "optimize"}

    # Normalise asset-level synonyms the Claude prompt might emit.
    asset_aliases = {
        "campaign": "campaign", "campaigns": "campaign",
        "adset": "adset", "ad_set": "adset", "ad set": "adset",
        "adgroup": "adset", "ad_group": "adset", "ad group": "adset",
        "ad squad": "adset", "ad-squad": "adset",
        "ad": "ad", "ads": "ad", "creative": "ad",
        "audience": "audience", "targeting": "audience", "lookalike": "audience",
        "tracking": "tracking", "utm": "tracking", "pixel": "tracking",
        "capi": "tracking", "attribution": "tracking", "conversion": "tracking",
        "keyword": "keyword", "keywords": "keyword", "search term": "keyword",
        "negative keyword": "keyword",
    }

    for res in results:
        role     = res["role"]
        decision = res.get("decision") or {}
        raw      = res.get("raw_response", "")
        action   = (decision.get("action") or "").lower()

        # Asana task for every role result that has meaningful content
        channel = decision.get("channel", "")
        dec_txt = decision.get("decision", "")
        if channel or dec_txt:
            project_key = PROJECT_KEY_MAP.get(
                decision.get("asana_project", "Daily Activity"), "daily_activity"
            )
            task_type = decision.get("asana_task_type", "Recommendation")

            # Asset level — Claude can put it in `asset_level`, `level`, or
            # we infer it from the decision text.
            raw_lvl = (decision.get("asset_level") or decision.get("level") or "").lower().strip()
            asset_level = asset_aliases.get(raw_lvl, "")
            if not asset_level:
                # Heuristic fallback: scan decision text for known keywords
                lower_dec = (dec_txt or "").lower()
                for k, v in asset_aliases.items():
                    if k in lower_dec:
                        asset_level = v
                        break

            title = (
                f"{channel} — {dec_txt}"
                if channel and dec_txt
                else dec_txt or channel or f"{cadence}/{role} check"
            )
            tasks.append({
                "title":       title,
                "description": _build_task_description(decision, raw, cadence, role),
                "project_key": project_key,
                "task_type":   task_type,
                "channel":     channel,
                "asset_level": asset_level,
                "action":      action,
            })

        # Actions needing human approval go to the approvals list
        if action in channel_actions and decision.get("confidence", "").lower() == "high":
            approvals.append(res)

    return tasks, approvals


# ---------------------------------------------------------------------------
# Slack summary builder
# ---------------------------------------------------------------------------

def _build_slack_summary(cadence: str, results: list, task_count: int) -> str:
    emoji = CADENCE_EMOJI.get(cadence, "📋")
    today = date.today().strftime("%d %b %Y")

    lines = [f"{emoji} *{cadence.title()} Performance Check — {today}*", ""]

    for res in results:
        role     = res["role"].replace("_", " ").title()
        decision = res.get("decision") or {}
        lines.append(f"*{role}*")

        if decision.get("channel"):
            lines.append(f"  • Channel: {decision['channel']}")
        if decision.get("kpi") and decision.get("value"):
            lines.append(f"  • {decision['kpi']}: {decision['value']} (threshold: {decision.get('threshold', 'N/A')})")
        if decision.get("decision"):
            lines.append(f"  • Decision: {decision['decision']}")
        if decision.get("action") and decision["action"].lower() != "recommend":
            lines.append(f"  • Action: {decision['action']}")
        lines.append("")

    lines.append(f"✅ *{task_count} Asana task(s) created* — check your Asana inbox.")
    if results and any((res.get("decision") or {}).get("action", "").lower()
                       in {"pause","exclude","adjust","scale"} for res in results):
        lines.append("⚠️  Approval requests sent to the approvals channel.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_cadence(cadence: str, force: bool = False):
    today = str(date.today())
    log.info(f"=== {cadence.upper()} cadence starting ===")

    if cadence != "on_demand" and not force:
        if not can_run_analysis(cadence):
            log.info(f"Already ran {cadence} today — skipping. Use --force to override.")
            return

    # 1. Collect data from ALL channels
    data = collect(cadence)
    channels_with_data = [k for k, v in data.items()
                          if k not in ("date", "cadence", "hubspot")
                          and (v.get("campaigns") or v.get("ads"))]
    log.info(f"Data collected from: {', '.join(channels_with_data)}")

    # 2. Run all role agents (cadence context passed for deeper weekly/monthly analysis)
    log.info(f"Running role agents for cadence={cadence}")
    results = run_trigger(cadence, data)
    if not results:
        log.warning(f"No role results returned — nothing to act on.")
        return

    # 3. Extract all tasks and approvals from all roles at once
    tasks, approvals = _extract_tasks(cadence, results)

    # 4. Ensure Asana channel sections exist (fast no-op if already created)
    try:
        ensure_channel_sections()
    except Exception as e:
        print(f"[asana] section setup warning: {e}")

    # 5. BATCH create all Asana tasks in one go
    created = 0
    print(f"[asana] Creating {len(tasks)} tasks in batch...")
    for t in tasks:
        gid = create_task(
            title=t["title"],
            description=t["description"],
            project_key=t["project_key"],
            task_type=t["task_type"],
            channel=t.get("channel", ""),
            asset_level=t.get("asset_level", ""),
            action=t.get("action", ""),
        )
        if gid:
            created += 1
    log.info(f"Asana batch complete: {created}/{len(tasks)} tasks created.")

    # 6. Post ONE combined Slack summary to notify channel
    summary_text = _build_slack_summary(cadence, results, created)
    send_summary(
        subject=f"{cadence.title()} check | {today}",
        body_text=summary_text,
        event_type={"daily": "daily_summary", "weekly": "weekly_review",
                    "monthly": "monthly_review", "quarterly": "monthly_review",
                    "on_demand": "daily_summary"}.get(cadence, "daily_summary"),
        meta={"Cadence": cadence, "Tasks": created, "Roles": len(results)},
    )

    # 6b. Generate the rendered daily report (Markdown -> HTML).
    #     Saved to reports/<date>.html + reports/latest.html so the team
    #     has a permalink. Failure here must not break the cadence.
    try:
        from claude.reporter import assemble_report_data
        from reports.render import save_report
        report = assemble_report_data(
            cadence=cadence,
            role_results=results,
            tasks_created=[t["title"] for t in tasks],
            approvals_pending=[
                {"role": r["role"], "decision": r.get("decision") or {}}
                for r in approvals
            ],
            permalink="/reports/latest",
        )
        path = save_report(report)
        log.info(f"Daily report rendered -> {path}")
    except Exception as e:
        log.warning(f"Daily report generation failed (non-fatal): {e}")

    # 7. Handle high-confidence channel actions → approval channel
    for res in approvals:
        print(f"[approval] Requesting approval for: {res['role']}")
        result = send_approval_request(res)
        ts = result.get("slack_ts") if result else None
        if ts:
            approval = wait_for_approval(ts, timeout_minutes=60)
            print(f"[approval] Response: {approval}")
            if approval == "approved":
                execute_channel_action(res.get("decision") or {})
        else:
            print(f"[approval] No Slack ts — manual approval via Asana task.")

    # 8. Zapier health check — runs alongside daily cadence
    try:
        from collectors.zapier import run_check as zapier_check
        zapier_check(since_hours=26, create_tasks=True)  # 26h covers any drift
    except Exception as e:
        log.warning(f"Zapier check failed (non-fatal): {e}")

    # 9. Mark cadence complete
    if cadence != "on_demand":
        mark_analysis_done(cadence)

    log.info(f"{cadence} cadence complete — Tasks: {created}  Approvals: {len(approvals)}")


# ---------------------------------------------------------------------------
# Post-approval execution
# ---------------------------------------------------------------------------

def execute_channel_action(decision: dict):
    action  = (decision.get("action") or "").lower()
    channel = (decision.get("channel") or "").lower()
    entity  = (decision.get("entity") or "").lower()
    notes   = decision.get("notes", "")

    if action.startswith("pause"):
        if "google" in channel:
            if "keyword" in entity and notes:
                gads_exec.pause_keyword(notes)
                print(f"✅ Paused Google Ads keyword: {notes}")
            elif "ad" in entity and notes:
                gads_exec.pause_ad(notes)
                print(f"✅ Paused Google Ads ad: {notes}")
        elif "meta" in channel and notes:
            meta_exec.pause_ad(notes)
            print(f"✅ Paused Meta ad: {notes}")
    else:
        print(f"Action '{action}' approved — Asana task is the execution record.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args    = sys.argv[1:]
    cadence = args[0] if args else "daily"
    force   = "--force" in args or "--bust" in args

    if cadence == "status":
        import pprint; pprint.pprint(cache_status())
        sys.exit(0)

    if "--bust" in args:
        bust_all()

    if cadence not in CADENCE_DAYS:
        sys.exit(f"Unknown cadence: {cadence!r}. Use: {list(CADENCE_DAYS)} or 'status'")

    run_cadence(cadence, force=force)
