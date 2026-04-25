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

# Asana per-channel sections within the Optimization project.
# These are auto-created on first run if they don't exist.
# Format: channel_key → section display name in Asana
ASANA_CHANNEL_SECTIONS = {
    "google_ads":    "Google Ads",
    "meta":          "Meta",
    "snapchat":      "Snapchat",
    "linkedin":      "LinkedIn",
    "microsoft_ads": "Microsoft Ads",
    "tiktok":        "TikTok",
    "hubspot":       "HubSpot / CRM",
    "general":       "General",
}

# ---------------------------------------------------------------------------
# Currency (single source of truth)
# ---------------------------------------------------------------------------
# All reporting is in USD. SAR is pegged to USD at 3.75 by the Saudi Central
# Bank (since 1986). If that peg ever changes, this is the only line to edit.
REPORTING_CURRENCY = "USD"
DEFAULT_NATIVE_CURRENCY = "SAR"
USD_SAR_PEG = 3.75   # 1 USD = 3.75 SAR

# ---------------------------------------------------------------------------
# KPI thresholds — all in USD
# ---------------------------------------------------------------------------
# CPL (cost per lead) zones, USD
CPL_SCALE      = 5.50   # < this  → scale up
CPL_ACCEPTABLE = 7.50   # ≤ this  → acceptable
CPL_WARNING    = 8.00   # ≤ this  → warning; above → pause zone
CPL_PAUSE      = CPL_WARNING   # backwards-compat alias

# CPQL (cost per qualified lead / SQL) zones, USD
CPQL_SCALE      = 11.00
CPQL_ACCEPTABLE = 17.00
CPQL_WARNING    = 21.33
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
