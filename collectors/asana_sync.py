"""
Sync Asana task completion status into BigQuery.

Reads GIDs from agent_activity_log.details, fetches current status from
Asana API (completed, completed_at), and upserts into asana_task_status.

Called from reporting_scheduler.run_refresh() — non-fatal if Asana is down.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import BytesIO

import asana
from asana.rest import ApiException as AsanaApiException

from collectors.bq_writer import get_client as get_bq


_TABLE = "asana_task_status"
_CREATE_DDL = """
CREATE TABLE IF NOT EXISTS `{P}.{D}.{T}` (
  gid            STRING  NOT NULL,
  title          STRING,
  project_key    STRING,
  completed      BOOL,
  completed_at   TIMESTAMP,
  assignee_name  STRING,
  due_on         DATE,
  synced_at      TIMESTAMP NOT NULL
)
PARTITION BY DATE(synced_at)
OPTIONS(require_partition_filter=false)
"""

_WINDOW_DAYS = 90


def _asana_client():
    from config import ASANA_TOKEN
    cfg = asana.Configuration()
    cfg.access_token = ASANA_TOKEN
    return asana.ApiClient(cfg)


def _fetch_task(api: asana.TasksApi, gid: str) -> dict | None:
    try:
        t = api.get_task(gid, {"opt_fields": "gid,name,completed,completed_at,assignee.name,due_on"})
        return {
            "gid":           gid,
            "title":         t.get("name", ""),
            "completed":     bool(t.get("completed", False)),
            "completed_at":  t.get("completed_at"),
            "assignee_name": (t.get("assignee") or {}).get("name", ""),
            "due_on":        t.get("due_on"),
        }
    except AsanaApiException:
        return None


def sync_asana_tasks(project_key_filter: str | None = None) -> int:
    """
    Fetch GIDs from BQ, check completion via Asana API, write results to BQ.
    Returns number of rows synced.
    """
    bq = get_bq()
    P  = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D  = os.getenv("BQ_DATASET",    "qoyod_marketing")

    # Ensure table exists
    bq.query(_CREATE_DDL.format(P=P, D=D, T=_TABLE)).result()

    # Pull GIDs from activity log
    pk_filter = ""
    if project_key_filter:
        pk_filter = f"AND JSON_VALUE(details, '$.project_key') = '{project_key_filter}'"

    gid_sql = f"""
        SELECT DISTINCT
          JSON_VALUE(details, '$.gid')         AS gid,
          JSON_VALUE(details, '$.title')        AS title,
          JSON_VALUE(details, '$.project_key')  AS project_key
        FROM `{P}.{D}.agent_activity_log`
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {_WINDOW_DAYS} DAY)
          AND action = 'asana_task_created'
          AND JSON_VALUE(details, '$.gid') IS NOT NULL
          {pk_filter}
        ORDER BY ts DESC
        LIMIT 200
    """
    rows = list(bq.query(gid_sql).result())
    if not rows:
        return 0

    client  = _asana_client()
    api     = asana.TasksApi(client)
    now_utc = datetime.now(timezone.utc)

    meta = {r.gid: {"title": r.title, "project_key": r.project_key} for r in rows}
    gids = list(meta.keys())

    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_task, api, gid): gid for gid in gids}
        for fut in as_completed(futures):
            data = fut.result()
            if data is None:
                continue
            gid = data["gid"]
            data["title"]       = data["title"] or meta[gid]["title"] or ""
            data["project_key"] = meta[gid]["project_key"] or ""
            data["synced_at"]   = now_utc.isoformat()
            results.append(data)

    if not results:
        return 0

    # Build NDJSON and load
    ndjson = b"\n".join(json.dumps(r).encode() for r in results)

    table_ref = bq.dataset(D, project=P).table(_TABLE)
    from google.cloud import bigquery as bqlib
    job_cfg = bqlib.LoadJobConfig(
        source_format=bqlib.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bqlib.WriteDisposition.WRITE_APPEND,
        autodetect=False,
        schema=[
            bqlib.SchemaField("gid",           "STRING"),
            bqlib.SchemaField("title",         "STRING"),
            bqlib.SchemaField("project_key",   "STRING"),
            bqlib.SchemaField("completed",     "BOOL"),
            bqlib.SchemaField("completed_at",  "TIMESTAMP"),
            bqlib.SchemaField("assignee_name", "STRING"),
            bqlib.SchemaField("due_on",        "DATE"),
            bqlib.SchemaField("synced_at",     "TIMESTAMP"),
        ],
    )
    bq.load_table_from_file(BytesIO(ndjson), table_ref, job_config=job_cfg).result()
    print(f"[asana_sync] wrote {len(results)} task statuses to BQ")
    return len(results)
