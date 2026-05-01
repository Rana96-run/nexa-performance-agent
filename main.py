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

Channels in analysis: Google Ads · Meta · Snapchat · TikTok · LinkedIn · Microsoft Ads · HubSpot
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
from executors.google_ads import list_search_terms, classify_search_terms, add_negative_keywords


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
    print(f"[collect] channels: Google Ads · Meta · Snapchat · TikTok · LinkedIn · Microsoft Ads · HubSpot")

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

def _build_action_lines(tasks: list, approvals: list) -> list[str]:
    """
    Spell out agent actions in full — no abbreviations (per CLAUDE.md).
    Groups tasks by action type and describes what happened precisely.
    """
    scale_channels:    list[str] = []
    pause_channels:    list[str] = []
    junk_channels:     list[str] = []
    optimize_channels: list[str] = []
    negatives_count  = 0
    kw_paused_count  = 0
    is_flagged       = 0
    qs_flagged       = 0
    kw_expand        = 0

    for t in tasks:
        action  = (t.get("action") or "").lower()
        title   = (t.get("title") or "").lower()
        channel = (t.get("channel") or t.get("title", "").split("—")[0].strip() or "")

        if action == "scale":
            scale_channels.append(channel)
        elif action == "pause":
            pause_channels.append(channel)
        elif "junk" in title or "junk-leads" in title:
            junk_channels.append(channel)
        elif action in ("optimize", "adjust", "recommend", "fix"):
            optimize_channels.append(channel)
        elif "negative keyword" in title or "negatives" in title:
            negatives_count += 1
        elif "impression share" in title or "impression-share" in title:
            is_flagged += 1
        elif "quality score" in title or "quality-score" in title:
            qs_flagged += 1
        elif "keyword expansion" in title or "search term" in title:
            kw_expand += 1
        elif "non-converting keyword" in title or "kw-auto-paused" in title:
            kw_paused_count += 1

    lines: list[str] = []

    if scale_channels:
        ch_str = ", ".join(scale_channels[:3])
        lines.append(
            f"  • Scaled {len(scale_channels)} campaign(s) +25% on {ch_str} "
            f"(CPQL + CPL both in scale zone) — executed"
        )
    if pause_channels:
        ch_str = ", ".join(pause_channels[:3])
        lines.append(
            f"  • Paused {len(pause_channels)} campaign(s) on {ch_str} "
            f"(CPQL critical, minimum 14-day window met) — executed"
        )
    if junk_channels:
        lines.append(
            f"  • {len(junk_channels)} junk-leads alert(s) — "
            f"low qualification rate despite low CPL"
        )
    if optimize_channels:
        # deduplicate channels, preserve insertion order
        seen: dict = {}
        for ch in optimize_channels:
            seen[ch] = None
        ch_str = ", ".join(seen)
        lines.append(
            f"  • Optimization recommendations queued for {ch_str} — "
            f"review Asana tasks and approve in #approvals"
        )
    if kw_paused_count:
        lines.append(
            f"  • Google Ads: {kw_paused_count} non-converting keyword(s) "
            f"auto-paused (zero conversions after 14+ days) — executed"
        )
    if negatives_count:
        lines.append(
            f"  • Google Ads: {negatives_count} negative keyword(s) added "
            f"from weekly search term review — executed"
        )
    if is_flagged:
        lines.append(
            f"  • Google Ads: Impression Share below threshold on "
            f"{is_flagged} campaign(s) — budget increase task in Asana"
        )
    if qs_flagged:
        lines.append(
            f"  • Google Ads: Quality Score below threshold on "
            f"{qs_flagged} keyword(s) — ad copy improvement task in Asana"
        )
    if kw_expand:
        lines.append(
            f"  • Google Ads: {kw_expand} search term(s) identified as "
            f"converting — ready to promote to exact/phrase match keywords"
        )

    # Any approval-pending actions not covered above
    pending_actions = [
        (res.get("decision") or {}).get("action", "")
        for res in approvals
        if (res.get("decision") or {}).get("action", "").lower()
        not in ("scale", "pause")
    ]
    if pending_actions:
        uniq = list(dict.fromkeys(pending_actions))
        lines.append(
            f"  • {', '.join(a.title() for a in uniq if a)} action(s) "
            f"pending your approval in #approvals"
        )

    return lines


def _build_slack_summary(cadence: str, results: list, tasks: list, approvals: list) -> str:
    """
    Build the main Slack summary per CLAUDE.md required format:
      1. Dashboard URL (plain text — never a hyperlink)
      2. 7-day headline totals (spend · leads · SQLs · CPL · CPQL)
      3. Peak numbers: top + worst campaign per channel with CPQL
      4. Agent actions spelled out in full (no abbreviations)
      5. Asana task count + approval count
    """
    import os
    from datetime import timedelta, timezone as _tz

    riyadh   = _tz(timedelta(hours=3))
    today_str = date.today().strftime("%d %b %Y")
    emoji    = CADENCE_EMOJI.get(cadence, "📋")
    domain   = (os.getenv("RAILWAY_PUBLIC_DOMAIN")
                or os.getenv("APP_DOMAIN", "nexa-performance-agent.up.railway.app"))
    url      = f"https://{domain}/paid-performance/latest"

    lines = [
        f"{emoji} *{cadence.title()} Performance Check — {today_str}*",
        f"Dashboard: {url}",
        "",
    ]

    # ── 7-day headline totals from BQ ────────────────────────────────────────
    try:
        from notifications.daily_summary import _headline_numbers, _peak_numbers_lines
        headline = _headline_numbers()
        if headline:
            h = headline["total"]
            cpl_str  = f"${h['cpl']:,}"  if h.get("cpl")  else "—"
            cpql_str = f"${h['cpql']:,}" if h.get("cpql") else "—"
            lines.append(
                f"*7-day totals:*  "
                f"Spend ${h['spend']:,}  ·  "
                f"Leads {h['leads']}  ·  "
                f"SQLs {h['qual']}  ·  "
                f"CPL {cpl_str}  ·  "
                f"CPQL {cpql_str}"
            )
        peak_lines = _peak_numbers_lines()
        if peak_lines:
            lines.append("*Peak numbers — top + worst per channel (CPQL):*")
            lines.extend(peak_lines)
        lines.append("")
    except Exception as e:
        print(f"[slack-summary] BQ headline/peak fetch skipped: {e}")

    # ── Agent actions ────────────────────────────────────────────────────────
    action_lines = _build_action_lines(tasks, approvals)
    if action_lines:
        lines.append("*Agent actions:*")
        lines.extend(action_lines)
        lines.append("")

    # ── Footer ───────────────────────────────────────────────────────────────
    lines.append(f"✅ *{len(tasks)} Asana task(s) created*")
    if approvals:
        lines.append(
            f"⚠️  *{len(approvals)} approval request(s)* sent to "
            f"<#{SLACK_CHANNEL_APPROVAL}>"
        )

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

    # 0. Weekly-only: search term review runs deterministically before LLM roles
    if cadence == "weekly":
        try:
            st_summary = weekly_search_term_review()
            log.info(f"Search term review: {st_summary}")
        except Exception as e:
            log.warning(f"Search term review failed (non-fatal): {e}")

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

    # 6. Post Slack summary.
    #    Daily cadence: operational_scheduler._post_report_ready() owns the channel
    #    after the nightly cycle finishes — it has spike data, health findings, and
    #    audit tasks that run_cadence() doesn't see.  Posting here too would flood
    #    the channel with duplicates.  Non-daily cadences (weekly, monthly, quarterly)
    #    still post here because _post_report_ready() is not called for them.
    if cadence != "daily":
        summary_text = _build_slack_summary(cadence, results, tasks, approvals)
        send_summary(
            subject=f"{cadence.title()} check | {today}",
            body_text=summary_text,
            event_type={"weekly": "weekly_review",
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
            permalink="/paid-performance/latest",
        )
        path = save_report(report)
        log.info(f"Daily report rendered -> {path}")
    except Exception as e:
        log.warning(f"Daily report generation failed (non-fatal): {e}")

    # 7. Handle high-confidence channel actions -> approval channel
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
# Weekly search term review (deterministic — runs before role agents)
# ---------------------------------------------------------------------------

def weekly_search_term_review() -> dict:
    """
    Pull Google Ads search terms for last 7 days, auto-classify, and act:
      - Negatives  → add immediately (no approval required)
      - Converting → post to #approvals Slack channel for keyword addition
      - Watch      → create Asana task for next week

    Returns summary dict logged by the caller.
    """
    from notifications.notify import post_to_slack
    today_str = str(date.today())

    print("[search_terms] Starting weekly search term review...")
    terms = list_search_terms(days=7)
    if not terms:
        print("[search_terms] No search terms returned — skipping.")
        return {"terms": 0, "negatives_added": 0, "approvals_sent": 0}

    buckets = classify_search_terms(terms)

    negatives_added: list[str] = []
    approvals_sent:  list[str] = []

    # 1. Auto-add negatives (Direct — no approval)
    # Group by campaign resource name so we batch per campaign
    from collections import defaultdict
    by_campaign: dict[str, list] = defaultdict(list)
    for t in buckets["negative"]:
        # Derive campaign resource name from ad_group_resource_name
        # Format: customers/{cid}/adGroups/{agid} → customers/{cid}/campaigns/{cid}
        ag_rn = t["ad_group_resource_name"]
        cid   = ag_rn.split("/")[1]
        cid_str = f"customers/{cid}"
        by_campaign[cid_str].append(t["query"])

    for campaign_prefix, queries in by_campaign.items():
        # campaign_prefix is "customers/{cid}" — extract cid, pair with campaign_id
        cid = campaign_prefix.split("/")[1]
        # Find any term belonging to this customer to get a campaign_id
        camp_rn = None
        for t in buckets["negative"]:
            ag_rn = t["ad_group_resource_name"]
            if ag_rn.split("/")[1] == cid:
                camp_rn = f"customers/{cid}/campaigns/{t['campaign_id']}"
                break
        if not camp_rn:
            print(f"[search_terms] Could not resolve campaign resource for {campaign_prefix} — skipping")
            continue
        try:
            add_negative_keywords(
                campaign_resource_name=camp_rn,
                keywords=queries,
            )
            negatives_added.extend(queries)
            print(f"[search_terms] Added {len(queries)} negatives to campaign {camp_rn}")
        except Exception as e:
            print(f"[search_terms] Negative keyword error: {e}")

    # 2. Post converting terms to #approvals
    if buckets["convert"]:
        lines = [f"*Google Ads — Weekly Search Term Review | {today_str}*",
                 f"Found *{len(buckets['convert'])} converting search terms* to add as keywords.\n"]
        for t in buckets["convert"]:
            lines.append(
                f"• `{t['query']}` — {t['clicks']} clicks, {t['conversions']:.0f} conv, "
                f"${t['cost_usd']:.2f} spend | ad group: _{t['ad_group_name']}_"
            )
        lines.append(
            f"\nReact ✅ to add these as EXACT match keywords to their respective ad groups. "
            f"React ❌ to skip."
        )
        msg = "\n".join(lines)
        try:
            post_to_slack(msg, channel=SLACK_CHANNEL_APPROVAL)
            approvals_sent = [t["query"] for t in buckets["convert"]]
            print(f"[search_terms] Approval request sent for {len(approvals_sent)} converting terms.")
        except Exception as e:
            print(f"[search_terms] Slack approval post failed: {e}")

    # 3. Create Asana task with full weekly summary
    watch_lines  = [f"• `{t['query']}` — {t['clicks']} clicks, ${t['cost_usd']:.2f}" for t in buckets["watch"]]
    neg_lines    = [f"• `{q}`" for q in negatives_added]
    conv_lines   = [f"• `{t['query']}` — {t['conversions']:.0f} conv" for t in buckets["convert"]]

    desc = "\n".join([
        f"Weekly search term review — {today_str}",
        f"Total terms pulled: {len(terms)}",
        "",
        f"NEGATIVES ADDED ({len(negatives_added)}) — executed automatically:",
        *([f"  • {q}" for q in negatives_added] or ["  (none)"]),
        "",
        f"CONVERTING TERMS ({len(approvals_sent)}) — approval requested in #approvals:",
        *([f"  • {t['query']} ({t['conversions']:.0f} conv, ${t['cost_usd']:.2f})" for t in buckets["convert"]] or ["  (none)"]),
        "",
        f"WATCH NEXT WEEK ({len(buckets['watch'])}):",
        *([f"  • {t['query']} ({t['clicks']} clicks, ${t['cost_usd']:.2f})" for t in buckets["watch"]] or ["  (none)"]),
        "",
        "Created: " + today_str,
        "Due: " + today_str,
        "Priority: Medium",
        "Type: Direct Log",
        "Channel: google_ads",
        "Asset level: keyword",
        "Action: Weekly search term review executed",
    ])

    try:
        create_task(
            title=f"[Google Ads] Weekly search terms review — {today_str}",
            description=desc,
            project_key="daily_activity",
            task_type="Keyword/Placement",
            channel="google_ads",
            asset_level="keyword",
            action="review",
        )
        print(f"[search_terms] Asana task created.")
    except Exception as e:
        print(f"[search_terms] Asana task creation failed: {e}")

    summary = {
        "terms_pulled":     len(terms),
        "negatives_added":  len(negatives_added),
        "approvals_sent":   len(approvals_sent),
        "watch":            len(buckets["watch"]),
    }
    print(f"[search_terms] Done: {summary}")
    return summary


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
                gads_exec.set_keyword_status(notes, "PAUSED")
                print(f"✅ Paused Google Ads keyword: {notes}")
            elif "ad" in entity and notes:
                gads_exec.set_ad_status(notes, "PAUSED")
                print(f"✅ Paused Google Ads ad: {notes}")
        elif "meta" in channel and notes:
            meta_exec.set_ad_status(notes, "PAUSED")
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
