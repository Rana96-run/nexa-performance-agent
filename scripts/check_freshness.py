"""
Collector freshness audit.

Checks MAX(date) per channel against today's date in Asia/Riyadh.
A channel that hasn't reported data for >1 day is flagged stale —
regardless of what `updated_at` says (the collector might be running
but silently fetching nothing).

Usage:
    python scripts/check_freshness.py            # console output, exit 1 if any stale
    python scripts/check_freshness.py --slack    # also post Slack alert if any stale

Programmatic:
    from scripts.check_freshness import audit
    stale = audit()  # returns list[(channel, last_date, days_behind)]
"""
import sys
import os
# Allow `python scripts/check_freshness.py` to import top-level `collectors/`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collectors.bq_writer import get_client

PROJECT = "angular-axle-492812-q4"
DATASET = "qoyod_marketing"

# How many days behind CURRENT_DATE('Asia/Riyadh') counts as "stale".
# Collectors run at 08:00 Riyadh and pull yesterday's data, so:
#  - On 09:00 Riyadh today, last data should be yesterday (1 day behind = OK)
#  - Before 08:00 today, last data is day-before-yesterday (2 days behind = OK)
#  - 3+ days behind = collector missed at least one full daily cycle = STALE
STALE_THRESHOLD_DAYS = 3

# Channels known to be paused on the platform side — no Slack alerts.
# When spend resumes, REMOVE the channel from this set so freshness gets
# tracked again. Run `python scripts/check_freshness.py` manually any time
# you want to see the full picture (no Slack post unless --slack passed).
KNOWN_PAUSED_CHANNELS = {"microsoft_ads", "linkedin"}


def audit() -> list[tuple]:
    """Return list of (channel, last_data_date, days_behind) for stale channels.

    Empty list means everything is fresh.
    """
    client = get_client()
    q = f"""
    SELECT channel,
           MAX(date) AS last_data_date,
           DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY) AS days_behind
    FROM `{PROJECT}.{DATASET}.campaigns_daily`
    WHERE channel IN ('google_ads','meta','snapchat','tiktok','microsoft_ads','linkedin')
    GROUP BY channel
    ORDER BY days_behind DESC, channel
    """
    stale = []
    print("=== Collector freshness — campaigns_daily ===")
    print(f"{'Channel':18} | {'Last date':12} | {'Days behind':12} | Status")
    print("-" * 70)
    for row in client.query(q).result():
        status = "OK" if row.days_behind < STALE_THRESHOLD_DAYS else "STALE"
        if status == "STALE":
            stale.append((row.channel, row.last_data_date, row.days_behind))
        print(f"{row.channel:18} | {row.last_data_date} | {row.days_behind:>12} | {status}")
    return stale


def post_slack_alert(stale: list[tuple]) -> None:
    """Post a Slack alert ONLY for channels that are unexpectedly stale.

    Filters out channels in KNOWN_PAUSED_CHANNELS unless they cross the
    PAUSED_ESCALATION_DAYS threshold. The team already knows Microsoft/
    LinkedIn are paused — daily reminders are noise, so we suppress them.
    """
    actionable = [
        (ch, last, days) for ch, last, days in stale
        if ch not in KNOWN_PAUSED_CHANNELS
    ]
    if not actionable:
        print(f"[freshness] {len(stale)} stale, all known-paused — no Slack alert")
        return

    try:
        from notifications.slack import client
        from config import SLACK_CHANNEL_NOTIFY
    except Exception as e:
        print(f"[freshness] could not import slack client: {e}")
        return

    lines = ["*:warning: Collector freshness alert*", ""]
    for ch, last, days in actionable:
        lines.append(f"• `{ch}` — last data `{last}` ({days} days behind)")
    text = "\n".join(lines)
    try:
        client.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=text)
        print(f"[freshness] posted alert to {SLACK_CHANNEL_NOTIFY} ({len(actionable)} channel(s))")
    except Exception as e:
        print(f"[freshness] slack post failed: {e}")


def main():
    stale = audit()
    if stale:
        print(f"\n[WARN] {len(stale)} stale channel(s):")
        for ch, last, days in stale:
            print(f"  - {ch}: last data {last} ({days} days behind)")
        print(
            "\nNOTE: 'stale' could mean either (a) the platform's campaigns "
            "are paused (no spend = no rows = correct), or (b) the collector "
            "is broken. Verify by logging into the channel's ad UI for the "
            "same window."
        )
        if "--slack" in sys.argv:
            post_slack_alert(stale)
        sys.exit(1)
    print("\nAll collectors fresh.")


if __name__ == "__main__":
    main()
