"""
HubSpot Lead module -> BigQuery.

Two write modes:
  1. collect_and_write()     — legacy createdate-window aggregation (kept for backfill).
  2. sync_cursor_and_write() — cursor-based CDC that exactly mirrors HubSpot.
     Fetches every lead modified since last checkpoint (hs_lastmodifieddate),
     upserts into hubspot_leads_individual (one row per hs_object_id), then
     re-aggregates only the affected dates into hubspot_leads_module_daily.
     Handles leads from ANY year — no window boundary.
"""
import os
import json as _json
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows, get_client

load_dotenv()
TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
BASE = "https://api.hubapi.com"
LEAD_OBJ = "0-136"

PROPERTIES = [
    "hs_createdate", "hs_lastmodifieddate", "hs_pipeline", "hs_pipeline_stage", "hs_lead_is_open",
    "lead_qoyod_source",
    "lead_utm_campaign", "lead_utm_audience", "lead_utm_content",
    "lead_utm_term", "lead_utm_source", "lead_utm_medium",
    # Fallback chain — see analysers/channel_inference.py.
    # The two *_traffic_source enums hold high-level source type
    # (PAID_SEARCH / PAID_SOCIAL / ORGANIC_SEARCH / ...).
    # The two *_drilldown_1 properties usually hold the campaign name —
    # that's where we disambiguate Google vs Bing, Meta vs TikTok, etc.
    # The two *_drilldown_2 properties may hold utm_audience or another
    # campaign-name hint.
    "lead_original_traffic_source",
    "lead_latest_traffic_source",
    "lead_original_traffic_source_drilldown_1",
    "lead_latest_traffic_source_drilldown_1",
    "lead_original_traffic_source_drilldown_2",
    "lead_latest_traffic_source_drilldown_2",
    "leads_disqualification_reason__ops",
    "leads_disqualification_reason__sub_reasons",
    "leads_disqualification_reason__ops_qflavour",
    "disqualification_reason_bookkeeping",
]

# One-time fetch: map pipeline_id -> label, stage_id -> (pipeline_id, stage_label)
_CACHE = {"pipelines": None, "stages": None}


def _load_pipelines():
    if _CACHE["pipelines"] is not None:
        return
    r = requests.get(f"{BASE}/crm/v3/pipelines/{LEAD_OBJ}",
                     headers={"Authorization": f"Bearer {TOKEN}"})
    r.raise_for_status()
    pipelines, stages = {}, {}
    for p in r.json().get("results", []):
        pipelines[p["id"]] = p["label"]
        for s in p.get("stages", []):
            stages[s["id"]] = (p["id"], p["label"], s["label"])
    _CACHE["pipelines"] = pipelines
    _CACHE["stages"] = stages


def _stage_info(stage_id):
    if not stage_id:
        return None, None, None
    pid, plabel, slabel = _CACHE["stages"].get(stage_id, (None, None, None))
    return pid, plabel, slabel


def _is_qualified(stage_label):
    return bool(stage_label) and "qualified" in stage_label.lower() and "dis" not in stage_label.lower()


def _is_disqualified(stage_label):
    return bool(stage_label) and "disqualified" in stage_label.lower()


def _search_leads(since_ms, until_ms=None, after=None):
    filters = [{"propertyName": "hs_createdate", "operator": "GTE", "value": str(since_ms)}]
    if until_ms is not None:
        filters.append({"propertyName": "hs_createdate", "operator": "LT", "value": str(until_ms)})
    body = {
        "filterGroups": [{"filters": filters}],
        "properties": PROPERTIES,
        "limit": 100,
        "sorts": [{"propertyName": "hs_createdate", "direction": "ASCENDING"}],
    }
    if after:
        body["after"] = after
    r = requests.post(f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
                      headers={"Authorization": f"Bearer {TOKEN}",
                               "Content-Type": "application/json"},
                      json=body)
    r.raise_for_status()
    return r.json()


def collect_and_write(days: int = None, start_date: date = None,
                       incremental: bool = False):
    """Modes:
      - incremental=True: last 30 days by hs_createdate (scheduled runs).
        Re-fetches leads created in the last 30 days with their CURRENT stage
        so leads qualified days after creation are correctly counted.
      - days=N / start_date=: custom window by hs_createdate
      - default: YTD backfill
    """
    _load_pipelines()

    end = date.today()
    if incremental:
        start = end - timedelta(days=30)
    elif start_date:
        start = start_date
    elif days:
        start = end - timedelta(days=days)
    else:
        start = date(end.year, 1, 1)
    print(f"[leads] Window: {start} -> {end}")
    since_ms = int(datetime(start.year, start.month, start.day).timestamp() * 1000)

    # bucket key: (date, qoyod_source, pipeline, stage, utm_campaign, utm_audience, utm_content, utm_source, utm_medium, utm_term)
    buckets = defaultdict(lambda: {"total": 0, "qualified": 0, "disqualified": 0, "open": 0,
                                     "disq_reasons": defaultdict(int),
                                     "disq_sub_reasons": defaultdict(int)})

    # HubSpot Search caps at 10k results — walk 7-day windows.
    # pages counter resets each window so one large period can't exhaust the cap.
    total_fetched = 0
    window = timedelta(days=7)
    win_start = start
    end_dt = end + timedelta(days=1)
    while win_start < end_dt:
        win_end = min(win_start + window, end_dt)
        w_since = int(datetime(win_start.year, win_start.month, win_start.day).timestamp() * 1000)
        w_until = int(datetime(win_end.year, win_end.month, win_end.day).timestamp() * 1000)
        after = None
        win_count = 0
        pages = 0  # reset per window
        while True:
            try:
                data = _search_leads(w_since, until_ms=w_until, after=after)
            except Exception as e:
                print(f"[leads] search error: {e}")
                break
            for row in data.get("results", []):
                p = row.get("properties", {})
                created = (p.get("hs_createdate") or "")[:10]
                if not created:
                    continue
                pid, plabel, slabel = _stage_info(p.get("hs_pipeline_stage"))
                is_open = str(p.get("hs_lead_is_open", "0")) == "1"
                qual = _is_qualified(slabel)
                disq = _is_disqualified(slabel)

                # Resolve channel through the full fallback chain (see
                # analysers/channel_inference.py for the full order).  Pass
                # every signal we have — the resolver decides which to use.
                from analysers.channel_inference import (
                    resolve_channel, CHANNEL_TO_QOYOD_SOURCE,
                )
                explicit_src = (p.get("lead_qoyod_source") or "").strip()
                inferred_slug = resolve_channel(
                    qoyod_source=explicit_src,
                    lead_utm_source=p.get("lead_utm_source") or "",
                    lead_utm_campaign=p.get("lead_utm_campaign") or "",
                    lead_original_traffic_source=p.get("lead_original_traffic_source") or "",
                    lead_latest_traffic_source=p.get("lead_latest_traffic_source") or "",
                    lead_original_traffic_source_drilldown_1=
                        p.get("lead_original_traffic_source_drilldown_1") or "",
                    lead_latest_traffic_source_drilldown_1=
                        p.get("lead_latest_traffic_source_drilldown_1") or "",
                    lead_original_traffic_source_drilldown_2=
                        p.get("lead_original_traffic_source_drilldown_2") or "",
                    lead_latest_traffic_source_drilldown_2=
                        p.get("lead_latest_traffic_source_drilldown_2") or "",
                    lead_utm_audience=p.get("lead_utm_audience") or "",
                    lead_utm_content=p.get("lead_utm_content") or "",
                    lead_utm_medium=p.get("lead_utm_medium") or "",
                )
                # Prefer the original explicit label (when not 'Other');
                # otherwise back-translate the inferred slug.  Fall back to
                # 'Other' (HubSpot's own classification for "no rule met")
                # when nothing resolves.
                if explicit_src and explicit_src != "Other":
                    src_label = explicit_src
                elif inferred_slug:
                    src_label = CHANNEL_TO_QOYOD_SOURCE.get(inferred_slug, inferred_slug)
                else:
                    src_label = explicit_src or "Other"

                key = (
                    created,
                    src_label,
                    plabel or "Unknown",
                    slabel or "Unknown",
                    (p.get("lead_utm_campaign") or "").strip() or "__none__",
                    (p.get("lead_utm_audience") or "").strip() or None,
                    (p.get("lead_utm_content") or "").strip() or None,
                    (p.get("lead_utm_source") or "").strip() or None,
                    (p.get("lead_utm_medium") or "").strip() or None,
                    (p.get("lead_utm_term") or "").strip() or None,
                )
                b = buckets[key]
                b["total"] += 1
                if qual:
                    b["qualified"] += 1
                elif disq:
                    b["disqualified"] += 1
                    reason = (p.get("leads_disqualification_reason__ops") or
                              p.get("leads_disqualification_reason__ops_qflavour") or
                              p.get("disqualification_reason_bookkeeping") or "Unknown")
                    b["disq_reasons"][reason] += 1
                    sub_reason = (p.get("leads_disqualification_reason__sub_reasons") or
                                  p.get("leads_disqualification_reason__sub_reasons_qflavour") or
                                  "Unknown")
                    b["disq_sub_reasons"][sub_reason] += 1
                if is_open:
                    b["open"] += 1
                total_fetched += 1
                win_count += 1

            pages += 1
            paging = data.get("paging", {}).get("next", {})
            after = paging.get("after")
            if not after or pages >= 100:   # 100 pages × 100 rows = 10k cap per window
                break
        print(f"[leads] {win_start}..{win_end}: {win_count} leads")
        win_start = win_end

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for key, b in buckets.items():
        (d, src, pipeline, stage, utm_c, utm_a, utm_co, utm_s, utm_m, utm_t) = key
        top_reason = max(b["disq_reasons"].items(), key=lambda x: x[1])[0] if b["disq_reasons"] else None
        top_sub_reason = max(b["disq_sub_reasons"].items(), key=lambda x: x[1])[0] if b["disq_sub_reasons"] else None
        rows.append({
            "date": d,
            "qoyod_source": src,
            "pipeline": pipeline,
            "stage": stage,
            "lead_utm_campaign": utm_c,
            "lead_utm_audience": utm_a,
            "lead_utm_content": utm_co,
            "lead_utm_source": utm_s,
            "lead_utm_medium": utm_m,
            "lead_utm_term": utm_t,
            "leads_total": b["total"],
            "leads_qualified": b["qualified"],
            "leads_disqualified": b["disqualified"],
            "leads_open": b["open"],
            "top_disq_reason": top_reason,
            "top_disq_sub_reason": top_sub_reason,
            "updated_at": now,
        })

    print(f"Processed {total_fetched} leads -> {len(rows)} daily buckets")
    _ensure_table_exists()
    return upsert_rows("hubspot_leads_module_daily", rows,
                       key_fields=["date", "qoyod_source", "pipeline", "stage",
                                   "lead_utm_campaign", "lead_utm_audience",
                                   "lead_utm_content", "lead_utm_term"])


def _ensure_table_exists():
    from google.cloud import bigquery
    client = get_client()
    table_id = f"{os.getenv('BQ_PROJECT_ID')}.{os.getenv('BQ_DATASET')}.hubspot_leads_module_daily"
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("qoyod_source", "STRING"),
        bigquery.SchemaField("pipeline", "STRING"),
        bigquery.SchemaField("stage", "STRING"),
        bigquery.SchemaField("lead_utm_campaign", "STRING"),
        bigquery.SchemaField("lead_utm_audience", "STRING"),
        bigquery.SchemaField("lead_utm_content", "STRING"),
        bigquery.SchemaField("lead_utm_source", "STRING"),
        bigquery.SchemaField("lead_utm_medium", "STRING"),
        bigquery.SchemaField("lead_utm_term", "STRING"),
        bigquery.SchemaField("leads_total", "INT64"),
        bigquery.SchemaField("leads_qualified", "INT64"),
        bigquery.SchemaField("leads_disqualified", "INT64"),
        bigquery.SchemaField("leads_open", "INT64"),
        bigquery.SchemaField("top_disq_reason", "STRING"),
        bigquery.SchemaField("top_disq_sub_reason", "STRING"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="date")
    table.clustering_fields = ["qoyod_source", "pipeline"]
    client.create_table(table, exists_ok=True)


# ── Cursor-based CDC (exact HubSpot mirror) ──────────────────────────────────

from google.cloud import bigquery as _bq

_INDIVIDUAL_TABLE = "hubspot_leads_individual"

_INDIVIDUAL_SCHEMA = [
    _bq.SchemaField("hs_object_id",        "STRING",    mode="REQUIRED"),
    _bq.SchemaField("hs_createdate",        "DATE",      mode="REQUIRED"),
    _bq.SchemaField("hs_lastmodifieddate",  "TIMESTAMP"),
    _bq.SchemaField("pipeline_id",          "STRING"),
    _bq.SchemaField("pipeline",             "STRING"),
    _bq.SchemaField("stage_id",             "STRING"),
    _bq.SchemaField("stage",               "STRING"),
    _bq.SchemaField("is_qualified",         "BOOL"),
    _bq.SchemaField("is_disqualified",      "BOOL"),
    _bq.SchemaField("is_open",              "BOOL"),
    _bq.SchemaField("qoyod_source",         "STRING"),
    _bq.SchemaField("lead_utm_campaign",    "STRING"),
    _bq.SchemaField("lead_utm_audience",    "STRING"),
    _bq.SchemaField("lead_utm_content",     "STRING"),
    _bq.SchemaField("lead_utm_source",      "STRING"),
    _bq.SchemaField("lead_utm_medium",      "STRING"),
    _bq.SchemaField("lead_utm_term",        "STRING"),
    _bq.SchemaField("top_disq_reason",      "STRING"),
    _bq.SchemaField("top_disq_sub_reason",  "STRING"),
    _bq.SchemaField("updated_at",           "TIMESTAMP"),
]


def _ensure_individual_table_exists():
    client = get_client()
    project = os.getenv("BQ_PROJECT_ID")
    dataset = os.getenv("BQ_DATASET")
    table_id = f"{project}.{dataset}.{_INDIVIDUAL_TABLE}"
    table = _bq.Table(table_id, schema=_INDIVIDUAL_SCHEMA)
    table.time_partitioning = _bq.TimePartitioning(field="hs_createdate")
    table.clustering_fields = ["qoyod_source", "pipeline"]
    client.create_table(table, exists_ok=True)


def _get_cursor() -> datetime:
    """
    Read the high-water mark from hubspot_leads_individual.
    Returns MAX(hs_lastmodifieddate) minus 5 minutes for overlap safety.
    Defaults to Jan 1 of current year if the table is empty.
    """
    try:
        client = get_client()
        project = os.getenv("BQ_PROJECT_ID")
        dataset = os.getenv("BQ_DATASET")
        result = list(client.query(
            f"SELECT MAX(hs_lastmodifieddate) AS max_ts "
            f"FROM `{project}.{dataset}.{_INDIVIDUAL_TABLE}`"
        ).result())
        max_ts = result[0].max_ts if result else None
        if max_ts:
            # 5-min overlap so clock skew never drops a record
            return max_ts - timedelta(minutes=5)
    except Exception as e:
        print(f"[leads-cursor] cursor read failed: {e}")
    return datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc)


def _search_by_modified(since_ms: int, until_ms: int, after=None) -> dict:
    """Search leads by hs_lastmodifieddate within a 1-hour window."""
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": str(since_ms)},
            {"propertyName": "hs_lastmodifieddate", "operator": "LT",  "value": str(until_ms)},
        ]}],
        "properties": PROPERTIES,
        "limit": 100,
        "sorts": [{"propertyName": "hs_lastmodifieddate", "direction": "ASCENDING"}],
    }
    if after:
        body["after"] = after
    r = requests.post(f"{BASE}/crm/v3/objects/{LEAD_OBJ}/search",
                      headers={"Authorization": f"Bearer {TOKEN}",
                               "Content-Type": "application/json"},
                      json=body)
    r.raise_for_status()
    return r.json()


def _row_from_lead(lead: dict) -> dict | None:
    """
    Convert a raw HubSpot lead result into a hubspot_leads_individual row.
    Returns None if hs_createdate is missing (can't partition without it).
    """
    _load_pipelines()
    p = lead.get("properties", {})
    created = (p.get("hs_createdate") or "")[:10]
    if not created:
        return None

    modified_str = p.get("hs_lastmodifieddate") or ""
    modified_iso = modified_str.replace("Z", "+00:00") if modified_str else None

    pid, plabel, slabel = _stage_info(p.get("hs_pipeline_stage"))
    is_open = str(p.get("hs_lead_is_open", "0")) == "1"
    qual    = _is_qualified(slabel)
    disq    = _is_disqualified(slabel)

    from analysers.channel_inference import resolve_channel, CHANNEL_TO_QOYOD_SOURCE
    explicit_src  = (p.get("lead_qoyod_source") or "").strip()
    inferred_slug = resolve_channel(
        qoyod_source=explicit_src,
        lead_utm_source=p.get("lead_utm_source") or "",
        lead_utm_campaign=p.get("lead_utm_campaign") or "",
        lead_original_traffic_source=p.get("lead_original_traffic_source") or "",
        lead_latest_traffic_source=p.get("lead_latest_traffic_source") or "",
        lead_original_traffic_source_drilldown_1=p.get("lead_original_traffic_source_drilldown_1") or "",
        lead_latest_traffic_source_drilldown_1=p.get("lead_latest_traffic_source_drilldown_1") or "",
        lead_original_traffic_source_drilldown_2=p.get("lead_original_traffic_source_drilldown_2") or "",
        lead_latest_traffic_source_drilldown_2=p.get("lead_latest_traffic_source_drilldown_2") or "",
        lead_utm_audience=p.get("lead_utm_audience") or "",
        lead_utm_content=p.get("lead_utm_content") or "",
        lead_utm_medium=p.get("lead_utm_medium") or "",
    )
    if explicit_src and explicit_src != "Other":
        src_label = explicit_src
    elif inferred_slug:
        src_label = CHANNEL_TO_QOYOD_SOURCE.get(inferred_slug, inferred_slug)
    else:
        src_label = explicit_src or "Other"

    disq_reason = (
        p.get("leads_disqualification_reason__ops") or
        p.get("leads_disqualification_reason__ops_qflavour") or
        p.get("disqualification_reason_bookkeeping") or None
    ) if disq else None
    disq_sub = (p.get("leads_disqualification_reason__sub_reasons") or None) if disq else None

    return {
        "hs_object_id":        lead["id"],
        "hs_createdate":       created,
        "hs_lastmodifieddate": modified_iso,
        "pipeline_id":         pid or "",
        "pipeline":            plabel or "Unknown",
        "stage_id":            p.get("hs_pipeline_stage") or "",
        "stage":               slabel or "Unknown",
        "is_qualified":        qual,
        "is_disqualified":     disq,
        "is_open":             is_open,
        "qoyod_source":        src_label,
        "lead_utm_campaign":   (p.get("lead_utm_campaign") or "").strip() or "__none__",
        "lead_utm_audience":   (p.get("lead_utm_audience") or "").strip() or None,
        "lead_utm_content":    (p.get("lead_utm_content") or "").strip() or None,
        "lead_utm_source":     (p.get("lead_utm_source") or "").strip() or None,
        "lead_utm_medium":     (p.get("lead_utm_medium") or "").strip() or None,
        "lead_utm_term":       (p.get("lead_utm_term") or "").strip() or None,
        "top_disq_reason":     disq_reason,
        "top_disq_sub_reason": disq_sub,
        "updated_at":          datetime.now(timezone.utc).isoformat(),
    }


def _delete_leads_by_ids(client, ids: list[str]) -> None:
    """Targeted DELETE on hubspot_leads_individual by hs_object_id list."""
    if not ids:
        return
    project = os.getenv("BQ_PROJECT_ID")
    dataset = os.getenv("BQ_DATASET")
    table_id = f"{project}.{dataset}.{_INDIVIDUAL_TABLE}"
    params    = [_bq.ArrayQueryParameter("ids", "STRING", ids)]
    client.query(
        f"DELETE FROM `{table_id}` WHERE hs_object_id IN UNNEST(@ids)",
        job_config=_bq.QueryJobConfig(query_parameters=params)
    ).result()


def _rebuild_daily_buckets(client, affected_dates: set) -> int:
    """
    Re-aggregate hubspot_leads_individual for the given set of createdate dates,
    then upsert into hubspot_leads_module_daily.
    Called after every cursor sync so the aggregated table stays current.
    """
    if not affected_dates:
        return 0

    project  = os.getenv("BQ_PROJECT_ID")
    dataset  = os.getenv("BQ_DATASET")
    table_id = f"{project}.{dataset}.{_INDIVIDUAL_TABLE}"
    date_list = sorted(str(d) for d in affected_dates)

    params = [_bq.ArrayQueryParameter("dates", "DATE", date_list)]
    rows_iter = client.query(
        f"SELECT * FROM `{table_id}` WHERE hs_createdate IN UNNEST(@dates)",
        job_config=_bq.QueryJobConfig(query_parameters=params)
    ).result()

    buckets = defaultdict(lambda: {
        "total": 0, "qualified": 0, "disqualified": 0, "open": 0,
        "disq_reasons": defaultdict(int), "disq_sub_reasons": defaultdict(int),
    })
    for row in rows_iter:
        key = (
            str(row.hs_createdate),
            row.qoyod_source or "Other",
            row.pipeline or "Unknown",
            row.stage or "Unknown",
            row.lead_utm_campaign or "__none__",
            row.lead_utm_audience,
            row.lead_utm_content,
            row.lead_utm_source,
            row.lead_utm_medium,
            row.lead_utm_term,
        )
        b = buckets[key]
        b["total"] += 1
        if row.is_qualified:
            b["qualified"] += 1
        elif row.is_disqualified:
            b["disqualified"] += 1
            if row.top_disq_reason:
                b["disq_reasons"][row.top_disq_reason] += 1
            if row.top_disq_sub_reason:
                b["disq_sub_reasons"][row.top_disq_sub_reason] += 1
        if row.is_open:
            b["open"] += 1

    now = datetime.now(timezone.utc).isoformat()
    daily_rows = []
    for key, b in buckets.items():
        d, src, pipeline, stage, utm_c, utm_a, utm_co, utm_s, utm_m, utm_t = key
        top_reason = max(b["disq_reasons"], key=b["disq_reasons"].get) if b["disq_reasons"] else None
        top_sub    = max(b["disq_sub_reasons"], key=b["disq_sub_reasons"].get) if b["disq_sub_reasons"] else None
        daily_rows.append({
            "date":                d,
            "qoyod_source":        src,
            "pipeline":            pipeline,
            "stage":               stage,
            "lead_utm_campaign":   utm_c,
            "lead_utm_audience":   utm_a,
            "lead_utm_content":    utm_co,
            "lead_utm_source":     utm_s,
            "lead_utm_medium":     utm_m,
            "lead_utm_term":       utm_t,
            "leads_total":         b["total"],
            "leads_qualified":     b["qualified"],
            "leads_disqualified":  b["disqualified"],
            "leads_open":          b["open"],
            "top_disq_reason":     top_reason,
            "top_disq_sub_reason": top_sub,
            "updated_at":          now,
        })

    _ensure_table_exists()
    return upsert_rows("hubspot_leads_module_daily", daily_rows,
                       key_fields=["date", "qoyod_source", "pipeline", "stage",
                                   "lead_utm_campaign", "lead_utm_audience",
                                   "lead_utm_content", "lead_utm_term"])


def sync_cursor_and_write(incremental: bool = False, days: int = None) -> int:
    # incremental / days are ignored — the BQ cursor determines the window.
    """
    Cursor-based sync — exactly mirrors HubSpot regardless of lead age.

    Algorithm:
      1. Read high-water mark = MAX(hs_lastmodifieddate) from hubspot_leads_individual
      2. Walk 1-hour windows from checkpoint -> now, fetching leads by hs_lastmodifieddate
         (1-hour windows keep each search well under HubSpot's 10k cap)
      3. Upsert modified leads into hubspot_leads_individual (DELETE by id + INSERT)
      4. Collect affected hs_createdates -> rebuild those dates in hubspot_leads_module_daily

    Run this in the scheduler instead of (or after) collect_and_write for incremental runs.
    Keep collect_and_write for historical backfills.
    """
    _load_pipelines()
    _ensure_individual_table_exists()

    client     = get_client()
    checkpoint = _get_cursor()
    now_utc    = datetime.now(timezone.utc)

    print(f"[leads-cursor] checkpoint={checkpoint.isoformat()}")
    print(f"[leads-cursor] syncing {checkpoint.strftime('%Y-%m-%d %H:%M')} -> {now_utc.strftime('%Y-%m-%d %H:%M')}")

    all_rows       = []
    affected_dates = set()
    win_hours      = timedelta(hours=1)
    win_start      = checkpoint
    total_fetched  = 0

    while win_start < now_utc:
        win_end  = min(win_start + win_hours, now_utc)
        since_ms = int(win_start.timestamp() * 1000)
        until_ms = int(win_end.timestamp() * 1000)
        after    = None
        pages    = 0
        win_count = 0

        while True:
            try:
                data = _search_by_modified(since_ms, until_ms, after=after)
            except Exception as e:
                print(f"[leads-cursor] search error at {win_start}: {e}")
                break

            for lead in data.get("results", []):
                row = _row_from_lead(lead)
                if row:
                    all_rows.append(row)
                    affected_dates.add(row["hs_createdate"])
                    win_count += 1

            pages += 1
            paging = data.get("paging", {}).get("next", {})
            after  = paging.get("after")
            if not after or pages >= 100:   # 100 × 100 = 10k cap per window
                break

        if win_count:
            print(f"[leads-cursor]   {win_start.strftime('%m-%d %H:%M')}: {win_count} leads")
        total_fetched += win_count
        win_start = win_end

    print(f"[leads-cursor] {total_fetched} leads modified -> {len(affected_dates)} affected dates")

    if not all_rows:
        print("[leads-cursor] nothing to sync")
        return 0

    # DELETE old rows by hs_object_id (batches of 500 — safe under BQ param limit)
    ids = [r["hs_object_id"] for r in all_rows]
    for i in range(0, len(ids), 500):
        _delete_leads_by_ids(client, ids[i:i + 500])

    # INSERT fresh rows via load job (never streaming — see pitfalls)
    _flush_individual(client, all_rows)
    print(f"[leads-cursor] wrote {len(all_rows)} rows -> hubspot_leads_individual")

    # Rebuild only the affected date buckets in the aggregated table
    n = _rebuild_daily_buckets(client, affected_dates)
    print(f"[leads-cursor] rebuilt {len(affected_dates)} dates -> {n} bucket rows -> hubspot_leads_module_daily")
    return n


def initial_load_individual(start_date: date = None) -> int:
    """
    One-time full load of hubspot_leads_individual from HubSpot by createdate.
    After this runs, sync_cursor_and_write() takes over for ongoing incremental sync.

    Usage:
        python -m collectors.hubspot_leads_bq initial_load
        python -m collectors.hubspot_leads_bq initial_load 2024-01-01
    """
    _load_pipelines()
    _ensure_individual_table_exists()

    client = get_client()
    start  = start_date or date(2024, 1, 1)
    end    = date.today() + timedelta(days=1)
    print(f"[leads-initial] full load {start} -> {date.today()}")

    all_rows      = []
    window        = timedelta(days=7)
    win_start     = start
    total_fetched = 0

    while win_start < end:
        win_end  = min(win_start + window, end)
        w_since  = int(datetime(win_start.year, win_start.month, win_start.day, tzinfo=timezone.utc).timestamp() * 1000)
        w_until  = int(datetime(win_end.year,   win_end.month,   win_end.day,   tzinfo=timezone.utc).timestamp() * 1000)
        after    = None
        pages    = 0
        win_count = 0

        while True:
            try:
                data = _search_leads(w_since, until_ms=w_until, after=after)
            except Exception as e:
                print(f"[leads-initial] error at {win_start}: {e}")
                break
            for lead in data.get("results", []):
                row = _row_from_lead(lead)
                if row:
                    all_rows.append(row)
                    win_count += 1
            pages += 1
            paging = data.get("paging", {}).get("next", {})
            after  = paging.get("after")
            if not after or pages >= 100:
                break

        print(f"[leads-initial] {win_start}..{win_end}: {win_count} leads")
        total_fetched += win_count
        win_start = win_end

        # Flush every 5k rows to avoid large in-memory batches
        if len(all_rows) >= 5000:
            _flush_individual(client, all_rows)
            all_rows = []

    if all_rows:
        _flush_individual(client, all_rows)

    print(f"[leads-initial] done — {total_fetched} leads loaded into hubspot_leads_individual")
    return total_fetched


def _flush_individual(client, rows: list[dict], label: str = "leads-initial") -> None:
    """Append a batch of rows to hubspot_leads_individual via load job."""
    project  = os.getenv("BQ_PROJECT_ID")
    dataset  = os.getenv("BQ_DATASET")
    table_id = f"{project}.{dataset}.{_INDIVIDUAL_TABLE}"
    ndjson   = "\n".join(_json.dumps(r, default=str) for r in rows).encode()
    job_cfg  = _bq.LoadJobConfig(
        schema=_INDIVIDUAL_SCHEMA,
        source_format=_bq.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition="WRITE_APPEND",
    )
    client.load_table_from_file(BytesIO(ndjson), table_id, job_config=job_cfg).result()
    print(f"[{label}] flushed {len(rows)} rows")


def full_resync_since_2026() -> int:
    """
    Full re-pull of all HubSpot leads with hs_createdate >= 2026-01-01.

    Replaces the individual table rows for that window with the freshest values
    from HubSpot, then rebuilds daily buckets.  Designed to run twice a week
    (Tuesday + Friday Riyadh time) to catch lead_qoyod_source changes caused
    by Contact workflow re-runs — changes that don't move the Lead's
    hs_lastmodifieddate so the cursor CDC never sees them.

    Approach mirrors Funnel.io: no delta logic, just pull the current state of
    every lead in the window and overwrite BQ.

    CLI: python -m collectors.hubspot_leads_bq resync
    """
    _load_pipelines()
    _ensure_individual_table_exists()

    client       = get_client()
    resync_start = date(2026, 1, 1)
    end          = date.today() + timedelta(days=1)
    project      = os.getenv("BQ_PROJECT_ID")
    dataset      = os.getenv("BQ_DATASET")
    table_id     = f"{project}.{dataset}.{_INDIVIDUAL_TABLE}"

    print(f"[leads-resync] full re-pull {resync_start} -> {date.today()}")

    # ── Step 1: Fetch all leads from HubSpot by createdate window ────────────
    all_rows  = []
    window    = timedelta(days=7)
    win_start = resync_start

    while win_start < end:
        win_end   = min(win_start + window, end)
        w_since   = int(datetime(win_start.year, win_start.month, win_start.day,
                                 tzinfo=timezone.utc).timestamp() * 1000)
        w_until   = int(datetime(win_end.year,   win_end.month,   win_end.day,
                                 tzinfo=timezone.utc).timestamp() * 1000)
        after     = None
        pages     = 0
        win_count = 0

        while True:
            try:
                data = _search_leads(w_since, until_ms=w_until, after=after)
            except Exception as e:
                print(f"[leads-resync] error at {win_start}: {e}")
                break
            for lead in data.get("results", []):
                row = _row_from_lead(lead)
                if row:
                    all_rows.append(row)
                    win_count += 1
            pages += 1
            paging = data.get("paging", {}).get("next", {})
            after  = paging.get("after")
            if not after or pages >= 100:
                break

        print(f"[leads-resync]   {win_start}..{win_end}: {win_count} leads")
        win_start = win_end

    print(f"[leads-resync] fetched {len(all_rows)} leads from HubSpot")
    if not all_rows:
        print("[leads-resync] nothing fetched — aborting")
        return 0

    # ── Step 2: Delete existing 2026 rows from individual table ──────────────
    print(f"[leads-resync] deleting rows where hs_createdate >= '{resync_start}'...")
    client.query(
        f"DELETE FROM `{table_id}` WHERE hs_createdate >= '{resync_start}'"
    ).result()

    # ── Step 3: Insert fresh rows in batches of 5 000 ────────────────────────
    for i in range(0, len(all_rows), 5000):
        _flush_individual(client, all_rows[i:i + 5000], label="leads-resync")
    print(f"[leads-resync] wrote {len(all_rows)} rows to {_INDIVIDUAL_TABLE}")

    # ── Step 4: Rebuild daily buckets for all affected dates ─────────────────
    affected_dates = {row["hs_createdate"] for row in all_rows}
    n = _rebuild_daily_buckets(client, affected_dates)
    print(f"[leads-resync] rebuilt {len(affected_dates)} dates -> {n} bucket rows")
    return n


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "backfill"

    if cmd == "initial_load":
        start = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else None
        n = initial_load_individual(start_date=start)
        print(f"Initial load complete: {n} leads")

    elif cmd == "cursor":
        n = sync_cursor_and_write()
        print(f"Cursor sync complete: {n} daily bucket rows updated")

    elif cmd == "resync":
        n = full_resync_since_2026()
        print(f"Full resync complete: {n} daily bucket rows updated")

    elif cmd == "rebuild_all":
        # Full rebuild of hubspot_leads_module_daily from hubspot_leads_individual.
        # Run this once after initial_load_individual completes.
        # Processes dates in batches of 30 to avoid MERGE timeout on 600+ date sets.
        from collectors.bq_writer import get_client
        import os as _os
        _client = get_client()
        _project = _os.getenv("BQ_PROJECT_ID")
        _dataset = _os.getenv("BQ_DATASET")
        _BATCH_SIZE = 30
        print("[rebuild_all] querying all distinct hs_createdate from individual table...")
        _dates_rows = _client.query(
            f"SELECT DISTINCT hs_createdate FROM `{_project}.{_dataset}.{_INDIVIDUAL_TABLE}`"
            f" WHERE hs_createdate IS NOT NULL ORDER BY 1"
        ).result()
        all_dates_sorted = sorted({row.hs_createdate for row in _dates_rows})
        total_dates = len(all_dates_sorted)
        print(f"[rebuild_all] rebuilding {total_dates} dates in batches of {_BATCH_SIZE}...")
        total_rows = 0
        for _i in range(0, total_dates, _BATCH_SIZE):
            _batch = set(all_dates_sorted[_i:_i + _BATCH_SIZE])
            _batch_start = all_dates_sorted[_i]
            _batch_end   = all_dates_sorted[min(_i + _BATCH_SIZE - 1, total_dates - 1)]
            print(f"[rebuild_all] batch {_i // _BATCH_SIZE + 1}/{(total_dates + _BATCH_SIZE - 1) // _BATCH_SIZE}"
                  f"  {_batch_start} .. {_batch_end}")
            total_rows += _rebuild_daily_buckets(_client, _batch)
        print(f"[rebuild_all] done — {total_rows} rows written to hubspot_leads_module_daily")

    else:  # backfill / legacy
        days = int(sys.argv[1]) if sys.argv[1].isdigit() else None
        n = collect_and_write(days=days)
        print(f"HubSpot Lead module backfill complete: {n} rows")
