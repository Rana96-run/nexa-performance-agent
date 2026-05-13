"""
Collector mutex — prevent parallel runs of the same collector from racing
through DELETE-then-INSERT and causing duplicates in BQ.

Why: 2026-05-13 we saw hubspot_deals_daily get 1.84x duplicate rows because
a manual deals backfill ran while the 6h scheduler also fired its sync.
Each DELETE removed the existing partition for that (date, source) tuple,
then both INSERTs landed — no per-row collision because the upsert's
DELETE-INSERT isn't atomic at BQ level.

How it works: each collector writes a "running" row to agent_activity_log
on start, checks for any other "running" row for the same action in the
last 30 minutes, and bails if one exists. On completion it logs
"success" or "failed" (which removes the lock implicitly — the
"running" entry isn't deleted, but a more-recent terminal entry overrides
the lock check via timestamp).

Usage:
    with collector_lock("hubspot_deals_sync"):
        collect_and_write(days=30)

If another instance holds the lock, raises CollectorLockBusy.
Set env LOCK_BYPASS=1 to skip the check (used by intentional re-runs).
"""
import os
from contextlib import contextmanager
from datetime import datetime, timezone


class CollectorLockBusy(RuntimeError):
    """Raised when another collector instance is currently holding the lock."""


# How long a "running" entry blocks new runs. After this, we assume the
# previous run died/crashed and let the new one proceed. Most collectors
# finish in < 5 min; 30 min is a generous timeout that won't false-block.
LOCK_TTL_MINUTES = 30


def _is_lock_held(action: str) -> tuple[bool, str | None]:
    """Check if another instance has a 'running' status for `action` more
    recent than LOCK_TTL_MINUTES. Returns (held, last_run_iso_ts_or_none)."""
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        client = get_client()
        q = f"""
        WITH latest AS (
          SELECT
            status,
            ts,
            ROW_NUMBER() OVER (ORDER BY ts DESC) AS rn
          FROM `{PROJECT_ID}.{DATASET}.agent_activity_log`
          WHERE action = @action
            AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(),
                                    INTERVAL {LOCK_TTL_MINUTES} MINUTE)
        )
        SELECT status, FORMAT_TIMESTAMP('%FT%TZ', ts) AS ts_iso
        FROM latest WHERE rn = 1
        """
        from google.cloud import bigquery
        params = [bigquery.ScalarQueryParameter("action", "STRING", action)]
        rows = list(client.query(
            q, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result())
        if not rows:
            return False, None
        # The most-recent entry within the TTL window
        row = rows[0]
        if row.status == "running":
            return True, row.ts_iso
        return False, row.ts_iso
    except Exception as e:
        # Fail-open: if we can't check the lock, allow the run rather than
        # blocking everything. Log the failure but proceed.
        print(f"[lock] check failed (fail-open, allowing run): {e}")
        return False, None


def _write_lock_state(action: str, status: str, details: dict | None = None) -> None:
    """Append a row to agent_activity_log marking lock state. Uses SYNC
    log_activity (not async) so the 'running' marker is immediately
    visible to the next collector's lock check — async writes use a
    background thread and the next process may not see them in time."""
    try:
        from logs.activity_logger import log_activity
        log_activity(
            role="collector",
            action=action,
            status=status,
            details=details or {},
        )
    except Exception as e:
        print(f"[lock] could not write {status} marker for {action}: {e}")


@contextmanager
def collector_lock(action: str):
    """Context manager: acquire a soft lock on `action`. Raises
    CollectorLockBusy if another instance is running. Use as:

        with collector_lock("hubspot_deals_sync"):
            do_the_work()

    Env override: set LOCK_BYPASS=1 to skip the check (for intentional
    parallel runs e.g. a manual backfill that knows what it's doing).
    """
    if os.getenv("LOCK_BYPASS"):
        print(f"[lock] LOCK_BYPASS=1 set — skipping check for {action}")
        yield
        return

    held, last_ts = _is_lock_held(action)
    if held:
        msg = (f"another '{action}' is already running (started {last_ts}). "
               f"Set LOCK_BYPASS=1 to override.")
        raise CollectorLockBusy(msg)

    _write_lock_state(action, status="running",
                      details={"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()})
    try:
        yield
        _write_lock_state(action, status="success",
                          details={"completed_at": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        _write_lock_state(action, status="failed",
                          details={"error": str(e)[:300]})
        raise
