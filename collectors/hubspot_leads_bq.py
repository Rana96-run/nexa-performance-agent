"""
HubSpot Lead module -> BigQuery.
Writes one row per lead per day (by createdate) with qoyod_source,
pipeline, stage, qualification status, disqualification reasons, and UTMs.
"""
import os
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
    "hs_createdate", "hs_pipeline", "hs_pipeline_stage", "hs_lead_is_open",
    "lead_qoyod_source",
    "lead_utm_campaign", "lead_utm_audience", "lead_utm_content",
    "lead_utm_term", "lead_utm_source", "lead_utm_medium",
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
      - incremental=True: last 2 days (scheduled runs)
      - days=N / start_date=: custom window
      - default: YTD (initial backfill only)
    """
    _load_pipelines()

    end = date.today()
    if incremental:
        start = end - timedelta(days=2)
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
                                     "disq_reasons": defaultdict(int)})

    # HubSpot Search caps at 10k results — walk 7-day windows.
    total_fetched, pages = 0, 0
    window = timedelta(days=7)
    win_start = start
    end_dt = end + timedelta(days=1)
    while win_start < end_dt:
        win_end = min(win_start + window, end_dt)
        w_since = int(datetime(win_start.year, win_start.month, win_start.day).timestamp() * 1000)
        w_until = int(datetime(win_end.year, win_end.month, win_end.day).timestamp() * 1000)
        after = None
        win_count = 0
        while True:
            data = _search_leads(w_since, until_ms=w_until, after=after)
            for row in data.get("results", []):
                p = row.get("properties", {})
                created = (p.get("hs_createdate") or "")[:10]
                if not created:
                    continue
                pid, plabel, slabel = _stage_info(p.get("hs_pipeline_stage"))
                is_open = str(p.get("hs_lead_is_open", "0")) == "1"
                qual = _is_qualified(slabel)
                disq = _is_disqualified(slabel)

                key = (
                    created,
                    p.get("lead_qoyod_source") or "Unknown",
                    plabel or "Unknown",
                    slabel or "Unknown",
                    (p.get("lead_utm_campaign") or "").strip() or None,
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
                if is_open:
                    b["open"] += 1
                total_fetched += 1
                win_count += 1

            pages += 1
            paging = data.get("paging", {}).get("next", {})
            after = paging.get("after")
            if not after or pages >= 500:
                break
        print(f"[leads] {win_start}..{win_end}: {win_count} leads")
        win_start = win_end

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for key, b in buckets.items():
        (d, src, pipeline, stage, utm_c, utm_a, utm_co, utm_s, utm_m, utm_t) = key
        top_reason = max(b["disq_reasons"].items(), key=lambda x: x[1])[0] if b["disq_reasons"] else None
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
            "updated_at": now,
        })

    print(f"Processed {total_fetched} leads -> {len(rows)} daily buckets")
    _ensure_table_exists()
    for r in rows:  # normalize None utm_campaign for idempotent key
        if r["lead_utm_campaign"] is None:
            r["lead_utm_campaign"] = "__none__"
    return upsert_rows("hubspot_leads_module_daily", rows,
                       key_fields=["date", "qoyod_source", "pipeline", "stage", "lead_utm_campaign"])


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
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="date")
    table.clustering_fields = ["qoyod_source", "pipeline"]
    client.create_table(table, exists_ok=True)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"HubSpot Lead module backfill complete: {n} rows")
