"""Launch-policy gate — enforce 1-new-campaign-per-channel-per-7-days.

Why this exists: between May 4 and May 10 2026, 8+ new campaigns went live
across Google + Bing within 6 days. None had a 7-day observation window
before the next launched. CPQL across the channel spiked from $77 → $138
within a week. No single decision was wrong; the *cluster* was.

This policy blocks new campaign creation if any campaign on the same channel
took its first spend (> $10) within the last `LAUNCH_COOLDOWN_DAYS` days.

Usage in an executor's `create_campaign()`:

    from executors.launch_policy import enforce_launch_policy, LaunchBlocked
    try:
        enforce_launch_policy("google_ads")
    except LaunchBlocked as e:
        print(f"[blocked] {e}")
        return None
    # ... proceed to create the campaign

CLI usage (for humans):

    railway run python -m executors.launch_policy --channel google_ads
    railway run python -m executors.launch_policy --channel google_ads --force
"""
from __future__ import annotations
import os
import sys
from datetime import date, timedelta

LAUNCH_COOLDOWN_DAYS = 7         # 1 launch per channel per N days
LAUNCH_FIRST_SPEND_MIN_USD = 10  # threshold for "took first spend"

# Channels exempt from the policy. Snap creates and rotates ~185 short-lived
# ad-objects daily; treating each as a "launch" would block all activity.
EXEMPT_CHANNELS = {"snapchat"}


class LaunchBlocked(Exception):
    """Raised when a new-campaign create would violate the cooldown."""
    def __init__(self, channel: str, blocker: dict):
        self.channel = channel
        self.blocker = blocker
        super().__init__(
            f"Launch blocked on {channel}: '{blocker.get('campaign_name')}' "
            f"first spent on {blocker.get('first_day')} "
            f"({blocker.get('days_ago')} day(s) ago). "
            f"Wait until {blocker.get('clear_after')} or pass force=True."
        )


def _recent_launches(channel: str, cooldown_days: int) -> list[dict]:
    """Return campaigns on `channel` whose first spend is within `cooldown_days`."""
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    client = get_client()
    sql = f"""
        SELECT campaign_id,
               ANY_VALUE(campaign_name) AS campaign_name,
               MIN(IF(spend > {LAUNCH_FIRST_SPEND_MIN_USD}, date, NULL)) AS first_day
        FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
        WHERE channel = @channel
        GROUP BY campaign_id
        HAVING first_day >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'),
                                     INTERVAL {cooldown_days} DAY)
        ORDER BY first_day DESC
    """
    from google.cloud import bigquery
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("channel", "STRING", channel),
    ])
    today = date.today()
    out = []
    for r in client.query(sql, job_config=job_config).result():
        first = r.first_day
        out.append({
            "campaign_id":   r.campaign_id,
            "campaign_name": r.campaign_name,
            "first_day":     first.isoformat() if first else None,
            "days_ago":      (today - first).days if first else None,
            "clear_after":   (first + timedelta(days=cooldown_days)).isoformat() if first else None,
        })
    return out


def enforce_launch_policy(channel: str,
                          force: bool = False,
                          cooldown_days: int = LAUNCH_COOLDOWN_DAYS) -> None:
    """Raise LaunchBlocked if the channel has a launch within the cooldown.

    Args:
        channel: 'google_ads' | 'meta' | 'microsoft_ads' | 'tiktok' | 'linkedin'
        force: bypass the check. Caller must log a justification to Asana.
        cooldown_days: override the default 7-day window.
    """
    channel = (channel or "").strip().lower()
    if not channel:
        raise ValueError("enforce_launch_policy: channel is required")

    if channel in EXEMPT_CHANNELS:
        return

    # Env-level override for batch operations / migrations.
    if force or os.getenv("FORCE_LAUNCH") == "1":
        print(f"[launch-policy] {channel}: force=True — policy bypassed")
        return

    blockers = _recent_launches(channel, cooldown_days)
    if not blockers:
        return

    # Block on the most-recent launch — it tells the caller exactly when
    # the cooldown clears.
    raise LaunchBlocked(channel, blockers[0])


def is_launch_allowed(channel: str,
                      cooldown_days: int = LAUNCH_COOLDOWN_DAYS) -> tuple[bool, str | None]:
    """Non-raising variant — returns (allowed, reason). Useful for UI / CLI."""
    try:
        enforce_launch_policy(channel, force=False, cooldown_days=cooldown_days)
        return True, None
    except LaunchBlocked as e:
        return False, str(e)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Launch-policy gate CLI")
    p.add_argument("--channel", required=True,
                   help="google_ads | meta | microsoft_ads | tiktok | linkedin")
    p.add_argument("--force", action="store_true",
                   help="bypass the check (logs reason to stdout)")
    p.add_argument("--cooldown-days", type=int, default=LAUNCH_COOLDOWN_DAYS)
    args = p.parse_args()
    allowed, reason = is_launch_allowed(args.channel, cooldown_days=args.cooldown_days)
    if allowed:
        print(f"OK: launches allowed on {args.channel}")
        sys.exit(0)
    else:
        print(f"BLOCKED: {reason}")
        sys.exit(1 if not args.force else 0)
