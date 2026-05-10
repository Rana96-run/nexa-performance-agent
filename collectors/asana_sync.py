"""
Sync Asana task status to BQ and detect user actions.

Two functions:
1. sync_asana_tasks()   — fetch completion status for agent-created tasks,
                          detect transitions (incomplete→complete = user acted),
                          infer executed recommendations from task title
2. sync_user_tasks()    — scan ASANA_PROJECTS for tasks NOT created by the agent
                          and log them as user_created_task

Both are called from reporting_scheduler.run_refresh() — non-fatal.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import BytesIO

import asana
from asana.rest import ApiException as AsanaApiException

from collectors.bq_writer import get_client as get_bq
from logs.activity_logger import log_activity_async


_TABLE  = "asana_task_status"
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
            "gid":          gid,
            "title":        t.get("name", ""),
            "completed":    bool(t.get("completed", False)),
            "completed_at": t.get("completed_at"),
            "assignee_name": (t.get("assignee") or {}).get("name", ""),
            "due_on":       t.get("due_on"),
        }
    except AsanaApiException:
        return None


def _infer_user_action(title: str, project_key: str) -> str:
    """
    Given a completed task, infer what the user actually did.
    Returns an action string for agent_activity_log.
    """
    t = (title or "").lower()
    if any(w in t for w in ("scale", "increase budget", "raise budget", "📈")):
        return "user_executed_scale"
    if any(w in t for w in ("pause", "stop", "disable", "⏸")):
        return "user_executed_pause"
    if any(w in t for w in ("negative", "negate", "🚫")):
        return "user_added_negative"
    if any(w in t for w in ("review", "creative", "drilldown", "drill down", "optimize")):
        return "user_reviewed_recommendation"
    return "user_completed_task"


def sync_asana_tasks() -> int:
    """
    Fetch Asana status for agent-created tasks, write to BQ, detect transitions.
    Returns number of rows written.
    """
    bq = get_bq()
    P  = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D  = os.getenv("BQ_DATASET",    "qoyod_marketing")

    bq.query(_CREATE_DDL.format(P=P, D=D, T=_TABLE)).result()

    # ── 1. GIDs from agent_activity_log ──────────────────────────────────────
    # Two sources:
    #   a) executors/asana.py  → action='asana_task_created', gid in details.gid
    #   b) campaign_health_tasks.py → action='*_task_created', gid in details.asana_gid
    gid_sql = f"""
        SELECT DISTINCT gid, title, project_key FROM (
          SELECT
            JSON_VALUE(details, '$.gid')         AS gid,
            JSON_VALUE(details, '$.title')        AS title,
            JSON_VALUE(details, '$.project_key')  AS project_key
          FROM `{P}.{D}.agent_activity_log`
          WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {_WINDOW_DAYS} DAY)
            AND action = 'asana_task_created'
            AND JSON_VALUE(details, '$.gid') IS NOT NULL

          UNION ALL

          SELECT
            JSON_VALUE(details, '$.asana_gid')   AS gid,
            CONCAT(
              CASE action
                WHEN 'scale_task_created'      THEN 'Scale: '
                WHEN 'pause_task_created'      THEN 'Pause: '
                WHEN 'junk_leads_task_created' THEN 'Junk Leads: '
                WHEN 'optimize_task_created'   THEN 'Optimize: '
                WHEN 'drilldown_task_created'  THEN 'Review: '
                ELSE ''
              END,
              COALESCE(campaign_name, action)
            )                                    AS title,
            'optimization'                       AS project_key
          FROM `{P}.{D}.agent_activity_log`
          WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {_WINDOW_DAYS} DAY)
            AND action IN (
              'scale_task_created', 'pause_task_created', 'junk_leads_task_created',
              'optimize_task_created', 'drilldown_task_created'
            )
            AND JSON_VALUE(details, '$.asana_gid') IS NOT NULL
        )
        WHERE gid IS NOT NULL
        LIMIT 500
    """
    log_rows  = list(bq.query(gid_sql).result())
    if not log_rows:
        return 0

    meta = {r.gid: {"title": r.title, "project_key": r.project_key} for r in log_rows}
    gids = list(meta.keys())

    # ── 2. Get previous completion state for transition detection ─────────────
    prev_sql = f"""
        SELECT gid, completed
        FROM (
          SELECT gid, completed,
                 ROW_NUMBER() OVER (PARTITION BY gid ORDER BY synced_at DESC) AS rn
          FROM `{P}.{D}.{_TABLE}`
          WHERE gid IN UNNEST({json.dumps(gids)})
        )
        WHERE rn = 1
    """
    try:
        prev_state = {r.gid: bool(r.completed) for r in bq.query(prev_sql).result()}
    except Exception:
        prev_state = {}

    # ── 3. Fetch current status from Asana ───────────────────────────────────
    client  = _asana_client()
    api     = asana.TasksApi(client)
    now_utc = datetime.now(timezone.utc)

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

    # ── 4. Write to BQ ───────────────────────────────────────────────────────
    ndjson    = b"\n".join(json.dumps(r).encode() for r in results)
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

    # ── 5. Log transitions: incomplete → complete = user acted ───────────────
    for r in results:
        gid  = r["gid"]
        was  = prev_state.get(gid, False)
        now_ = r["completed"]
        if not was and now_:
            action = _infer_user_action(r["title"], r["project_key"])
            log_activity_async(
                role="user",
                action=action,
                status="success",
                details={
                    "gid":         gid,
                    "title":       r["title"],
                    "project_key": r["project_key"],
                    "completed_at": r.get("completed_at", ""),
                },
            )
            print(f"[asana_sync] user action detected: {action} — {r['title'][:60]!r}")

    print(f"[asana_sync] wrote {len(results)} task statuses")
    return len(results)


def sync_user_tasks() -> int:
    """
    Scan all ASANA_PROJECTS for tasks NOT created by the agent.
    These are tasks the user created themselves. Logs each as user_created_task
    (deduplicates against previous sync runs via a BQ lookup).
    Returns number of new user tasks found.
    """
    from config import ASANA_PROJECTS

    bq = get_bq()
    P  = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D  = os.getenv("BQ_DATASET",    "qoyod_marketing")

    # Known agent-created GIDs — both direct creates and audit recommendation tasks
    known_sql = f"""
        SELECT DISTINCT gid FROM (
          SELECT JSON_VALUE(details, '$.gid') AS gid
          FROM `{P}.{D}.agent_activity_log`
          WHERE action = 'asana_task_created'
            AND JSON_VALUE(details, '$.gid') IS NOT NULL
            AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {_WINDOW_DAYS} DAY)
          UNION ALL
          SELECT JSON_VALUE(details, '$.asana_gid') AS gid
          FROM `{P}.{D}.agent_activity_log`
          WHERE action IN (
            'scale_task_created', 'pause_task_created', 'junk_leads_task_created',
            'optimize_task_created', 'drilldown_task_created'
          )
            AND JSON_VALUE(details, '$.asana_gid') IS NOT NULL
            AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {_WINDOW_DAYS} DAY)
        )
        WHERE gid IS NOT NULL
    """
    known_gids = {r.gid for r in bq.query(known_sql).result() if r.gid}

    # Already-logged user tasks (avoid duplicate log entries)
    already_sql = f"""
        SELECT DISTINCT JSON_VALUE(details, '$.gid') AS gid
        FROM `{P}.{D}.agent_activity_log`
        WHERE action = 'user_created_task'
          AND JSON_VALUE(details, '$.gid') IS NOT NULL
          AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {_WINDOW_DAYS} DAY)
    """
    already_logged = {r.gid for r in bq.query(already_sql).result() if r.gid}

    client     = _asana_client()
    tasks_api  = asana.TasksApi(client)
    cutoff     = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    found = 0
    for project_key, project_id in ASANA_PROJECTS.items():
        try:
            page = tasks_api.get_tasks_for_project(
                project_id,
                {
                    "opt_fields": "gid,name,completed,completed_at,assignee.name,created_at",
                    "modified_since": cutoff_str,
                    "limit": 100,
                },
            )
            for task in page:
                gid = task.get("gid")
                if not gid:
                    continue
                if gid in known_gids or gid in already_logged:
                    continue
                # New user-created task
                log_activity_async(
                    role="user",
                    action="user_created_task",
                    status="success",
                    details={
                        "gid":         gid,
                        "title":       task.get("name", ""),
                        "project_key": project_key,
                        "completed":   task.get("completed", False),
                        "completed_at": task.get("completed_at", ""),
                    },
                )
                already_logged.add(gid)
                found += 1
        except AsanaApiException as e:
            print(f"[asana_sync] project {project_key} list failed: {e}")
            continue

    if found:
        print(f"[asana_sync] found {found} user-created tasks across projects")
    return found


def run_full_sync() -> int:
    """Entry point called from reporting_scheduler."""
    n = sync_asana_tasks()
    m = sync_user_tasks()
    return n + m
