from collectors.meta import pause_ad, pause_adset

# Re-export executor functions from the collector module.
# These are only called after explicit Slack approval.
__all__ = ["pause_ad", "pause_adset"]
