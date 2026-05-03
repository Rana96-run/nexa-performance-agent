"""
Agent Workflow Definitions
==========================
Single source of truth for every role the agent plays.

When this file changes the activity dashboard auto-reflects — no Miro edits needed.

Each workflow dict has:
    id          : unique slug
    role        : display name shown in the dashboard
    emoji       : icon
    description : one-line summary
    trigger     : what kicks this off
    steps       : ordered list of step strings (shown as numbered list)
    graphviz    : GraphViz DOT string — rendered via st.graphviz_chart() (no HTML)
"""

WORKFLOWS: list[dict] = [

    # ── 1. Daily Performance Digest ─────────────────────────────────────────
    {
        "id":          "daily_digest",
        "role":        "Daily Performance Digest",
        "emoji":       "📊",
        "description": "Pulls last 14 days of BQ data, scores every campaign, posts a Slack digest, and creates Asana tasks for every action needed.",
        "trigger":     "main.py daily — 09:00 Riyadh (06:00 UTC)",
        "steps": [
            "Pull campaigns_daily + hubspot_leads_module_daily from BQ (last 14 days)",
            "Join spend → leads → SQLs; calculate CPL, CPQL, qual_rate per campaign",
            "Score each campaign: scale / acceptable / warning / pause_zone (CPQL-first)",
            "Identify top performer and worst performer per channel",
            "Draft Slack main message: dashboard URL + peak numbers with CPQL",
            "Draft follow-up: recommendations + Asana task links",
            "Post both messages to #performance-daily",
            "Create Asana tasks for every recommended action",
            "Log to agent_activity_log: posted_digest + n_campaigns + n_actions",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#7c3aed" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="09:00 Riyadh\\nmain.py daily" shape=oval fillcolor="#4c1d95"]
    bq       [label="Query BQ\\ncampaigns_daily + hubspot_leads"]
    calc     [label="Calculate CPL · CPQL · qual_rate\\nper campaign"]
    score    [label="Score campaigns" shape=diamond fillcolor="#312e81"]
    scale    [label="Scale zone\\nCPQL < 11 SAR" fillcolor="#14532d"]
    ok       [label="Acceptable\\nCPQL 11-17 SAR" fillcolor="#1e3a5f"]
    warn     [label="Warning\\nCPQL 17-21 SAR" fillcolor="#78350f"]
    pause    [label="Pause zone\\nCPQL > 21 SAR" fillcolor="#7f1d1d"]
    slack    [label="Post Slack digest\\n#performance-daily"]
    asana    [label="Create Asana tasks"]
    log      [label="log_activity:\\nposted_digest" fillcolor="#0f172a"]

    trigger -> bq -> calc -> score
    score -> scale [label="CPQL<11"]
    score -> ok    [label="11-17"]
    score -> warn  [label="17-21"]
    score -> pause [label=">21"]
    scale -> slack
    ok    -> slack
    warn  -> slack
    pause -> slack
    slack -> asana -> log
}
""",
    },

    # ── 2. Pause / Scale Watcher ─────────────────────────────────────────────
    {
        "id":          "pause_watcher",
        "role":        "Pause / Scale Watcher",
        "emoji":       "⚡",
        "description": "Monitors campaigns on a rolling 14-day window. Auto-executes pause and scale. Sends optimize/junk to #approvals.",
        "trigger":     "operational_scheduler.py — every 4 hours",
        "steps": [
            "Pull last 14 days for all active campaigns (minimum window enforced)",
            "Calculate rolling CPL and CPQL per campaign",
            "PAUSE: CPQL > 21.33 SAR for 14+ days → auto-execute, log EXECUTED:",
            "SCALE: CPQL < 11 SAR for 14+ days → auto-execute, log EXECUTED:",
            "OPTIMIZE: CPL in warning zone → post to #approvals, wait for ✅ reaction",
            "JUNK LEADS: qual_rate < 30% → drill down to keyword + audience",
            "Create Asana task with pause list and audience recommendation",
            "Log every decision to agent_activity_log",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#7c3aed" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="Every 4h\\noperational_scheduler" shape=oval fillcolor="#4c1d95"]
    pull     [label="Pull 14-day rolling window\\nall active campaigns"]
    calc     [label="Calculate CPL + CPQL"]
    decide   [label="Decision" shape=diamond fillcolor="#312e81"]
    pause    [label="AUTO PAUSE\\nlog: EXECUTED" fillcolor="#7f1d1d"]
    scale    [label="AUTO SCALE\\nlog: EXECUTED" fillcolor="#14532d"]
    optimize [label="Post to #approvals\\nwait for reaction" fillcolor="#78350f"]
    junk     [label="Drill down:\\nkeyword + audience" fillcolor="#451a03"]
    asana    [label="Create Asana task"]
    log      [label="log_activity:\\ndecision recorded" fillcolor="#0f172a"]

    trigger -> pull -> calc -> decide
    decide -> pause    [label="CPQL>21"]
    decide -> scale    [label="CPQL<11"]
    decide -> optimize [label="warning"]
    decide -> junk     [label="qual<30%"]
    junk -> asana
    pause -> log
    scale -> log
    optimize -> log
    asana -> log
}
""",
    },

    # ── 3. BQ Refresh Scheduler ──────────────────────────────────────────────
    {
        "id":          "bq_refresh",
        "role":        "BQ Refresh Scheduler",
        "emoji":       "🔄",
        "description": "Runs every 6 hours. Pulls incremental data from all ad platforms and CRM into BigQuery, then refreshes all reporting views.",
        "trigger":     "reporting_scheduler.py — 00:00 / 06:00 / 12:00 / 18:00 UTC",
        "steps": [
            "Windsor.ai collector: pulls Google, Meta, Snap, TikTok, LinkedIn, Bing in one call",
            "Direct collectors (fallback if Windsor key missing)",
            "CRM collectors: hubspot_leads_bq, hubspot_deals_bq",
            "Airbyte normalizer: airbyte_raw.* → adsets_daily, ads_daily, keywords_daily (if configured)",
            "Refresh all BQ views: campaign_performance, utm_paid_attribution_daily, v_adset_performance, v_ad_performance, v_keyword_performance",
            "Send heartbeat to #monitoring",
            "Log total rows + failed collectors to agent_activity_log",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#0ea5e9" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="Every 6h UTC\\nreporting_scheduler" shape=oval fillcolor="#0c4a6e"]
    windsor  [label="Windsor.ai\\nAll 6 channels"]
    direct   [label="Direct collectors\\n(fallback)"]
    hubspot  [label="HubSpot\\nleads + deals"]
    airbyte  [label="Airbyte normalizer\\nadsets · ads · keywords" fillcolor="#1e3a5f"]
    views    [label="Refresh all BQ views\\n5 reporting views"]
    heartbeat[label="Heartbeat\\n#monitoring"]
    log      [label="log_activity:\\nrefresh_complete" fillcolor="#0f172a"]

    trigger -> windsor
    trigger -> direct  [label="fallback" style=dashed]
    windsor -> hubspot
    direct  -> hubspot
    hubspot -> airbyte -> views -> heartbeat -> log
}
""",
    },

    # ── 4. Junk Leads Detector ───────────────────────────────────────────────
    {
        "id":          "junk_leads",
        "role":        "Junk Leads Detector",
        "emoji":       "🗑️",
        "description": "Detects campaigns with low qualification rate, drills into keyword and audience data, and creates actionable Asana tasks with specific pause recommendations.",
        "trigger":     "Called from Pause/Scale Watcher when qual_rate < 30% for 14+ days",
        "steps": [
            "Flag campaign: qual_rate < 30% over 14-day window",
            "Query v_keyword_performance: find keywords with qual% < 20% → mark PAUSE",
            "Group keywords by ad group name for actionable pause list",
            "Query v_adset_performance: find worst audience → generate replacement suggestion",
            "Build Asana task body: campaign, qual%, keyword pause list, audience recommendation",
            "Create task in Junk Leads project with mandatory footer",
            "Post notification to #approvals",
            "Log: junk_leads_detected, channel, campaign_name",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#f59e0b" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="qual_rate < 30%\\n14-day window" shape=oval fillcolor="#451a03"]
    keywords [label="Query v_keyword_performance\\nflag qual_pct < 20%"]
    group    [label="Group by ad_group\\nbuild pause list"]
    audience [label="Query v_adset_performance\\nfind worst audience"]
    suggest  [label="Generate replacement\\naudiece suggestion"]
    task     [label="Build Asana task\\ncampaign · qual% · keywords · audience"]
    create   [label="Create task\\nJunk Leads project"]
    notify   [label="Post to #approvals"]
    log      [label="log_activity:\\njunk_leads_detected" fillcolor="#0f172a"]

    trigger -> keywords -> group -> audience -> suggest -> task -> create -> notify -> log
}
""",
    },

    # ── 5. Slack Approval Handler ────────────────────────────────────────────
    {
        "id":          "slack_approvals",
        "role":        "Slack Approval Handler",
        "emoji":       "✅",
        "description": "Listens to emoji reactions on #approvals. ✅ executes the action, ❌ logs rejection. Scale and pause bypass this — they are auto-executed.",
        "trigger":     "slack_listener.py — always-on WebSocket",
        "steps": [
            "Listen for reaction_added events on #approvals",
            "Match reaction to a pending approval request (by Slack message ts)",
            "✅ reaction: parse action from message, route to correct executor",
            "❌ reaction: log rejection, no action taken",
            "Post confirmation reply to the approval thread",
            "Update Asana task: In Progress → Done (approved) or Cancelled (rejected)",
            "Log: approval_handled, action, approved_by",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#10b981" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="reaction_added event\\n#approvals" shape=oval fillcolor="#064e3b"]
    match    [label="Match to pending\\napproval request"]
    check    [label="Which reaction?" shape=diamond fillcolor="#065f46"]
    approve  [label="Parse action\\nroute to executor" fillcolor="#14532d"]
    reject   [label="Log rejection\\nno action" fillcolor="#7f1d1d"]
    confirm  [label="Post confirmation\\nto approval thread"]
    asana    [label="Update Asana task\\nDone / Cancelled"]
    log      [label="log_activity:\\napproval_handled" fillcolor="#0f172a"]

    trigger -> match -> check
    check -> approve [label="✅"]
    check -> reject  [label="❌"]
    approve -> confirm
    reject  -> confirm
    confirm -> asana -> log
}
""",
    },

    # ── 6. Airbyte Normalizer ────────────────────────────────────────────────
    {
        "id":          "airbyte_normalizer",
        "role":        "Airbyte Normalizer",
        "emoji":       "🔗",
        "description": "Reads raw data Airbyte writes into BigQuery and normalises it into adsets_daily, ads_daily, keywords_daily tables.",
        "trigger":     "Called from BQ Refresh Scheduler when AIRBYTE_RAW_DATASET env var is set",
        "steps": [
            "Check AIRBYTE_RAW_DATASET env var — skip entirely if not set",
            "For each channel (google, meta, snap, tiktok, linkedin, microsoft):",
            "  Read raw table from airbyte_raw dataset",
            "  Map raw column names to canonical schema",
            "  MERGE into campaigns_daily on (date, channel, campaign_id)",
            "Google Ads: also normalise ad groups → adsets_daily, keywords → keywords_daily",
            "Meta: also normalise ad sets → adsets_daily, ads → ads_daily",
            "Return {channel: rows_merged} dict for heartbeat",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#3b82f6" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="BQ Refresh calls\\nrun_all_normalizations" shape=oval fillcolor="#1e3a5f"]
    check    [label="AIRBYTE_RAW_DATASET\\nset?" shape=diamond fillcolor="#1e40af"]
    skip     [label="Skip — return {}" fillcolor="#0f172a"]
    read     [label="Read airbyte_raw\\nfor each channel"]
    map      [label="Map columns\\nto canonical schema"]
    merge    [label="MERGE into\\ncampaigns_daily"]
    sub      [label="Sub-campaign\\nGoogle/Meta only?" shape=diamond fillcolor="#1e40af"]
    adsets   [label="→ adsets_daily\\n→ keywords_daily\\n→ ads_daily"]
    done     [label="Return rows_merged\\nper channel" fillcolor="#0f172a"]

    trigger -> check
    check -> skip  [label="no"]
    check -> read  [label="yes"]
    read -> map -> merge -> sub
    sub -> adsets [label="yes"]
    sub -> done   [label="no"]
    adsets -> done
}
""",
    },

    # ── 7. Campaign Creator ──────────────────────────────────────────────────
    {
        "id":          "campaign_creator",
        "role":        "Campaign Creator",
        "emoji":       "🚀",
        "description": "Creates campaigns from Asana briefs. Validates naming convention, selects correct pixels, and launches via platform APIs.",
        "trigger":     "Asana task moves to 'Ready to Launch' column",
        "steps": [
            "Read Asana task: channel, type, language, product, audience, budget, start date",
            "Validate naming convention via executors/naming.py — raises ValueError on bad audience",
            "Normalise product: einvoice→Invoice, qbookkeeping→Bookkeeping, etc.",
            "Meta: select both pixels (Qoyod_CRM_PIXEL + Qoyod_Web_PIXEL)",
            "Google: select correct conversion action",
            "Call platform API via Adspirer MCP or direct executor",
            "Write new campaign_id to campaigns_daily (status=LEARNING)",
            "Update Asana task: Launched + campaign ID",
            "Log: campaign_created, channel, campaign_name",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#8b5cf6" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="Asana task →\\nReady to Launch" shape=oval fillcolor="#2e1065"]
    parse    [label="Parse brief\\nchannel · type · language · product · audience"]
    validate [label="Validate naming\\nexecutors/naming.py" shape=diamond fillcolor="#3b0764"]
    error    [label="Post error to Asana\\nask for correction" fillcolor="#7f1d1d"]
    normalise[label="Normalise product name"]
    channel  [label="Channel setup" shape=diamond fillcolor="#3b0764"]
    meta     [label="Select both pixels\\nCRM + Web"]
    google   [label="Select conversion\\naction"]
    api      [label="Call platform API\\nAdspirer MCP"]
    write    [label="Write to campaigns_daily\\nstatus=LEARNING"]
    update   [label="Update Asana:\\nLaunched + campaign_id"]
    log      [label="log_activity:\\ncampaign_created" fillcolor="#0f172a"]

    trigger -> parse -> validate
    validate -> error  [label="invalid"]
    validate -> normalise [label="valid"]
    normalise -> channel
    channel -> meta   [label="Meta"]
    channel -> google [label="Google"]
    meta -> api
    google -> api
    api -> write -> update -> log
}
""",
    },

    # ── 8. Asana Task Creator ────────────────────────────────────────────────
    {
        "id":          "asana_creator",
        "role":        "Asana Task Creator",
        "emoji":       "📋",
        "description": "Creates structured Asana tasks for every agent action. Every task ends with the mandatory footer: Created, Due, Priority, Type, Channel, Asset level, Action.",
        "trigger":     "Called from daily_digest and pause_watcher after every decision",
        "steps": [
            "Determine project: Paid Performance, Junk Leads, or Campaign Launches",
            "Build task title: [Channel] [Action] — [Campaign Name]",
            "Build task body: context + data + specific recommendation",
            "Append mandatory footer: Created / Due / Priority / Type / Channel / Asset level / Action",
            "Set assignee, due date, section based on action type",
            "POST to Asana API",
            "Return task URL for inclusion in Slack message",
            "Log: asana_task_created, channel, campaign_name",
        ],
        "graphviz": """
digraph {
    rankdir=TB
    node [shape=box style="rounded,filled" fillcolor="#1e293b" color="#f97316" fontcolor="white" fontname="Helvetica"]
    edge [color="#94a3b8" fontcolor="#94a3b8" fontname="Helvetica" fontsize=10]

    trigger  [label="Called by digest\\nor pause_watcher" shape=oval fillcolor="#431407"]
    project  [label="Choose project" shape=diamond fillcolor="#7c2d12"]
    perf     [label="Paid Performance"]
    junk     [label="Junk Leads"]
    launch   [label="Campaign Launches"]
    title    [label="Build task title\\nChannel · Action · Campaign"]
    body     [label="Build task body\\ncontext + data + recommendation"]
    footer   [label="Append mandatory footer\\nCreated · Due · Priority · Type · Channel · Level · Action"]
    post     [label="POST to Asana API"]
    url      [label="Return task URL\\nfor Slack message"]
    log      [label="log_activity:\\nasana_task_created" fillcolor="#0f172a"]

    trigger -> project
    project -> perf   [label="scale/pause/optimize"]
    project -> junk   [label="junk leads"]
    project -> launch [label="new campaign"]
    perf -> title
    junk -> title
    launch -> title
    title -> body -> footer -> post -> url -> log
}
""",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_workflow(workflow_id: str) -> dict | None:
    return next((w for w in WORKFLOWS if w["id"] == workflow_id), None)


def get_all_roles() -> list[str]:
    return [w["id"] for w in WORKFLOWS]
