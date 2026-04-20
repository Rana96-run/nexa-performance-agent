from collectors.google_ads import pause_keyword, pause_ad

# Re-export executor functions from the collector module.
# These are only called after explicit Slack approval.
__all__ = ["pause_keyword", "pause_ad"]
