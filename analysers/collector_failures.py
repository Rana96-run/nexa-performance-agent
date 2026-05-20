"""Morning health ping — scans agent_activity_log for collector failures.

Runs after _refresh_bigquery() in _nightly(). If any collector failed in the
last 24h (i.e. since the previous nightly), posts a one-line ping to
#nexa-health with a count by channel + link to the dashboard.

This closes the gap that allowed the May 18-20 deals/leads silence: those
collectors failed for 3 days, the failures were logged to BQ, but nothing
proactively alerted on them. Now they will.

The ping uses notifications.slack_ping.post_ping — same format as the QA
gate alerts and reconciler drift alerts.
"""
from __future__ import annotations
import os
from typing import Optional

from collectors.bq_writer import get_client
from notifications.slack_ping import post_ping

HEALTH_CHANNEL = os.getenv("SLACK_CHANNEL_HEALTH", "#nexa-health")
ACTIVITY_URL = (
    os.getenv("ACTIVITY_SHORT_URL")
    or "https://nexa-web-production-6a6b.up.railway.app/activity"
)


def check_collector_failures(window_hours: int = 24, post_slack: bool = True) -> dict:
    """Scan agent_activity_log for collector failures in the last window_hours.

    Returns:
        {
          "failures": [(channel, count, latest_error), ...],
          "total_failed_collectors": int,
          "posted_to_slack": bool,
        }
    """
    c = get_client()
    proj = os.environ["BQ_PROJECT_ID"]
    ds = os.environ["BQ_DATASET"]

    # Group by channel + find the latest error message for each
    sql = f"""
    WITH recent AS (
      SELECT
        channel,
        status,
        ts,
        SUBSTR(IFNULL(JSON_VALUE(details, '$.error'), ''), 1, 200) AS err
      FROM `{proj}.{ds}.agent_activity_log`
      WHERE role = 'bq_refresh'
        AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_hours} HOUR)
    )
    SELECT
      channel,
      COUNTIF(status = 'failed') AS failures,
      COUNTIF(status = 'success') AS successes,
      ARRAY_AGG(IF(status = 'failed', err, NULL) IGNORE NULLS
                ORDER BY ts DESC LIMIT 1)[SAFE_OFFSET(0)] AS latest_error,
      MAX(IF(status = 'failed', ts, NULL)) AS latest_fail_ts
    FROM recent
    GROUP BY channel
    HAVING failures > 0
    ORDER BY failures DESC, channel
    """
    rows = list(c.query(sql).result())

    # Only alert on channels that had failures AND no recovery write since
    # (otherwise transient failures with later success self-heal, no need to ping)
    blocking = []
    for r in rows:
        if r.failures > 0 and r.successes == 0:
            # No successful run in the window → genuine outage
            blocking.append((r.channel, r.failures, (r.latest_error or "")[:120]))

    result = {
        "failures": blocking,
        "total_failed_collectors": len(blocking),
        "transient_failures": [(r.channel, r.failures) for r in rows
                               if r.successes > 0],
        "posted_to_slack": False,
    }

    if not blocking:
        return result

    if post_slack:
        # Slack is just a reminder — one line, link to dashboard
        channels_str = ", ".join(f"{ch} ({n})" for ch, n, _ in blocking[:5])
        if len(blocking) > 5:
            channels_str += f", +{len(blocking) - 5} more"
        headline = (
            f"Collector failures last {window_hours}h — no recovery: {channels_str}"
        )
        try:
            post_ping(channel=HEALTH_CHANNEL, status="alert",
                      headline=headline, link=ACTIVITY_URL)
            result["posted_to_slack"] = True
        except Exception as e:
            print(f"[collector_failures] Slack ping failed: {e}")

    return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = check_collector_failures(window_hours=24, post_slack=False)
    print(f"Failed collectors (no recovery): {r['total_failed_collectors']}")
    for ch, n, err in r["failures"]:
        print(f"  {ch}: {n} failures — {err}")
    if r["transient_failures"]:
        print(f"\nTransient (later self-healed): {r['transient_failures']}")
