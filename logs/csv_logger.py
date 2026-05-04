"""
logs/csv_logger.py
==================
Append-only CSV activity log for the Nexa agent.

Every significant action the agent takes — BQ collects, Slack posts,
Asana task creation, role runs, approval decisions, keyword executions —
writes one row here. The CSV is synced to BigQuery (agent_activity_log
table) on each BQ refresh cycle so Hex can query it.

CSV path: logs/activity_log.csv
BQ table: agent_activity_log

Schema
------
timestamp     ISO-8601 UTC  when the action happened
date          YYYY-MM-DD    Riyadh date (UTC+3)
session_id    8-char str    shared across one agent run (groups a nightly cycle)
role          str           bq_refresh | daily_agent | keyword_approval |
                            campaign_health | paid_media_strategist |
                            spike_detector | slack_approval | hubspot_webhook
action_type   str           collect | analyse | notify | task | approve |
                            execute | health | refresh
action        str           human-readable one-liner
channel       str           google_ads | meta | snapchat | tiktok | linkedin |
                            microsoft_ads | all | — (blank)
campaign      str           campaign name or blank
status        str           ok | failed | skipped | approved | rejected
count         int           rows / messages / tasks / keywords (0 if N/A)
details       str           JSON string with extras (error msg, channel list, etc.)
"""
from __future__ import annotations

import csv
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

_CSV_PATH = Path(__file__).parent / "activity_log.csv"
_LOCK     = threading.Lock()
_RIYADH   = timezone(timedelta(hours=3))

_COLUMNS = [
    "timestamp", "date", "session_id", "role", "action_type",
    "action", "channel", "campaign", "status", "count", "details",
]

# One session_id per process — groups everything one nightly run did
_SESSION_ID = str(uuid.uuid4())[:8]


def _ensure_header():
    if not _CSV_PATH.exists() or _CSV_PATH.stat().st_size == 0:
        with open(_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_COLUMNS).writeheader()


def log(
    role:        str,
    action_type: str,
    action:      str,
    status:      str         = "ok",
    channel:     str         = "",
    campaign:    str         = "",
    count:       int         = 0,
    details:     dict | None = None,
) -> None:
    """Append one row to activity_log.csv. Never raises — logging must not crash the agent."""
    try:
        now    = datetime.now(timezone.utc)
        riyadh = datetime.now(_RIYADH)
        row = {
            "timestamp":   now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date":        riyadh.strftime("%Y-%m-%d"),
            "session_id":  _SESSION_ID,
            "role":        role,
            "action_type": action_type,
            "action":      action,
            "channel":     channel,
            "campaign":    campaign,
            "status":      status,
            "count":       count,
            "details":     json.dumps(details, default=str) if details else "",
        }
        with _LOCK:
            _ensure_header()
            with open(_CSV_PATH, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=_COLUMNS).writerow(row)
    except Exception as e:
        print(f"[csv_logger] write failed (non-fatal): {e}")


def log_async(
    role:        str,
    action_type: str,
    action:      str,
    status:      str         = "ok",
    channel:     str         = "",
    campaign:    str         = "",
    count:       int         = 0,
    details:     dict | None = None,
) -> None:
    """Same as log() but fire-and-forget in a background thread."""
    threading.Thread(
        target=log,
        kwargs=dict(role=role, action_type=action_type, action=action,
                    status=status, channel=channel, campaign=campaign,
                    count=count, details=details),
        daemon=True,
    ).start()


def sync_to_bq() -> int:
    """
    Upload the full CSV to BigQuery agent_activity_log (WRITE_TRUNCATE).
    Called at the end of each BQ refresh cycle.
    Returns number of rows synced, or 0 on failure.
    """
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        from google.cloud import bigquery

        if not _CSV_PATH.exists():
            print("[csv_logger] activity_log.csv not found — nothing to sync")
            return 0

        client   = get_client()
        table_id = f"{PROJECT_ID}.{DATASET}.agent_activity_log"

        schema = [
            bigquery.SchemaField("timestamp",   "TIMESTAMP"),
            bigquery.SchemaField("date",        "DATE"),
            bigquery.SchemaField("session_id",  "STRING"),
            bigquery.SchemaField("role",        "STRING"),
            bigquery.SchemaField("action_type", "STRING"),
            bigquery.SchemaField("action",      "STRING"),
            bigquery.SchemaField("channel",     "STRING"),
            bigquery.SchemaField("campaign",    "STRING"),
            bigquery.SchemaField("status",      "STRING"),
            bigquery.SchemaField("count",       "INTEGER"),
            bigquery.SchemaField("details",     "STRING"),
        ]
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        with open(_CSV_PATH, "rb") as f:
            job = client.load_table_from_file(f, table_id, job_config=job_config)
            job.result()

        rows = client.get_table(table_id).num_rows
        print(f"[csv_logger] synced {rows} rows → {table_id}")
        return rows

    except Exception as e:
        print(f"[csv_logger] BQ sync failed (non-fatal): {e}")
        return 0
