"""
Slack @mention listener for the Qoyod Performance Agent.

Polls both Slack channels every 60 seconds for messages that mention the
bot. Parses the request, routes it to Claude, and replies in-thread.

What it can do when mentioned:
  @Nexa report [channel] [last N days]   -> performance report
  @Nexa brief [description]              -> creative/campaign brief
  @Nexa scaling strategy [campaign]      -> data-backed scaling plan
  @Nexa miro [what to diagram]           -> Miro board update
  @Nexa task [description]               -> create Asana task directly
  @Nexa past due                         -> list overdue Asana tasks
  @Nexa [anything else]                  -> Nexa answers as the agent

Run alongside the operational scheduler. Requires the bot to have been
added to both channels in Slack.
"""
import os
import re
import sys
import time
import json
import anthropic
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from logs.logger import setup_global_logging

setup_global_logging("slack-listener")  # captures every print() into logs/
load_dotenv()

SLACK_BOT_TOKEN    = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_NOTIFY   = os.getenv("SLACK_CHANNEL_NOTIFY", "")
SLACK_CHANNEL_APPROVAL = os.getenv("SLACK_CHANNEL_APPROVAL", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
MIRO_ACCESS_TOKEN  = os.getenv("MIRO_ACCESS_TOKEN")
MIRO_BOARD_ID      = os.getenv("MIRO_BOARD_ID")
ASANA_TOKEN        = os.getenv("ASANA_ACCESS_TOKEN")

slack  = WebClient(token=SLACK_BOT_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Both channels monitored for @mentions
# NOTIFY  = summaries, alerts, reminders
# APPROVAL = direct actions (pause/scale) — agent also listens here
CHANNELS = list({c for c in [SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL] if c})

# Track already-processed message timestamps so we never double-reply
_seen: set[str] = set()
_bot_user_id: str = ""


# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------

def get_bot_user_id() -> str:
    global _bot_user_id
    if _bot_user_id:
        return _bot_user_id
    try:
        resp = slack.auth_test()
        _bot_user_id = resp["user_id"]
        print(f"[listener] Bot user ID: {_bot_user_id}")
    except SlackApiError as e:
        print(f"[listener] Could not get bot user ID: {e}")
        _bot_user_id = ""
    return _bot_user_id


# ---------------------------------------------------------------------------
# Channel polling
# ---------------------------------------------------------------------------

def poll_channel(channel_id: str, since_ts: str) -> list[dict]:
    """Fetch messages from a channel since a given timestamp."""
    try:
        resp = slack.conversations_history(
            channel=channel_id,
            oldest=since_ts,
            limit=20,
        )
        return resp.get("messages", [])
    except SlackApiError as e:
        err = e.response.get("error", "")
        if err in ("not_in_channel", "channel_not_found", "missing_scope"):
            # Silently skip — bot hasn't been added to this channel yet
            pass
        else:
            print(f"[listener] Poll error on {channel_id}: {e}")
        return []


def is_mention(message: dict, bot_uid: str) -> bool:
    """Return True if message mentions the bot."""
    text = message.get("text", "")
    return f"<@{bot_uid}>" in text


def strip_mention(text: str, bot_uid: str) -> str:
    """Remove the @mention prefix and return the clean request."""
    return re.sub(rf"<@{bot_uid}>", "", text).strip()


# ---------------------------------------------------------------------------
# Request routing
# ---------------------------------------------------------------------------

def route_request(clean_text: str) -> str:
    """
    Detect intent from the message text and call the appropriate handler.
    Returns the reply text to post back to Slack.
    """
    lower = clean_text.lower()

    if re.search(r"\bpast.?due\b|\boverdue\b", lower):
        return handle_past_due()
    elif re.search(r"\breport\b", lower):
        return handle_report(clean_text)
    elif re.search(r"\b(gtm|go.?to.?market|campaign.?plan|channel.?distribut|budget.?allocat|launch.?plan)\b", lower):
        # Inter-agent GTM / launch plan → structured brief with BQ data
        return handle_gtm_brief(clean_text)
    elif re.search(r"\bbrief\b", lower):
        # Generic brief — check if it's a campaign brief with enough context
        if re.search(r"\b(budget|channel|audience|product|invoice|bookkeeping|qflavours)\b", lower):
            return handle_gtm_brief(clean_text)
        return handle_brief(clean_text)
    elif re.search(r"\bscal(e|ing)\b", lower):
        return handle_scaling(clean_text)
    elif re.search(r"\bmiro\b|\bdiagram\b|\bboard\b", lower):
        return handle_miro(clean_text)
    elif re.search(r"\b(create|add)\s+task\b", lower):
        return handle_create_task(clean_text)
    else:
        return handle_general(clean_text)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

from config import (
    CPL_WARNING, CPQL_WARNING, QUAL_RATE_TARGET, ROAS_TARGET,
    CPL_SCALE, CPQL_SCALE, USD_SAR_PEG,
)

AGENT_SYSTEM = f"""You are Nexa — Qoyod's AI Performance Marketing Agent.
You are an expert media buyer and analyst embedded in the team's workflow.
Qoyod is a Saudi B2B SaaS company (cloud accounting, ZATCA compliance).
You manage paid media across Google Ads, Meta, Snapchat, LinkedIn, Microsoft Ads, and TikTok.
You also create campaign setups, campaign briefs, and scaling strategies.
KPI thresholds: CPL < {CPL_WARNING} USD, CPQL < {CPQL_WARNING} USD, Qualification rate > {int(QUAL_RATE_TARGET*100)}%, ROAS > {ROAS_TARGET}.
Currency is always USD (all spend values are normalized to USD; SAR pegged at {USD_SAR_PEG}). Respond concisely and professionally.
Format replies for Slack (*bold*, bullet points). Never make up data — state if unavailable."""


def _ask_claude(user_msg: str) -> str:
    msg = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=AGENT_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return msg.content[0].text


def handle_past_due() -> str:
    """Check Asana for overdue tasks and return a formatted list."""
    try:
        import asana
        config = asana.Configuration()
        config.access_token = ASANA_TOKEN
        client = asana.ApiClient(config)
        tasks_api = asana.TasksApi(client)

        from config import ASANA_PROJECTS
        overdue_items = []
        now = datetime.now(timezone.utc)

        for proj_name, proj_id in ASANA_PROJECTS.items():
            if not proj_id:
                continue
            try:
                tasks = tasks_api.get_tasks_for_project(
                    proj_id,
                    {"opt_fields": "name,due_on,completed,permalink_url", "completed": False},
                )
                for t in tasks:
                    due_str = t.get("due_on")
                    if due_str:
                        due_dt = datetime.strptime(due_str, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                        if due_dt < now:
                            days_late = (now - due_dt).days
                            overdue_items.append(
                                f"• *{t['name'][:60]}* — {days_late}d overdue "
                                f"(<{t.get('permalink_url', '')}|open>)"
                            )
            except Exception:
                continue

        if not overdue_items:
            return "✅ No overdue tasks found across all Asana projects."
        header = f"⚠️ *{len(overdue_items)} overdue task(s) found:*\n"
        return header + "\n".join(overdue_items[:15])

    except Exception as e:
        return f"Could not fetch Asana tasks: {e}"


def handle_report(request: str) -> str:
    """Generate a performance report narrative via Claude."""
    prompt = (
        f"The team asked for: {request}\n\n"
        "Generate a structured performance report. Include: channel summary, "
        "CPL/CPQL status, top/bottom campaigns, key recommendations. "
        "Note that live data isn't fetched in this context — structure the "
        "report template and state what data is needed if not available."
    )
    return _ask_claude(prompt)


def _bq_channel_cpql(days: int = 14) -> list[dict]:
    """
    Pull CPQL per channel from BQ (last N days).
    Returns [{"channel": ..., "spend": ..., "sqls": ..., "cpql": ...}, ...]
    sorted by cpql ascending (best first).  Returns [] on any error.
    """
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        client = get_client()
        rows = list(client.query(f"""
            WITH hs AS (
              SELECT date, lead_utm_campaign, SUM(leads_qualified) AS sqls
              FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
              GROUP BY date, lead_utm_campaign
            )
            SELECT
              c.channel,
              ROUND(SUM(c.spend), 0)  AS spend,
              SUM(hs.sqls)            AS sqls,
              ROUND(SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0)), 0) AS cpql
            FROM `{PROJECT_ID}.{DATASET}.campaigns_daily` c
            LEFT JOIN hs ON c.date = hs.date
                        AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
            WHERE c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {days} DAY)
              AND c.date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
            GROUP BY c.channel
            HAVING SUM(c.spend) >= 50
            ORDER BY cpql ASC NULLS LAST
        """).result())
        return [
            {
                "channel": r.channel,
                "spend":   int(r.spend or 0),
                "sqls":    int(r.sqls  or 0),
                "cpql":    int(r.cpql)  if r.cpql is not None else None,
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[listener] BQ channel CPQL fetch failed: {e}")
        return []


# Channel defaults (used when BQ data is unavailable)
_CHANNEL_DEFAULTS = [
    {"channel": "google_ads",    "pct": 35, "ad_type": "Search"},
    {"channel": "meta",          "pct": 30, "ad_type": "LeadGen"},
    {"channel": "snapchat",      "pct": 15, "ad_type": "LeadGen"},
    {"channel": "linkedin",      "pct": 12, "ad_type": "LeadGen"},
    {"channel": "tiktok",        "pct":  8, "ad_type": "LeadGen"},
]

_CHANNEL_DISPLAY = {
    "google_ads":    "Google Search",
    "meta":          "Meta",
    "snapchat":      "Snapchat",
    "linkedin":      "LinkedIn",
    "tiktok":        "TikTok",
    "microsoft_ads": "Microsoft Ads",
}

_AUDIENCE_SETUP = {
    "google_ads":    "Broad keywords + Competitor keywords (AR) | Maximize Conversions bidding",
    "meta":          "Interests → Lookalike 3% → Retargeting | LeadGen form",
    "snapchat":      "Interests (AR) + Lookalike | Lead Snap Ad",
    "linkedin":      "Job function + Company size 10-500 | LeadGen form",
    "tiktok":        "Interests AR + Lookalike | Spark Ad / Lead form",
    "microsoft_ads": "Broad match + Competitor keywords | Maximize Conversions",
}


def _allocate_budget(total: float, bq_rows: list[dict]) -> list[dict]:
    """
    Allocate budget across channels.
    If BQ data exists: weight inversely by CPQL (better CPQL → more budget).
    Falls back to _CHANNEL_DEFAULTS if BQ is empty.
    Returns [{"channel", "display", "pct", "budget", "cpql", "ad_type"}, ...]
    """
    if bq_rows:
        # Only use channels that have CPQL data; cap at 5 channels
        usable = [r for r in bq_rows if r["cpql"] and r["cpql"] > 0][:5]
        if usable:
            # Inverse-CPQL weighting: lower CPQL = higher weight
            weights = [1 / r["cpql"] for r in usable]
            total_w = sum(weights)
            allocs = []
            for r, w in zip(usable, weights):
                pct    = round(w / total_w * 100)
                budget = round(total * pct / 100)
                ch     = r["channel"]
                allocs.append({
                    "channel": ch,
                    "display": _CHANNEL_DISPLAY.get(ch, ch.title()),
                    "pct":     pct,
                    "budget":  budget,
                    "cpql":    r["cpql"],
                    "ad_type": "Search" if ch in ("google_ads", "microsoft_ads") else "LeadGen",
                    "audience": _AUDIENCE_SETUP.get(ch, "—"),
                })
            return allocs

    # Fallback: fixed defaults
    allocs = []
    for d in _CHANNEL_DEFAULTS:
        ch = d["channel"]
        allocs.append({
            "channel":  ch,
            "display":  _CHANNEL_DISPLAY.get(ch, ch.title()),
            "pct":      d["pct"],
            "budget":   round(total * d["pct"] / 100),
            "cpql":     None,
            "ad_type":  d["ad_type"],
            "audience": _AUDIENCE_SETUP.get(ch, "—"),
        })
    return allocs


def handle_gtm_brief(request: str) -> str:
    """
    Data-driven campaign brief for inter-agent GTM requests.

    Extracts: product, budget, date range, language from the request text.
    Pulls real CPQL per channel from BQ to allocate budget.
    Generates campaign names via naming convention.
    Creates an Asana task with the full brief.
    """
    # ── Parse key fields via Claude (lightweight) ─────────────────────────────
    parse_prompt = (
        f"Extract from this request (return JSON only, no markdown):\n"
        f'Request: "{request}"\n\n'
        f'Return exactly: {{"product": "...", "budget_usd": 0, "start_date": "YYYY-MM-DD", '
        f'"end_date": "YYYY-MM-DD", "language": "AR|EN|AREN", "objective": "lead_gen|awareness|traffic", '
        f'"notes": "..."}}\n'
        f'product: normalize to Invoice/Bookkeeping/Qflavours/General or season name.\n'
        f'If budget missing use 10000. If dates missing use next 30 days. '
        f'If language missing use AR. If objective missing use lead_gen.'
    )
    try:
        raw = _ask_claude(parse_prompt)
        # Strip markdown fences if any
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip()
        parsed = json.loads(raw)
    except Exception:
        parsed = {}

    product     = parsed.get("product", "Invoice")
    budget_usd  = float(parsed.get("budget_usd") or 10000)
    start_date  = parsed.get("start_date", "")
    end_date    = parsed.get("end_date", "")
    language    = parsed.get("language", "AR").upper()
    objective   = parsed.get("objective", "lead_gen")
    extra_notes = parsed.get("notes", "")

    # Friendly date string
    date_str = f"{start_date} → {end_date}" if start_date and end_date else "TBD"

    # ── Pull live channel CPQL from BQ ────────────────────────────────────────
    bq_rows = _bq_channel_cpql(days=14)
    allocs  = _allocate_budget(budget_usd, bq_rows)

    # ── Build channel distribution block ─────────────────────────────────────
    icon_map = {"scale": ":large_green_circle:", "ok": ":large_blue_circle:",
                "warn":  ":large_yellow_circle:", "": ":white_circle:"}
    ch_lines = []
    for a in allocs:
        cpql_str = f" · CPQL ${a['cpql']}" if a["cpql"] else " · no data"
        ch_lines.append(
            f"  *{a['display']}*: {a['pct']}% · ${a['budget']:,}{cpql_str}"
        )

    # ── Generate campaign names (naming convention) ───────────────────────────
    name_lines = []
    for a in allocs:
        ch      = a["channel"]
        ad_type = a["ad_type"]
        ch_prefix = {
            "google_ads":    "Google",
            "meta":          "Meta",
            "snapchat":      "Snapchat",
            "linkedin":      "LinkedIn",
            "tiktok":        "TikTok",
            "microsoft_ads": "Microsoft",
        }.get(ch, ch.title())

        if objective == "awareness":
            audiences = ["ImpressionShare"]
        elif ch == "google_ads":
            audiences = ["Broad"]
        elif ch == "linkedin":
            audiences = ["Interests"]
        else:
            audiences = ["Interests", "Lookalike", "Retargeting"]

        for aud in audiences:
            name_lines.append(f"  `{ch_prefix}_{ad_type}_{language}_{product}_{aud}`")

    # ── KPI targets ───────────────────────────────────────────────────────────
    from config import CPQL_ACCEPTABLE, CPL_ACCEPTABLE, QUAL_RATE_TARGET, ROAS_GOOD
    kpi_line = (f"CPQL ≤ ${CPQL_ACCEPTABLE:.0f}  ·  CPL ≤ ${CPL_ACCEPTABLE:.0f}  ·  "
                f"Qual rate ≥ {int(QUAL_RATE_TARGET*100)}%  ·  ROAS ≥ {ROAS_GOOD}")

    # ── Audience setup block ──────────────────────────────────────────────────
    aud_lines = [f"  *{a['display']}*: {a['audience']}" for a in allocs]

    # ── Compose Slack message ─────────────────────────────────────────────────
    data_note = "(based on 14d CPQL from BQ)" if bq_rows else "(default allocation — no BQ data)"
    budget_monthly = f"${budget_usd:,.0f}"

    reply_lines = [
        f":clipboard: *Campaign Brief — {product} · {language}*",
        f"*Objective:* {'Lead Generation' if objective == 'lead_gen' else objective.title()}",
        f"*Total Budget:* {budget_monthly}  ·  *Period:* {date_str}",
        "",
        f"*Channel Distribution* {data_note}",
    ] + ch_lines + [
        "",
        "*Audience Setup:*",
    ] + aud_lines + [
        "",
        "*Campaign Names (naming convention):*",
    ] + name_lines + [
        "",
        f"*KPI Targets:*  {kpi_line}",
    ]

    if extra_notes:
        reply_lines += ["", f"_Notes from GTM: {extra_notes}_"]

    # ── Creative performance: pull best/worst across all campaigns for this product
    try:
        from analysers.creative_performance import audit_creative_performance, format_creative_slack
        # Search by product keyword across all campaigns
        cr = audit_creative_performance(campaign_name=None, days=30)
        # Filter creatives whose utm_content name contains the product hint
        product_lower = product.lower()
        cr["creatives"] = [
            c for c in cr.get("creatives", [])
            if product_lower in c["utm_content"].lower()
        ]
        # Re-derive best/worst from filtered set
        if cr["creatives"]:
            cr["best"]  = sorted(cr["creatives"], key=lambda c: (-c["sqls"], -c["qual_rate"]))[:2]
            cr["worst"] = sorted(cr["creatives"], key=lambda c: (-c["disquals"], c["qual_rate"]))[:1]
            from analysers.creative_performance import _build_direction
            cr["direction"] = _build_direction(cr["best"], cr["worst"], cr["creatives"])
        creative_block = format_creative_slack(cr)
        if creative_block:
            reply_lines += ["", creative_block]
    except Exception as e:
        print(f"[listener] creative analysis in brief failed: {e}")

    reply_text = "\n".join(reply_lines)

    # ── Create Asana task with full brief ─────────────────────────────────────
    try:
        from executors.asana import create_task
        asana_body = reply_text.replace("*", "").replace("`", "").replace(":clipboard:", "")
        asana_body += f"\n\nSource request:\n{request[:500]}"
        create_task(
            title=f"Campaign Brief — {product} {language} {date_str}",
            description=asana_body,
            project_key="daily_activity",
            task_type="Recommendation",
            channel="all",
            asset_level="campaign",
            action="launch",
        )
        reply_text += "\n\n✅ _Asana task created with full brief._"
    except Exception as e:
        reply_text += f"\n\n⚠️ _Asana task creation failed: {e}_"

    return reply_text


def handle_brief(request: str) -> str:
    """Generate a creative or campaign brief."""
    prompt = (
        f"The team asked for: {request}\n\n"
        "Generate a detailed brief. If it's a creative brief, include: "
        "objective, target audience, key message, format, platform, reference "
        "ads, CTA, required sizes, tone. If it's a campaign brief, include: "
        "goal, budget, channels, targeting, timeline, success KPIs."
    )
    return _ask_claude(prompt)


def handle_scaling(request: str) -> str:
    """Generate a scaling strategy."""
    prompt = (
        f"The team asked for: {request}\n\n"
        "Generate a data-driven scaling strategy. Include: scaling criteria "
        f"(CPL < {CPL_SCALE} USD, CPQL < {CPQL_SCALE} USD, qual rate > {int(QUAL_RATE_TARGET*100)}%), recommended budget "
        "increase % (typically 20-30% weekly), audience expansion tactics, "
        "creative refresh timeline, risk mitigation. Format for Slack."
    )
    return _ask_claude(prompt)


def handle_miro(request: str) -> str:
    """Create or update a sticky note / card on the Miro board."""
    if not MIRO_ACCESS_TOKEN or not MIRO_BOARD_ID:
        return "⚠️ Miro token or board ID not configured in .env"

    try:
        import requests
        content = _ask_claude(
            f"Summarize this for a Miro sticky note (max 200 words, plain text): {request}"
        )
        payload = {
            "data": {"content": content, "shape": "rectangle"},
            "style": {"fillColor": "#6C63FF", "textAlign": "center",
                      "textAlignVertical": "middle", "fontSize": "14"},
            "position": {"x": 0, "y": 0},
        }
        resp = requests.post(
            f"https://api.miro.com/v2/boards/{MIRO_BOARD_ID}/sticky_notes",
            headers={"Authorization": f"Bearer {MIRO_ACCESS_TOKEN}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            item_id = resp.json().get("id", "")
            return (
                f"✅ Added to Miro board:\n_{content[:120]}..._\n"
                f"<https://miro.com/app/board/{MIRO_BOARD_ID}|Open board>"
            )
        else:
            return f"Miro API error {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return f"Miro update failed: {e}"


def handle_create_task(request: str) -> str:
    """Create an Asana task from the mention."""
    try:
        from executors.asana import create_task
        # Extract task name from request
        task_name = re.sub(r"(?i)(create|add)\s+task\s*:?\s*", "", request).strip()
        if not task_name:
            return "Please specify a task title: `@Nexa create task [title]`"

        gid = create_task(
            title=task_name,
            description=f"Created via Slack @mention on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            project_key="daily_activity",
            task_type="Recommendation",
        )
        if gid:
            return f"✅ Asana task created: *{task_name}*"
        return "⚠️ Task creation failed — check Asana credentials."
    except Exception as e:
        return f"Task creation error: {e}"


def handle_general(request: str) -> str:
    """Route any free-form question to Claude as the performance agent."""
    return _ask_claude(request)


# ---------------------------------------------------------------------------
# Reply helper
# ---------------------------------------------------------------------------

def post_reply(channel: str, thread_ts: str, text: str):
    """Post a reply in-thread, splitting if needed (Slack 3000-char limit)."""
    from notifications.quiet import is_quiet, quiet_log
    if is_quiet():
        quiet_log("listener", f"{channel}/{thread_ts}", text)
        return
    chunks = [text[i:i+2900] for i in range(0, len(text), 2900)]
    for chunk in chunks:
        try:
            slack.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=chunk,
            )
        except SlackApiError as e:
            print(f"[listener] Reply error: {e}")


# ---------------------------------------------------------------------------
# Asana comment listener (polls for @Nexa in task comments)
# ---------------------------------------------------------------------------

_asana_seen: set[str] = set()


def _get_task_full_context(tasks_api, task_gid: str) -> str:
    """Fetch task name + notes + due date to give Nexa full context before replying."""
    try:
        task = tasks_api.get_task(
            task_gid,
            {"opt_fields": "gid,name,notes,due_on,assignee.name,custom_fields"},
        )
        parts = [f"Task: {task.get('name', '')}"]
        if task.get("notes"):
            # First 600 chars of description — enough for context, not too many tokens
            parts.append(f"Description:\n{task['notes'][:600]}")
        if task.get("due_on"):
            parts.append(f"Due: {task['due_on']}")
        if task.get("assignee"):
            parts.append(f"Assigned to: {task['assignee'].get('name', '')}")
        return "\n".join(parts)
    except Exception:
        return ""


def _get_recent_asana_comments() -> list[dict]:
    """
    Poll Asana projects for task comments containing '@Nexa'.
    Returns list of {task_gid, task_name, task_context, comment_gid, text, task_url}.
    Includes full task context so Nexa can reply with relevant information.
    """
    if not ASANA_TOKEN:
        return []
    try:
        import asana as asana_sdk
        from config import ASANA_PROJECTS
        config = asana_sdk.Configuration()
        config.access_token = ASANA_TOKEN
        client = asana_sdk.ApiClient(config)
        tasks_api   = asana_sdk.TasksApi(client)
        stories_api = asana_sdk.StoriesApi(client)

        hits = []
        for proj_id in ASANA_PROJECTS.values():
            if not proj_id:
                continue
            try:
                tasks = tasks_api.get_tasks_for_project(
                    proj_id,
                    {"opt_fields": "gid,name,permalink_url", "completed_since": "now"},
                )
                for task in tasks:
                    tgid = task.get("gid", "")
                    try:
                        stories = stories_api.get_stories_for_task(
                            tgid, {"opt_fields": "gid,text,type,created_at"}
                        )
                        for s in stories:
                            if s.get("type") != "comment":
                                continue
                            cgid = s.get("gid", "")
                            text = s.get("text", "")
                            if cgid not in _asana_seen and "@Nexa" in text:
                                _asana_seen.add(cgid)
                                # Fetch full task context for richer replies
                                task_context = _get_task_full_context(tasks_api, tgid)
                                hits.append({
                                    "task_gid":     tgid,
                                    "task_name":    task.get("name", ""),
                                    "task_context": task_context,
                                    "comment_gid":  cgid,
                                    "text":         text,
                                    "task_url":     task.get("permalink_url", ""),
                                })
                    except Exception:
                        continue
            except Exception:
                continue
        return hits
    except Exception as e:
        print(f"[asana-listener] Error: {e}")
        return []


def _reply_asana_comment(task_gid: str, reply_text: str):
    """Post a reply comment on an Asana task."""
    try:
        import asana as asana_sdk
        config = asana_sdk.Configuration()
        config.access_token = ASANA_TOKEN
        client = asana_sdk.ApiClient(config)
        stories_api = asana_sdk.StoriesApi(client)
        snippet = reply_text[:3000]
        stories_api.create_story_for_task(
            task_gid,
            {"data": {"text": f"[Nexa AI]\n{snippet}"}},
        )
    except Exception as e:
        print(f"[asana-listener] Reply error on task {task_gid}: {e}")


# ---------------------------------------------------------------------------
# Main loop (Slack + Asana)
# ---------------------------------------------------------------------------

def run():
    bot_uid = get_bot_user_id()
    if not bot_uid:
        print("[listener] WARNING: Could not get bot user ID — mention detection may fail.")

    print("=" * 52)
    print("  Qoyod Agent Listener — LIVE")
    print("=" * 52)
    print(f"  Slack notify channel:   {SLACK_CHANNEL_NOTIFY}")
    print(f"  Slack approval channel: {SLACK_CHANNEL_APPROVAL}")
    print(f"  Bot user ID: {bot_uid or '(unknown)'}")
    print("  Slack poll: every 60s | Asana poll: every 120s")
    print("  Mention @Nexa in Slack or @Nexa in Asana comments")
    print("=" * 52)

    # Startup heartbeat — confirms the listener came up cleanly after a restart.
    try:
        from notifications.notify import send_heartbeat
        send_heartbeat("slack-listener", status="started",
                       detail="listener online; polling Slack every 60s")
    except Exception as e:
        print(f"[listener] startup heartbeat skipped: {e}")

    since = str((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
    asana_tick = 0   # poll Asana every 2 Slack cycles

    while True:
        new_since = str(datetime.now(timezone.utc).timestamp())

        # --- Slack ---
        for channel in CHANNELS:
            messages = poll_channel(channel, since)
            for msg in messages:
                ts  = msg.get("ts", "")
                uid = msg.get("user", "")
                if ts in _seen:
                    continue
                if uid == bot_uid:
                    _seen.add(ts)
                    continue
                if bot_uid and not is_mention(msg, bot_uid):
                    _seen.add(ts)
                    continue

                _seen.add(ts)
                text  = msg.get("text", "")
                clean = strip_mention(text, bot_uid) if bot_uid else text
                print(f"[slack] Mention from <@{uid}> in {channel}: {clean[:80]!r}")

                try:
                    slack.reactions_add(channel=channel, timestamp=ts,
                                        name="hourglass_flowing_sand")
                except Exception:
                    pass

                try:
                    reply = route_request(clean)
                except Exception as e:
                    import traceback; traceback.print_exc()
                    reply = f"⚠️ Nexa error: {e}"
                post_reply(channel, ts, reply)

                try:
                    slack.reactions_remove(channel=channel, timestamp=ts,
                                           name="hourglass_flowing_sand")
                    slack.reactions_add(channel=channel, timestamp=ts,
                                        name="white_check_mark")
                except Exception:
                    pass

        # --- Asana (every 2nd cycle = ~120s) ---
        asana_tick += 1
        if asana_tick >= 2:
            asana_tick = 0
            for hit in _get_recent_asana_comments():
                task_name    = hit["task_name"]
                task_context = hit.get("task_context", "")
                raw_text     = hit["text"]
                clean        = raw_text.replace("@Nexa", "").strip()
                print(f"[asana] Comment on '{task_name[:50]}': {clean[:80]!r}")

                # Give Nexa the full task context so the reply is specific
                context = (
                    f"{task_context}\n\n"
                    f"Team comment: {clean}\n\n"
                    "Reply directly and specifically based on the task above. "
                    "Plain text only (no Slack markdown — this goes into Asana)."
                )
                reply = route_request(context)
                _reply_asana_comment(hit["task_gid"], reply)
                print(f"[asana] Replied to task {hit['task_gid']}")

        since = new_since
        time.sleep(60)


if __name__ == "__main__":
    run()
