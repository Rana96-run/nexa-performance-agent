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

# KPI Thresholds (matches agent logic)
CPL_PAUSE = 30
CPL_WARNING = 28
CPQL_PAUSE = 80
CPQL_WARNING = 65
DAYS_FOR_PAUSE_DECISION = 4
ZERO_CONV_SPEND_THRESHOLD = 30      # USD - pause ad if spend > this with zero conv
ZERO_CONV_DAYS_THRESHOLD = 7        # days - pause ad if no conv for this many days
KEYWORD_PAUSE_SPEND = 15            # USD
KEYWORD_PAUSE_DAYS = 14
PLACEMENT_PAUSE_SPEND = 10          # USD
