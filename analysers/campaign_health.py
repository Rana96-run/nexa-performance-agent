"""
Stub for analysers.campaign_health.

The full campaign_health analyser was removed 2026-06-16 when the analysers/
package was consolidated into n8n workflow Claude nodes and BQ views.

This stub exists so that qa/checks.py check_pause_precedence() does NOT
silently pass — it explicitly returns an empty list (no pause candidates),
which means the pause-precedence gate passes cleanly but the check is
effectively disabled until a real implementation is restored.
"""


def get_pause_candidates(*args, **kwargs):
    """Return empty list — real implementation removed 2026-06-16."""
    return []


def _campaigns_with_keyword_pause_candidates(*args, **kwargs):
    """Return empty dict — real implementation removed 2026-06-16."""
    return {}


def _campaigns_with_ad_pause_candidates(*args, **kwargs):
    """Return empty dict — real implementation removed 2026-06-16."""
    return {}
