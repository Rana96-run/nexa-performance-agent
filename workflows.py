"""
Agent Workflow Definitions
==========================
Single source of truth for every role the agent plays.

When this file changes the dashboard auto-reflects — no Miro edits needed.

Each workflow dict has:
    id          : unique slug used as URL anchor
    role        : display name
    emoji       : icon shown in the card header
    description : one-line summary
    trigger     : what kicks this off
    steps       : ordered list of step strings
    mermaid     : Mermaid flowchart definition (rendered in dashboard)
    bq_query    : optional SQL to show recent activity for this role
"""

WORKFLOWS: list[dict] = [

    # ── 1. Daily Performance Digest ─────────────────────────────────────────
    {
        "id":          "daily_digest",
        "role":        "Daily Performance Digest",
        "emoji":       "📊",
        "description": "Pulls last 14 days of BQ data, scores every campaign, posts a structured Slack digest, and creates Asana tasks for every action needed.",
        "trigger":     "main.py daily — runs at 09:00 Riyadh time every day",
        "steps": [
            "Pull campaigns_daily + hubspot_leads_module_daily from BQ (last 14 days)",
            "Join spend → leads → SQLs; calculate CPL, CPQL, qual_rate per campaign",
            "Score each campaign: scale / acceptable / warning / pause_zone",
            "Identify top performer and worst performer per channel",
            "Draft Slack main message: dashboard URL + peak numbers (CPQL-first)",
            "Draft follow-up message: recommendations + Asana task links",
            "Post both messages to #performance-daily",
            "Create Asana tasks for every recommended action",
            "Log activity: posted_digest + n_campaigns + n_actions",
        ],
        "mermaid": """
flowchart TD
    A([🕘 09:00 Riyadh — main.py daily]) --> B[Query BQ\\ncampaigns_daily + hubspot_leads]
    B --> C[Join spend→leads→SQLs\\ncalculate CPL · CPQL · qual_rate]
    C --> D{Score each campaign}
    D --> D1[🟢 Scale zone\\nCPQL < 11 SAR]
    D --> D2[🟡 Acceptable\\nCPQL 11–17 SAR]
    D --> D3[🟠 Warning\\nCPQL 17–21 SAR]
    D --> D4[🔴 Pause zone\\nCPQL > 21 SAR]
    D1 & D2 & D3 & D4 --> E[Pick top + worst per channel]
    E --> F[Draft Slack digest\\nmain msg + follow-up]
    F --> G[Post to #performance-daily]
    G --> H[Create Asana tasks\\nfor every recommended action]
    H --> I[log_activity: posted_digest]
""",
    },

    # ── 2. Pause / Scale Watcher ─────────────────────────────────────────────
    {
        "id":          "pause_watcher",
        "role":        "Pause / Scale Watcher",
        "emoji":       "⚡",
        "description": "Monitors campaigns on a rolling 14-day window. Auto-executes pause and scale without approval. Sends optimize/junk decisions to #approvals.",
        "trigger":     "operational_scheduler.py — checks every 4 hours",
        "steps": [
            "Pull last 14 days for all active campaigns (minimum window = 14 days)",
            "Calculate rolling CPL and CPQL",
            "Pause: CPQL > CPQL_WARNING threshold for 14+ days → auto-execute, log EXECUTED:",
            "Scale: CPQL < CPQL_SCALE threshold for 14+ days → auto-execute, log EXECUTED:",
            "Optimize: CPL in warning zone → post to #approvals, wait for reaction",
            "Junk leads: qual_rate < 30% → drill down to keyword/audience → create Asana task",
            "Log every decision to agent_activity_log",
        ],
        "mermaid": """
flowchart TD
    A([⏰ Every 4h — operational_scheduler]) --> B[Pull 14-day rolling window\\nall active campaigns]
    B --> C[Calculate CPL + CPQL per campaign]
    C --> D{Decision logic}
    D -->|CPQL > 21.33 SAR| E[🔴 PAUSE]
    D -->|CPQL < 11 SAR| F[🟢 SCALE]
    D -->|CPL warning zone| G[🟡 OPTIMIZE]
    D -->|qual_rate < 30%| H[🗑️ JUNK LEADS]
    E --> E1[Auto-execute pause\\nlog: EXECUTED: paused]
    F --> F1[Auto-execute scale\\nlog: EXECUTED: scaled]
    G --> G1[Post to #approvals\\nwait for ✅ reaction]
    H --> H1[Drill down to\\nkeyword + audience]
    H1 --> H2[Create Asana task\\nwith pause list]
    G1 -->|approved| G2[Execute optimization]
    G1 -->|rejected| G3[Log: rejected, skip]
    E1 & F1 & G2 & G3 & H2 --> Z[log_activity: decision recorded]
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
            "Direct collectors (fallback if Windsor key missing): google_ads, meta, snap, tiktok, linkedin, microsoft_ads",
            "Organic: meta_organic, youtube, linkedin organic",
            "CRM: hubspot_leads_bq, hubspot_deals_bq",
            "Airbyte normalizer: reads airbyte_raw.* → MERGEs into adsets_daily, ads_daily, keywords_daily",
            "Refresh all BQ views: campaign_performance, utm_paid_attribution_daily, v_adset_performance, v_ad_performance, v_keyword_performance",
            "Send heartbeat to Slack #monitoring",
            "Log total rows + failed collectors to agent_activity_log",
        ],
        "mermaid": """
flowchart TD
    A([⏰ Every 6h UTC — reporting_scheduler]) --> B{Windsor key set?}
    B -->|yes| C[Windsor.ai\\nGoogle·Meta·Snap·TikTok·LinkedIn·Bing]
    B -->|no| D[Direct collectors\\nper-platform APIs]
    C & D --> E[HubSpot collectors\\nleads + deals]
    E --> F{AIRBYTE_RAW_DATASET set?}
    F -->|yes| G[Airbyte normalizer\\nairbyte_raw → adsets/ads/keywords]
    F -->|no| H[Skip Airbyte\\nuse UTM proxy]
    G & H --> I[Refresh all BQ views\\ncampaign_performance + 3 sub-grain views]
    I --> J[Send heartbeat\\n#monitoring]
    J --> K[log_activity: bq_refresh complete\\nn rows · n failed]
""",
    },

    # ── 4. Junk Leads Detector ───────────────────────────────────────────────
    {
        "id":          "junk_leads",
        "role":        "Junk Leads Detector",
        "emoji":       "🗑️",
        "description": "Detects campaigns with low qualification rate, drills into keyword and audience data from BQ, and creates actionable Asana tasks with specific pause recommendations.",
        "trigger":     "Called from pause_watcher when qual_rate < 30% for 14+ days",
        "steps": [
            "Flag campaign: qual_rate < 30% over 14-day window",
            "Query v_keyword_performance: find keywords with qual% < 20% → mark PAUSE",
            "Query v_adset_performance: find worst audience → suggest replacement",
            "Build Asana task body: campaign name, qual%, keyword pause list by ad group, audience recommendation",
            "Create task in 'Junk Leads' Asana project with correct footer",
            "Post notification to #approvals for review",
            "Log: junk_leads_detected, channel, campaign_name",
        ],
        "mermaid": """
flowchart TD
    A([Trigger: qual_rate < 30% — 14 days]) --> B[Query v_keyword_performance\\nfilter qual_pct < 20%]
    B --> C[Group by adgroup_name\\nbuild keyword pause list]
    C --> D[Query v_adset_performance\\nfind worst audience]
    D --> E[Generate replacement suggestion\\nbased on audience type]
    E --> F[Build Asana task\\ncampaign · qual% · keyword list · audience rec]
    F --> G[Create task in\\nJunk Leads project]
    G --> H[Post to #approvals]
    H --> I[log_activity: junk_leads_detected]
""",
    },

    # ── 5. Slack Approval Handler ────────────────────────────────────────────
    {
        "id":          "slack_approvals",
        "role":        "Slack Approval Handler",
        "emoji":       "✅",
        "description": "Listens to emoji reactions on #approvals messages. ✅ triggers execution, ❌ logs rejection. Scale and pause are auto-executed without this flow.",
        "trigger":     "slack_listener.py — always-on WebSocket connection",
        "steps": [
            "Listen for reaction_added events on #approvals channel",
            "Match reaction to pending approval request (by message ts)",
            "✅ reaction: extract action from message, execute it via the relevant executor",
            "❌ reaction: log rejection, no action taken",
            "Post confirmation reply to the approval thread",
            "Update Asana task status: In Progress → Done (if approved) or Cancelled (if rejected)",
            "Log: approval_handled, action, approved_by",
        ],
        "mermaid": """
flowchart TD
    A([slack_listener.py — always-on]) --> B[reaction_added event\\non #approvals]
    B --> C{Which reaction?}
    C -->|✅| D[Parse action from message]
    C -->|❌| E[Log rejection]
    D --> F{Action type}
    F -->|optimize_bid| G[Call Google/Meta API\\nadjust bid strategy]
    F -->|update_creative| H[Flag in Asana\\nfor creative team]
    F -->|other| I[Route to correct executor]
    G & H & I --> J[Post confirmation\\nto approval thread]
    J --> K[Update Asana task\\nDone / Cancelled]
    K --> L[log_activity: approval_handled]
    E --> L
""",
    },

    # ── 6. Airbyte Normalizer ────────────────────────────────────────────────
    {
        "id":          "airbyte_normalizer",
        "role":        "Airbyte Normalizer",
        "emoji":       "🔗",
        "description": "Reads raw data Airbyte writes into BigQuery and normalises it into the canonical adsets_daily, ads_daily, keywords_daily tables.",
        "trigger":     "Called from reporting_scheduler after direct collectors, when AIRBYTE_RAW_DATASET env var is set",
        "steps": [
            "Check AIRBYTE_RAW_DATASET env var — skip entirely if not set",
            "For each channel (google_ads, meta, snap, tiktok, linkedin, microsoft_ads):",
            "  Read raw table from airbyte_raw dataset",
            "  Map raw column names to canonical schema",
            "  MERGE into campaigns_daily on (date, channel, campaign_id)",
            "For Google Ads: also normalise ad groups → adsets_daily, keywords → keywords_daily",
            "For Meta: also normalise ad sets → adsets_daily, ads → ads_daily",
            "Return dict of {channel: rows_merged} for heartbeat",
        ],
        "mermaid": """
flowchart TD
    A([reporting_scheduler calls run_all_normalizations]) --> B{AIRBYTE_RAW_DATASET set?}
    B -->|no| Z[Skip — return empty dict]
    B -->|yes| C[For each channel\\ngoogle·meta·snap·tiktok·linkedin·bing]
    C --> D[Read airbyte_raw.channel_table]
    D --> E[Map columns → canonical schema]
    E --> F[MERGE into campaigns_daily\\non date+channel+campaign_id]
    F --> G{Has sub-campaign data?}
    G -->|Google Ads| H[Normalise ad groups\\n→ adsets_daily]
    H --> H2[Normalise keywords\\n→ keywords_daily]
    G -->|Meta| I[Normalise ad sets\\n→ adsets_daily]
    I --> I2[Normalise ads\\n→ ads_daily]
    G -->|other channels| J[Campaign level only]
    H2 & I2 & J --> K[Return rows_merged per channel]
""",
    },

    # ── 7. Campaign Creator ──────────────────────────────────────────────────
    {
        "id":          "campaign_creator",
        "role":        "Campaign Creator",
        "emoji":       "🚀",
        "description": "Creates new campaigns from Asana briefs. Validates naming convention, selects correct pixels, and launches via platform APIs.",
        "trigger":     "Asana task moves to 'Ready to Launch' column in the Campaigns project",
        "steps": [
            "Read Asana task: channel, type, language, product, audience, budget, start date",
            "Validate naming: executors/naming.py::prefixed() — raises ValueError on bad audience",
            "Normalise product: einvoice→Invoice, qbookkeeping→Bookkeeping, etc.",
            "For Meta: select both pixels (Qoyod_CRM + Qoyod_Web)",
            "For Google: select correct conversion action",
            "Call platform API via Adspirer MCP or direct executor",
            "Write new campaign_id to campaigns_daily (status=LEARNING)",
            "Update Asana task: Launched + campaign ID in description",
            "Log: campaign_created, channel, campaign_name",
        ],
        "mermaid": """
flowchart TD
    A([Asana task → 'Ready to Launch']) --> B[Parse brief\\nchannel · type · language · product · audience]
    B --> C[Validate naming convention\\nexecutors/naming.py]
    C --> D{Valid?}
    D -->|ValueError| E[Post error to Asana task\\nask for correction]
    D -->|OK| F[Normalise product name]
    F --> G{Which channel?}
    G -->|Meta| H[Select both pixels\\nCRM + Web]
    G -->|Google| I[Select conversion action]
    G -->|other| J[Standard setup]
    H & I & J --> K[Call platform API\\nvia Adspirer MCP]
    K --> L[Write to campaigns_daily\\nstatus=LEARNING]
    L --> M[Update Asana: Launched + campaign_id]
    M --> N[log_activity: campaign_created]
""",
    },

    # ── 8. Asana Task Creator ────────────────────────────────────────────────
    {
        "id":          "asana_creator",
        "role":        "Asana Task Creator",
        "emoji":       "📋",
        "description": "Creates structured Asana tasks for every agent action. Every task has the mandatory footer: Created, Due, Priority, Type, Channel, Asset level, Action.",
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
        "mermaid": """
flowchart TD
    A([Called by digest or pause_watcher]) --> B{Action type}
    B -->|pause| C[Project: Paid Performance\\nSection: To Pause]
    B -->|scale| D[Project: Paid Performance\\nSection: To Scale]
    B -->|junk leads| E[Project: Junk Leads]
    B -->|optimize| F[Project: Paid Performance\\nSection: Optimise]
    C & D & E & F --> G[Build task title\\nChannel · Action · Campaign]
    G --> H[Build task body\\ncontext + data + recommendation]
    H --> I[Append mandatory footer\\nCreated · Due · Priority · Type · Channel · Level · Action]
    I --> J[Set assignee + due date]
    J --> K[POST to Asana API]
    K --> L[Return task URL]
    L --> M[log_activity: asana_task_created]
""",
    },
]


# ── Helper: get workflow by id ────────────────────────────────────────────────

def get_workflow(workflow_id: str) -> dict | None:
    """Return a workflow dict by its id, or None if not found."""
    return next((w for w in WORKFLOWS if w["id"] == workflow_id), None)


def get_all_roles() -> list[str]:
    """Return list of all role IDs."""
    return [w["id"] for w in WORKFLOWS]
