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
ASANA_TOKEN = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_PROJECTS = {
    "daily_activity": os.getenv("ASANA_PROJECT_DAILY_ACTIVITY") or os.getenv("ASANA_PORTFOLIO_DAILY_ACTIVITY"),
    "optimization": os.getenv("ASANA_PROJECT_OPTIMIZATION") or os.getenv("ASANA_PORTFOLIO_OPTIMIZATION"),
    "campaigns_hub": os.getenv("ASANA_PROJECT_CAMPAIGNS_HUB") or os.getenv("ASANA_PORTFOLIO_CAMPAIGNS_HUB") or os.getenv("ASANA_PORTFOLIO_DAILY_ACTIVITY"),
    "seasonal": os.getenv("ASANA_PROJECT_SEASONAL") or os.getenv("ASANA_PORTFOLIO_SEASONAL"),
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
# CPL (cost per lead) zones, USD
CPL_SCALE      = 20.00  # < this  → scale up
CPL_ACCEPTABLE = 28.00  # ≤ this  → acceptable
CPL_WARNING    = 30.00  # ≤ this  → warning; > $30 for 4 days → pause zone
CPL_PAUSE      = CPL_WARNING   # backwards-compat alias

# CPQL (cost per qualified lead / SQL) zones, USD
CPQL_SCALE      = 40.00
CPQL_ACCEPTABLE = 65.00
CPQL_WARNING    = 80.00  # > $80 for 4 days → pause zone
CPQL_PAUSE      = CPQL_WARNING  # backwards-compat alias

# Qualification / ROAS targets
QUAL_RATE_TARGET = 0.30   # ≥ 30 %
ROAS_TARGET      = 1.0

# Pause decision rules (USD, days)
DAYS_FOR_PAUSE_DECISION    = 4
ZERO_CONV_SPEND_THRESHOLD  = 8     # pause ad if spend > $8 with zero conv
ZERO_CONV_DAYS_THRESHOLD   = 7
KEYWORD_PAUSE_SPEND        = 4     # pause keyword if spend > $4 with zero conv
KEYWORD_PAUSE_DAYS         = 14
PLACEMENT_PAUSE_SPEND      = 3
