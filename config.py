import os
from dotenv import load_dotenv

load_dotenv()

# Google Ads
GOOGLE_ADS_CONFIG = {
    "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
    "client_id": os.getenv("GOOGLE_ADS_CLIENT_ID"),
    "client_secret": os.getenv("GOOGLE_ADS_CLIENT_SECRET"),
    "refresh_token": os.getenv("GOOGLE_ADS_REFRESH_TOKEN"),
    "login_customer_id": "5789762982",   # MCC - no dashes
    "customer_id": "1513020554",          # Active account - no dashes
}

# Meta
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_AD_ACCOUNTS = [
    os.getenv("META_AD_ACCOUNT_1"),  # act_1366192231206913
    os.getenv("META_AD_ACCOUNT_2"),  # act_835030860363827
]

# HubSpot
HUBSPOT_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Slack
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN") or os.getenv("SLACK_ACCESS_TOKEN")
# Two purpose-split channels. Falls back to legacy SLACK_CHANNEL_ID if not set.
SLACK_CHANNEL_NOTIFY = os.getenv("SLACK_CHANNEL_NOTIFY") or os.getenv("SLACK_CHANNEL_ID")
SLACK_CHANNEL_APPROVAL = os.getenv("SLACK_CHANNEL_APPROVAL") or os.getenv("SLACK_CHANNEL_ID")
# Health channel: where heartbeat beacons from the schedulers land.
# If missing, heartbeats fall back to the notify channel (still better than silence).
SLACK_CHANNEL_HEALTH = os.getenv("SLACK_CHANNEL_HEALTH") or SLACK_CHANNEL_NOTIFY
SLACK_CHANNEL_ID = SLACK_CHANNEL_NOTIFY  # legacy alias

# Notification backend: 'slack', 'email', or 'both'. Default 'email' while Slack is being set up.
NOTIFY_VIA = os.getenv("NOTIFY_VIA", "email").lower()

# Asana
ASANA_TOKEN        = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_ASSIGNEE_GID = os.getenv("ASANA_ASSIGNEE_GID", "")   # legacy fallback

# Per-person Asana GIDs — sourced from Railway env vars
# Add new team members here + in Railway; no code change needed
ASANA_ASSIGNEE_GOOGLE_ADS_GID = os.getenv("ASANA_ASSIGNEE_GOOGLE_ADS_GID", "1208007704598388")  # Rana Khalid
ASANA_ASSIGNEE_DEFAULT_GID    = os.getenv("ASANA_ASSIGNEE_DEFAULT_GID",    "1211896896006183")  # Donia Mohamed
ASANA_ASSIGNEE_DONIA_GID      = os.getenv("ASANA_ASSIGNEE_DONIA",          "1211896896006183")  # Donia Mohamed (explicit)
ASANA_ASSIGNEE_RANA_GID       = os.getenv("ASANA_ASSIGNEE_RANA",           "1208007704598388")  # Rana Khalid (explicit)

# ── Agent identity map ─────────────────────────────────────────────────────────
# Single source of truth for every agent's display name, Slack persona, and
# Asana assignee GID.  Add a new agent here; routing in asana.py + slack.py
# reads from this dict — no other files need changing.
#
# log_role keys match agent_activity_log.role values.  Each entry has:
#   display_name  — human-readable label shown in Asana task descriptions
#   slack_name    — bot username used in chat_postMessage (visible in Slack)
#   slack_emoji   — icon_emoji for that persona
#   asana_gid     — Asana user GID to assign tasks to (None = unassigned)
#
# To override a GID without a code deploy: set ASANA_ASSIGNEE_<ROLE> in Railway.
AGENT_IDENTITY: dict[str, dict] = {
    # ── AI Orchestrator (manager) ─────────────────────────────────────────────
    "ops_scheduler":   {"display_name": "AI Orchestrator",     "slack_name": "Nexa · Orchestrator",  "slack_emoji": ":robot_face:",      "asana_gid": os.getenv("ASANA_ASSIGNEE_ORCHESTRATOR",   ASANA_ASSIGNEE_RANA_GID)},
    "daily_digest":    {"display_name": "AI Orchestrator",     "slack_name": "Nexa · Orchestrator",  "slack_emoji": ":robot_face:",      "asana_gid": os.getenv("ASANA_ASSIGNEE_ORCHESTRATOR",   ASANA_ASSIGNEE_RANA_GID)},
    "task_creator":    {"display_name": "AI Orchestrator",     "slack_name": "Nexa · Orchestrator",  "slack_emoji": ":robot_face:",      "asana_gid": os.getenv("ASANA_ASSIGNEE_ORCHESTRATOR",   ASANA_ASSIGNEE_RANA_GID)},
    # ── Performance Lead ──────────────────────────────────────────────────────
    "performance_audit":       {"display_name": "Performance Lead",    "slack_name": "Nexa · Performance Lead",  "slack_emoji": ":bar_chart:",        "asana_gid": os.getenv("ASANA_ASSIGNEE_PERFORMANCE_LEAD", ASANA_ASSIGNEE_DEFAULT_GID)},
    "paid_media_strategist":   {"display_name": "Performance Lead",    "slack_name": "Nexa · Performance Lead",  "slack_emoji": ":bar_chart:",        "asana_gid": os.getenv("ASANA_ASSIGNEE_PERFORMANCE_LEAD", ASANA_ASSIGNEE_DEFAULT_GID)},
    # ── Campaign Manager ──────────────────────────────────────────────────────
    "campaign_creator":        {"display_name": "Campaign Manager",    "slack_name": "Nexa · Campaign Manager", "slack_emoji": ":mega:",             "asana_gid": os.getenv("ASANA_ASSIGNEE_CAMPAIGN_MANAGER", ASANA_ASSIGNEE_RANA_GID)},
    "keyword_management":      {"display_name": "Campaign Manager",    "slack_name": "Nexa · Campaign Manager", "slack_emoji": ":mega:",             "asana_gid": os.getenv("ASANA_ASSIGNEE_CAMPAIGN_MANAGER", ASANA_ASSIGNEE_RANA_GID)},
    # ── Marketing Ops ─────────────────────────────────────────────────────────
    "health_monitor":          {"display_name": "Marketing Ops",       "slack_name": "Nexa · Marketing Ops",    "slack_emoji": ":wrench:",           "asana_gid": os.getenv("ASANA_ASSIGNEE_MARKETING_OPS",    ASANA_ASSIGNEE_DEFAULT_GID)},
    "collector":               {"display_name": "Marketing Ops",       "slack_name": "Nexa · Marketing Ops",    "slack_emoji": ":wrench:",           "asana_gid": os.getenv("ASANA_ASSIGNEE_MARKETING_OPS",    ASANA_ASSIGNEE_DEFAULT_GID)},
    # ── Growth Analyst ────────────────────────────────────────────────────────
    "bq_refresh":              {"display_name": "Growth Analyst",      "slack_name": "Nexa · Growth Analyst",   "slack_emoji": ":mag:",              "asana_gid": os.getenv("ASANA_ASSIGNEE_GROWTH_ANALYST",   ASANA_ASSIGNEE_RANA_GID)},
    "spike_detector":          {"display_name": "Growth Analyst",      "slack_name": "Nexa · Growth Analyst",   "slack_emoji": ":mag:",              "asana_gid": os.getenv("ASANA_ASSIGNEE_GROWTH_ANALYST",   ASANA_ASSIGNEE_RANA_GID)},
    "llm_cadence":             {"display_name": "Growth Analyst",      "slack_name": "Nexa · Growth Analyst",   "slack_emoji": ":mag:",              "asana_gid": os.getenv("ASANA_ASSIGNEE_GROWTH_ANALYST",   ASANA_ASSIGNEE_RANA_GID)},
    # ── fallback ──────────────────────────────────────────────────────────────
    "default":                 {"display_name": "Nexa Agent",          "slack_name": "Nexa",                    "slack_emoji": ":sparkles:",         "asana_gid": ASANA_ASSIGNEE_DEFAULT_GID},
}

def agent_identity(log_role: str) -> dict:
    """Return the identity dict for a log-role. Falls back to 'default'."""
    return AGENT_IDENTITY.get(log_role) or AGENT_IDENTITY["default"]
ASANA_PROJECTS = {
    "daily_activity": os.getenv("ASANA_PROJECT_DAILY_ACTIVITY") or os.getenv("ASANA_PORTFOLIO_DAILY_ACTIVITY") or "1213280681364571",  # Daily Activity portfolio (confirmed 2026-05-11)
    "optimization":   os.getenv("ASANA_PROJECT_OPTIMIZATION")   or os.getenv("ASANA_PORTFOLIO_OPTIMIZATION")   or "1213239417965392",  # Optimization portfolio (confirmed 2026-05-11)
"seasonal":       os.getenv("ASANA_PROJECT_SEASONAL")       or os.getenv("ASANA_PORTFOLIO_SEASONAL"),
}

# Microsoft Ads
MS_DEVELOPER_TOKEN = os.getenv("MS_DEVELOPER_TOKEN")
MS_CLIENT_ID       = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET   = os.getenv("MS_CLIENT_SECRET")
MS_TENANT_ID       = os.getenv("MS_TENANT_ID")
MS_CUSTOMER_ID     = os.getenv("MS_CUSTOMER_ID")
MS_ACCOUNT_ID      = os.getenv("MS_ACCOUNT_ID")
MS_REFRESH_TOKEN   = os.getenv("MS_REFRESH_TOKEN", "")

# Snapchat
SNAPCHAT_CLIENT_ID     = os.getenv("SNAPCHAT_CLIENT_ID")
SNAPCHAT_CLIENT_SECRET = os.getenv("SNAPCHAT_CLIENT_SECRET")
SNAPCHAT_REFRESH_TOKEN = os.getenv("SNAPCHAT_REFRESH_TOKEN")

# LinkedIn
LI_ACCESS_TOKEN  = os.getenv("LI_ACCESS_TOKEN")
LI_AD_ACCOUNT_URN = os.getenv("LI_AD_ACCOUNT_URN")

# Databox Push API — custom metrics destination
DATABOX_TOKEN = os.getenv("DATABOX_TOKEN", "")

# Asana per-channel display labels (used as the prefix in section names).
ASANA_CHANNEL_LABELS = {
    "google_ads":    "Google Ads",
    "meta":          "Meta",
    "snapchat":      "Snapchat",
    "linkedin":      "LinkedIn",
    "microsoft_ads": "Microsoft",
    "tiktok":        "TikTok",
    "youtube":       "YouTube",
    "hubspot":       "HubSpot / CRM",
    "general":       "General",
}

# ──────────────────────────────────────────────────────────────────────────────
# Asana project routing — Performance Marketing portfolios
# ──────────────────────────────────────────────────────────────────────────────
# Channel optimization tasks land in the per-channel project under the
# Optimization portfolio.
ASANA_OPTIMIZATION_PROJECTS = {
    "google_ads":    "1213239419217795",   # Google Ads Optimization (Recovery)
    "meta":          "1213280413868927",   # Meta Ads (Recovery)
    "snapchat":      "1214135546324721",   # Snapchat Ads Optimization
    "tiktok":        "1214135614950965",   # TikTok Ads Optimization
    "linkedin":      "1214135614968862",   # LinkedIn Ads Optimization
    "youtube":       "1214135614991277",   # YouTube Ads Optimization
    "microsoft_ads": "1213294555250809",   # Bing Ads Scaling
}

# Daily Activity tasks land in the function-specific project.
ASANA_DAILY_PROJECTS = {
    "performance":  "1214135581886045",   # Daily Performance Review (default)
    "budget":       "1214135615047733",   # Budget Pacing & Alerts
    "creative":     "1214135615054862",   # Creative Refresh & QA
    "keyword":      "1214135581961690",   # Keyword & Placement Audit
    "tracking":     "1214135615075674",   # Conversion Tracking & CRM Sync
    "competitor":   "1214135604475705",   # Competitive & Market Monitoring
}

# Seasonal campaigns — when a task is seasonal, route to the right campaign.
ASANA_SEASONAL_PROJECTS = {
    "national_day":  "1214135696742177",   # National Day Campaign (Sep)
    "founding_day":  "1213285141717446",   # Founding Day 2026
    "q_flavours":    "1213968030724875",   # Q Flavours
    "q_bookkeeping": "1213294657591156",   # Q Bookkeeping 2026
    "eoy":           "1214135614983362",   # End of Year Campaign (EOY)
}

# Active seasonal campaign — the agent uses this when it generates a seasonal
# task without specifying which campaign. Update as the calendar rolls.
ASANA_ACTIVE_SEASONAL = "national_day"

# Asset levels at which a paid-media action can apply. Each channel uses its
# own platform name (Ad Set vs Ad Group vs Ad Squad). The prompt + extractor
# normalise to one of these slugs.
ASANA_ASSET_LEVEL_LABELS = {
    "campaign":   "Campaign",
    "adset":      "Ad Set / Group",      # Meta=Ad Set, Google/MS=Ad Group, Snap=Ad Squad, TikTok=Ad Group
    "ad":         "Ad",                   # creative-level
    "audience":   "Audience",             # targeting / lookalike / retargeting
    "tracking":   "Tracking",             # UTMs, pixels, CAPI, attribution
    "keyword":    "Keyword",              # Google Ads / Microsoft only
}

# What channels support which asset levels (so we don't auto-create
# "Snapchat — Keyword" sections that don't make sense).
ASANA_CHANNEL_ASSET_MATRIX = {
    "google_ads":    ["campaign", "adset", "ad", "audience", "tracking", "keyword"],
    "meta":          ["campaign", "adset", "ad", "audience", "tracking"],
    "snapchat":      ["campaign", "adset", "ad", "audience", "tracking"],
    "tiktok":        ["campaign", "adset", "ad", "audience", "tracking"],
    "linkedin":      ["campaign", "ad", "audience", "tracking"],
    "microsoft_ads": ["campaign", "adset", "ad", "audience", "tracking", "keyword"],
    "hubspot":       ["tracking"],
    "general":       [],
}

# Section name format used inside the Optimization project: "Channel — Level"
# e.g. "Google Ads — Campaign", "Meta — Ad", "Snapchat — Audience"
def asana_section_name(channel: str, asset_level: str = "") -> str:
    chan = ASANA_CHANNEL_LABELS.get(channel, channel)
    if not asset_level:
        return chan
    lvl = ASANA_ASSET_LEVEL_LABELS.get(asset_level, asset_level)
    return f"{chan} — {lvl}"

# Backward-compat alias used by older imports
ASANA_CHANNEL_SECTIONS = ASANA_CHANNEL_LABELS

# ---------------------------------------------------------------------------
# Currency (single source of truth)
# ---------------------------------------------------------------------------
# All reporting is in USD. SAR is pegged to USD at 3.75 by the Saudi Central
# Bank (since 1986). If that peg ever changes, this is the only line to edit.
REPORTING_CURRENCY = "USD"
DEFAULT_NATIVE_CURRENCY = "SAR"
USD_SAR_PEG = 3.75   # 1 USD = 3.75 SAR

# ---------------------------------------------------------------------------
# KPI thresholds — all in USD (per playbook in qoyod-manager-os.md)
# ---------------------------------------------------------------------------
# *** CANONICAL pause/scale thresholds — campaign level ***
#
# CPQL is the PRIMARY KPI for all pause/scale decisions. CPL is secondary
# support context only. Decision tree in analysers/campaign_health.py uses
# CPQL zones first; CPL is consulted as a tie-breaker / supporting signal.
#
# Switched primacy on 2026-05-17 after the May 2026 incident: lp.qoyod.com/
# accounting had $46 CPL (same as HubSpot LPs) so it looked fine on CPL, but
# CPQL was $246. CPL gave a green light while CPQL was alarming — team kept
# scaling because the dashboard led with CPL.

# CPQL (cost per qualified lead) zones, USD — campaign level — PRIMARY KPI
CPQL_SCALE      = 60.00   # < this  -> scale up
CPQL_ACCEPTABLE = 80.00   # ≤ this  -> acceptable
CPQL_WARNING    = 95.00   # ≤ this  -> warning
CPQL_PAUSE      = 100.00  # > this  -> pause candidate

# CPL (cost per lead) zones, USD — campaign level — SECONDARY support metric
CPL_SCALE      = 25.00  # < this  -> scale up
CPL_ACCEPTABLE = 35.00  # ≤ this  -> acceptable
CPL_WARNING    = 40.00  # ≤ this  -> warning
CPL_PAUSE      = 45.00  # > this  -> pause candidate
# backwards-compat alias (some callers check CPL_PAUSE as the single trigger)

# Lag-aware CPQL reporting — see analysers/lag_aware.py.
# Days where (open_leads / leads_total) exceeds this fraction are considered
# "lag-affected" and excluded from CPQL math. Set on 2026-05-17 after May 15-16
# CPQL of $2,801 / $1,373 turned out to be 90%+ open leads (SDR backlog), not
# real performance crashes.
LAG_OPEN_PCT_THRESHOLD = 0.30

# Ad-level CPL/CPQL zones, USD
# Slightly more lenient than campaign level — individual ads can spike before
# the campaign average does. Used by bulk_ads.py and ad-level health checks.
# Same primacy as campaign level: AD_CPQL_* is canonical; AD_CPL_* is secondary.

# Ad-level CPQL zones — PRIMARY KPI
AD_CPQL_SCALE      = 60.00  # < this  -> scale up
AD_CPQL_ACCEPTABLE = 75.00  # ≤ this  -> acceptable
AD_CPQL_WARNING    = 85.00  # ≤ this  -> warning
AD_CPQL_PAUSE      = 90.00  # > this  -> pause candidate

# Ad-level CPL zones — SECONDARY support metric
AD_CPL_SCALE      = 30.00   # < this  -> scale up
AD_CPL_ACCEPTABLE = 35.00   # ≤ this  -> acceptable
AD_CPL_WARNING    = 50.00   # ≤ this  -> warning
AD_CPL_PAUSE      = 50.00   # > this  -> pause candidate

# Qualification / ROAS targets
QUAL_RATE_TARGET = 0.30   # ≥ 30 %
ROAS_TARGET      = 1.0

# ROAS override — if campaign ROAS ≥ this, it's healthy regardless of qual rate
# (revenue is covering spend; don't pause on qual rate alone)
ROAS_GOOD = 0.8

# Awareness / traffic campaign name patterns (case-insensitive).
# These campaigns are evaluated on impression share/reach, NOT leads.
# Zero leads is fine — primary KPI is impressions or IS ≥ 25%.
AWARENESS_PATTERNS = [
    "impressionshare", "impression_share",
    "websitetraffic", "website_traffic",
    "reach",
]

# Per-channel CPQL acceptable overrides.
# Up to $130 is acceptable for Google Ads within 14 days.
CHANNEL_CPQL_ACCEPTABLE = {
    "google_ads": 130.00,
}

# Scale condition: CPQL < CPQL_SCALE *AND* ROAS > ROAS_GOOD — both required.
# CPQL alone is not enough; revenue must also be covering spend.
SCALE_REQUIRES_ROAS = True   # set False to scale on CPQL alone

# Drill-down trigger — when BOTH conditions are true for ≥ DRILL_DOWN_DAYS,
# analyse at ad/keyword level before touching the campaign.
DRILL_DOWN_CPQL   = 130.00   # CPQL must be above this
DRILL_DOWN_CPL    = 32.00    # AND CPL must be above this
DRILL_DOWN_DAYS   = 10       # for at least this many days of data

# Channel taxonomy for drill-down hierarchy.
# Social: start at Ad → AdSet → Campaign
# Search: start at Keyword → Ad Group → Campaign
SOCIAL_CHANNELS  = ["meta", "snapchat", "tiktok", "linkedin"]
SEARCH_CHANNELS  = ["google_ads", "microsoft_ads"]

# Minimum days since last campaign edit before we take action.
# If a campaign was edited < 7 days ago, changes haven't had time to show
# results yet — downgrade to "monitor" regardless of CPQL.
MIN_DAYS_SINCE_EDIT = 7

# Qflavours HubSpot pipeline — leads for the Qflavours product are tracked
# in a separate pipeline. Flag campaigns with "qflavours" in the name for
# manual pipeline verification.
QFLAVOURS_PIPELINE_CHECK = True

# Pause decision rules (USD, days)
DAYS_FOR_PAUSE_DECISION    = 14
SCALE_PAUSE_DIGEST_INTERVAL_DAYS = 4   # Slack #approvals digest cadence — only post every N days
ZERO_CONV_SPEND_THRESHOLD  = 8     # pause ad if spend > $8 with zero conv
ZERO_CONV_DAYS_THRESHOLD   = 7
# Keyword pause rules (Google Ads + Microsoft Ads) — three independent triggers:
#   Rule A: spend > $80, 0 conversions, active ≥ 10 days        → pause
#   Rule B: converting keyword but CPA > $90, active ≥ 10 days  → pause
#   Rule C: QS < 5 AND lost IS (rank) > 70%, 0 conv for 7 days  → pause
# Note: wasted-spend KEYWORDS are paused, NOT added as negatives.
KEYWORD_PAUSE_SPEND        = 80.00   # Rule A: zero-conv spend threshold
KEYWORD_PAUSE_CPA          = 90.00   # Rule B: high-CPA threshold (converting keywords)
KEYWORD_PAUSE_DAYS         = 10      # Rules A+B window (days)
KEYWORD_QS_PAUSE_THRESHOLD = 5       # Rule C: QS < 5
KEYWORD_IS_LOST_THRESHOLD  = 0.70    # Rule C: lost search IS (rank) > 70%
KEYWORD_QS_PAUSE_DAYS      = 7       # Rule C window (days)

# Minimum age before a NON-CONVERTING keyword can be paused. A 3-day-old
# keyword with $0 spend and 0 conv shouldn't be paused — it hasn't had time
# to perform. Measured by first-impression date (proxy for "active since").
# Does NOT apply to ALWAYS-NEGATIVE policy violations (login / دورة / etc.) —
# those are paused immediately regardless of age, since they should never be
# a keyword at any age.
MIN_KEYWORD_AGE_DAYS       = 10      # rule from Amar 2026-05-06
PLACEMENT_PAUSE_SPEND      = 3
