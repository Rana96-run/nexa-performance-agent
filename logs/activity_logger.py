"""
Agent Activity Logger
=====================
Every action the agent takes — Slack posts, Asana tasks, pause decisions,
BQ refreshes, junk-leads flags — is written here to BigQuery.

The dashboard/pages/7_Agent_Activity.py page reads this table live so you
can see exactly what the agent did and when, without digging through logs.

Usage (anywhere in the codebase):
    from logs.activity_logger import log_activity

    log_activity(
        role="daily_digest",
        action="posted_slack_digest",
        status="success",
        channel="meta",
        campaign_name=None,
        details={"channels": 6, "total_spend": 4200},
        rows_affected=None,
        duration_s=2.3,
    )

All parameters except role, action, status are optional.
Failures are swallowed — a logging bug must never take down the agent.
"""
import json
import os
import uuid
import threading
from datetime import datetime, timezone
from typing import Any

_SESSION_ID = str(uuid.uuid4())[:8]   # short ID shared across one agent run

# ── Lazy BQ client (created once per process) ────────────────────────────────
_bq_client = None
_bq_lock   = threading.Lock()


def _get_client():
    global _bq_client
    if _bq_client is not None:
        return _bq_client
    with _bq_lock:
        if _bq_client is not None:
            return _bq_client
        try:
            from collectors.bq_writer import get_client
            _bq_client = get_client()
        except Exception:
            _bq_client = None
    return _bq_client


def log_activity(
    role:             str,
    action:           str,
    status:           str          = "success",   # success | failed | skipped | pending_approval | approved | rejected
    channel:          str | None   = None,
    campaign_name:    str | None   = None,
    details:          Any          = None,        # dict, list, or str — serialised to JSON
    rows_affected:    int | None   = None,
    duration_s:       float | None = None,
    session_id:       str | None   = None,
    # ── Resource-consumption fields (added 2026-05-08, all nullable) ─────────
    tokens_in:        int | None   = None,        # Anthropic input tokens
    tokens_out:       int | None   = None,        # Anthropic output tokens
    cost_usd:         float | None = None,        # total $ cost (LLM + BQ + …)
    api_calls:        int | None   = None,        # outbound HTTP calls to platform APIs
    bq_bytes_scanned: int | None   = None,        # bytes processed by BQ queries
) -> None:
    """
    Fire-and-forget: writes one row to agent_activity_log in BQ.
    Completely silent on failure — never raises.
    """
    try:
        import os
        project  = os.getenv("BQ_PROJECT_ID")
        dataset  = os.getenv("BQ_DATASET", "qoyod_marketing")
        if not project:
            return  # no BQ configured — dev/local run, skip silently

        client = _get_client()
        if client is None:
            return

        row = {
            "activity_id":      str(uuid.uuid4()),
            "ts":               datetime.now(timezone.utc).isoformat(),
            "session_id":       session_id or _SESSION_ID,
            "role":             role,
            "action":           action,
            "status":           status,
            "channel":          channel,
            "campaign_name":    campaign_name,
            "details":          json.dumps(details, default=str) if details is not None else None,
            "rows_affected":    rows_affected,
            "duration_s":       round(duration_s, 3) if duration_s is not None else None,
            "tokens_in":        tokens_in,
            "tokens_out":       tokens_out,
            "cost_usd":         round(cost_usd, 6) if cost_usd is not None else None,
            "api_calls":        api_calls,
            "bq_bytes_scanned": bq_bytes_scanned,
        }

        table_id = f"{project}.{dataset}.agent_activity_log"

        from io import BytesIO
        import json as _json
        from google.cloud import bigquery

        ndjson = _json.dumps(row, default=str).encode("utf-8")
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        )
        client.load_table_from_file(
            BytesIO(ndjson), table_id, job_config=job_config
        ).result()

    except Exception:
        pass   # activity logging must never crash the agent


def log_activity_async(
    role:             str,
    action:           str,
    status:           str          = "success",
    channel:          str | None   = None,
    campaign_name:    str | None   = None,
    details:          Any          = None,
    rows_affected:    int | None   = None,
    duration_s:       float | None = None,
    # ── Resource-consumption fields (added 2026-05-08, all nullable) ─────────
    tokens_in:        int | None   = None,
    tokens_out:       int | None   = None,
    cost_usd:         float | None = None,
    api_calls:        int | None   = None,
    bq_bytes_scanned: int | None   = None,
) -> None:
    """
    Same as log_activity() but fire-and-forget in a background thread.
    Use this in time-sensitive paths (Slack posting, live Asana creation)
    so BQ latency doesn't slow the agent down.
    """
    t = threading.Thread(
        target=log_activity,
        kwargs=dict(
            role=role, action=action, status=status,
            channel=channel, campaign_name=campaign_name,
            details=details, rows_affected=rows_affected,
            duration_s=duration_s,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost_usd, api_calls=api_calls,
            bq_bytes_scanned=bq_bytes_scanned,
        ),
        daemon=False,   # non-daemon so the thread survives process keepalive cycles
    )
    t.start()


# ── Convenience context manager for timed blocks ─────────────────────────────
import time as _time
from contextlib import contextmanager


@contextmanager
def track(role: str, action: str, channel: str | None = None,
          campaign_name: str | None = None, details: Any = None):
    """
    Context manager that logs start + finish + duration automatically.

        with track("bq_refresh", "refresh_views"):
            refresh_all_views()

    Logs status="success" if the block exits normally, status="failed" if
    it raises (re-raises the exception after logging).
    """
    t0 = _time.time()
    try:
        yield
        duration = _time.time() - t0
        log_activity_async(
            role=role, action=action, status="success",
            channel=channel, campaign_name=campaign_name,
            details=details, duration_s=duration,
        )
    except Exception as exc:
        duration = _time.time() - t0
        log_activity_async(
            role=role, action=action, status="failed",
            channel=channel, campaign_name=campaign_name,
            details={"error": str(exc), **(details or {})},
            duration_s=duration,
        )
        raise
