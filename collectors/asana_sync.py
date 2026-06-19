"""
Sync Asana task status to BQ and detect user actions.

Two functions:
1. sync_asana_tasks()   — fetch completion status for agent-created tasks,
                          detect transitions (incomplete→complete = user acted),
                          infer executed recommendations from task title
2. sync_user_tasks()    — scan ASANA_PROJECTS for tasks NOT created by the agent
                          and log them as user_created_task

Called from n8n workflows via Railway subprocess, or directly via `python -m collectors.asana_sync`.
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
  gid            STRING,
  title          STRING,
  project_key    STRING,
  completed      BOOL,
  completed_at   TIMESTAMP,
  assignee_name  STRING,
  due_on         DATE,
  synced_at      TIMESTAMP
)
PARTITION BY DATE(synced_at)
OPTIONS(require_partition_filter=false)
"""
# Fix for existing tables created with NOT NULL constraints — drop REQUIRED mode
_ALTER_DDL = """
ALTER TABLE `{P}.{D}.{T}`
  ALTER COLUMN gid DROP NOT NULL,
  ALTER COLUMN synced_at DROP NOT NULL
"""
_WINDOW_DAYS = 365


def _asana_client():
    from config import ASANA_TOKEN
    cfg = asana.Configuration()
    cfg.access_token = ASANA_TOKEN
    return asana.ApiClient(cfg)


_EXCLUDED_PROJECTS = {"seasonal"}  # not active work-item projects

def _all_projects() -> dict[str, str]:
    """Return every Asana project the agent creates tasks in.

    Merges all four project dicts into one flat {project_key: project_id},
    skipping any None/empty IDs and excluded keys.
    """
    from config import (
        ASANA_PROJECTS, ASANA_OPTIMIZATION_PROJECTS,
        ASANA_DAILY_PROJECTS, ASANA_SEASONAL_PROJECTS,
    )
    merged: dict[str, str] = {}
    for d in (ASANA_PROJECTS, ASANA_OPTIMIZATION_PROJECTS,
              ASANA_DAILY_PROJECTS, ASANA_SEASONAL_PROJECTS):
        for k, v in d.items():
            if v and k not in _EXCLUDED_PROJECTS:
                merged[k] = v
    return merged


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
    try:
        bq.query(_ALTER_DDL.format(P=P, D=D, T=_TABLE)).result()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[asana_sync] schema alter failed: {e}")
        raise

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

    # ── 5. Log transitions + patch "Completed on" in task notes ─────────────
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
            # Patch "Completed on" field in the task notes
            _patch_completed_on(api, gid, r.get("completed_at") or "")

    print(f"[asana_sync] wrote {len(results)} task statuses")
    return len(results)


def _patch_completed_on(api: asana.TasksApi, gid: str, completed_at: str) -> None:
    """Replace '| ✅ Completed on | — |' in task notes with the actual date."""
    try:
        task = api.get_task(gid, {"opt_fields": "notes"})
        notes = task.get("notes") or ""
        if "| ✅ Completed on | — |" not in notes:
            return
        from datetime import datetime, timezone, timedelta
        if completed_at:
            try:
                dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                riyadh = timezone(timedelta(hours=3))
                date_str = dt.astimezone(riyadh).strftime("%Y-%m-%d %H:%M Riyadh")
            except Exception:
                date_str = completed_at[:10]
        else:
            date_str = datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d")
        new_notes = notes.replace(
            "| ✅ Completed on | — |",
            f"| ✅ Completed on | {date_str} |",
        )
        api.update_task(gid, {"data": {"notes": new_notes}}, {})
        print(f"[asana_sync] patched completed_on for {gid}: {date_str}")
    except Exception as e:
        print(f"[asana_sync] patch completed_on failed for {gid} (non-fatal): {e}")


def sync_user_tasks() -> int:
    """
    Scan all ASANA_PROJECTS for tasks NOT created by the agent.
    These are tasks the user created themselves. Logs each as user_created_task
    (deduplicates against previous sync runs via a BQ lookup).
    Returns number of new user tasks found.
    """
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
    for project_key, project_id in _all_projects().items():
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


def backfill_from_projects() -> int:
    """
    Scan ALL ASANA_PROJECTS (including completed tasks, all pages) and seed
    agent_activity_log for any task GID not already recorded there.

    Safe to call every sync — skips already-known GIDs in O(1).
    Covers the full project history since agent creation.

    Returns count of newly seeded tasks.
    """
    bq = get_bq()
    P  = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
    D  = os.getenv("BQ_DATASET",    "qoyod_marketing")

    # All GIDs already in agent_activity_log (either logging path)
    known_sql = f"""
        SELECT DISTINCT gid FROM (
          SELECT JSON_VALUE(details, '$.gid')       AS gid
          FROM `{P}.{D}.agent_activity_log`
          WHERE action = 'asana_task_created'
            AND JSON_VALUE(details, '$.gid') IS NOT NULL

          UNION ALL

          SELECT JSON_VALUE(details, '$.asana_gid') AS gid
          FROM `{P}.{D}.agent_activity_log`
          WHERE action IN (
            'scale_task_created', 'pause_task_created', 'junk_leads_task_created',
            'optimize_task_created', 'drilldown_task_created'
          )
            AND JSON_VALUE(details, '$.asana_gid') IS NOT NULL
        )
        WHERE gid IS NOT NULL
    """
    try:
        already_known = {r.gid for r in bq.query(known_sql).result() if r.gid}
    except Exception:
        already_known = set()

    client    = _asana_client()
    tasks_api = asana.TasksApi(client)
    seeded    = 0
    status_rows: list[dict] = []  # collect for bulk write to asana_task_status
    now_utc   = datetime.now(timezone.utc)

    for project_key, project_id in _all_projects().items():
        if not project_id:
            continue
        try:
            # completed_since="1970-01-01" returns ALL tasks including completed ones.
            # The SDK handles pagination automatically when iterating the generator.
            opts = {
                "opt_fields": "gid,name,completed,completed_at,assignee.name,created_at,due_on",
                "completed_since": "1970-01-01T00:00:00.000Z",
                "limit": 100,
            }
            for task in tasks_api.get_tasks_for_project(project_id, opts):
                gid = task.get("gid")
                if not gid:
                    continue
                name = task.get("name", "")
                if gid not in already_known:
                    asset_level = "campaign"
                    name_words = name.lower().split()
                    if any(w in name_words for w in ("keyword", "negative", "kw")):
                        asset_level = "keyword"
                    elif "ad" in name_words or "creative" in name_words:
                        asset_level = "ad"
                    log_activity_async(
                        role="task_creator",
                        action="asana_task_created",
                        status="success",
                        details={
                            "gid":         gid,
                            "title":       name[:120],
                            "project_key": project_key,
                            "asset_level": asset_level,
                            "backfilled":  True,
                        },
                    )
                    already_known.add(gid)
                    seeded += 1
                # Always collect status — backfill already has completed_at, write it
                status_rows.append({
                    "gid":           gid,
                    "title":         name[:120],
                    "project_key":   project_key,
                    "completed":     bool(task.get("completed", False)),
                    "completed_at":  task.get("completed_at"),
                    "assignee_name": (task.get("assignee") or {}).get("name", ""),
                    "due_on":        task.get("due_on"),
                    "synced_at":     now_utc.isoformat(),
                })
        except Exception as e:
            print(f"[asana_backfill] project {project_key} failed: {e}")

    # Write completion status to asana_task_status in one bulk pass
    if status_rows:
        try:
            bq.query(_CREATE_DDL.format(P=P, D=D, T=_TABLE)).result()
            try:
                bq.query(_ALTER_DDL.format(P=P, D=D, T=_TABLE)).result()
            except Exception:
                pass
            ndjson    = b"\n".join(json.dumps(r).encode() for r in status_rows)
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
            n_done = sum(1 for r in status_rows if r["completed"])
            print(f"[asana_backfill] wrote {len(status_rows)} status rows ({n_done} completed) to {_TABLE}")
        except Exception as e:
            print(f"[asana_backfill] asana_task_status write failed (non-fatal): {e}")

    if seeded:
        print(f"[asana_backfill] seeded {seeded} historical tasks into agent_activity_log")
    return seeded


def run_full_sync() -> int:
    """Entry point called from n8n workflows via Railway subprocess.
    Always runs backfill first — idempotent, skips known GIDs instantly."""
    backfill_from_projects()
    n = sync_asana_tasks()
    m = sync_user_tasks()
    return n + m


# Backwards-compat alias — callers that import sync_tasks get run_full_sync
sync_tasks = run_full_sync
