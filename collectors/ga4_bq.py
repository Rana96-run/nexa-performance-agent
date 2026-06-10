"""
GA4 -> BigQuery collector.

Uses the GA4 Data API (REST via google-api-python-client) to pull daily
website metrics into `ga4_sessions_daily`.

Table: ga4_sessions_daily
  date              DATE
  property_id       STRING
  sessions          INT64
  engaged_sessions  INT64
  new_users         INT64
  total_users       INT64
  conversions       INT64     (all key_events / goal completions)
  bounce_rate       FLOAT64
  avg_session_duration_s FLOAT64
  source_medium     STRING    (top source/medium by sessions, for reference)
  collected_at      TIMESTAMP

Run:
  railway run python collectors/ga4_bq.py
  railway run python collectors/ga4_bq.py --days 30
  railway run python collectors/ga4_bq.py --incremental
"""
import os
import json
import argparse
from datetime import date, timedelta, datetime, timezone
from io import BytesIO

from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv(override=True)

PROJECT_ID  = os.getenv("BQ_PROJECT_ID")
DATASET     = os.getenv("BQ_DATASET", "qoyod_marketing")
TABLE       = "ga4_sessions_daily"
PROPERTY_ID = os.getenv("GA4_PROPERTY_ID", "")  # e.g. "517912363"

_BQ_SCHEMA = [
    bigquery.SchemaField("date",                    "DATE",      mode="REQUIRED"),
    bigquery.SchemaField("property_id",             "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("sessions",                "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("engaged_sessions",        "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("new_users",               "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("total_users",             "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("conversions",             "INT64",     mode="NULLABLE"),
    bigquery.SchemaField("bounce_rate",             "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("avg_session_duration_s",  "FLOAT64",   mode="NULLABLE"),
    bigquery.SchemaField("top_source_medium",       "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("collected_at",            "TIMESTAMP", mode="NULLABLE"),
]


def _bq_client():
    raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if raw_key and os.path.exists(raw_key):
        creds = service_account.Credentials.from_service_account_file(raw_key)
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    return bigquery.Client(project=PROJECT_ID)


def _ga4_client():
    """Build GA4 Data API client using the same service-account credentials."""
    raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    scopes  = ["https://www.googleapis.com/auth/analytics.readonly"]
    if raw_key and os.path.exists(raw_key):
        creds = service_account.Credentials.from_service_account_file(
            raw_key, scopes=scopes
        )
    else:
        # Fall back to ADC (Application Default Credentials)
        import google.auth
        creds, _ = google.auth.default(scopes=scopes)
    return build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)


def _date_window(days: int, incremental: bool):
    end = date.today() - timedelta(days=1)
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)
    return start, end


def _fetch_daily(svc, property_id: str, start: date, end: date) -> list[dict]:
    """Pull daily aggregate metrics from GA4 Data API."""
    body = {
        "dateRanges": [{"startDate": str(start), "endDate": str(end)}],
        "dimensions": [{"name": "date"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "engagedSessions"},
            {"name": "newUsers"},
            {"name": "totalUsers"},
            {"name": "conversions"},
            {"name": "bounceRate"},
            {"name": "averageSessionDuration"},
        ],
        "orderBys": [{"dimension": {"dimensionName": "date"}}],
        "limit": 3000,
    }
    resp = (
        svc.properties()
           .runReport(property=f"properties/{property_id}", body=body)
           .execute()
    )
    rows = []
    for row in resp.get("rows", []):
        dims  = row.get("dimensionValues", [])
        vals  = row.get("metricValues",    [])
        d_str = dims[0]["value"] if dims else None
        if not d_str or len(d_str) != 8:
            continue
        iso_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
        rows.append({
            "date":                   iso_date,
            "property_id":            property_id,
            "sessions":               int(float(vals[0]["value"])) if len(vals) > 0 else 0,
            "engaged_sessions":       int(float(vals[1]["value"])) if len(vals) > 1 else 0,
            "new_users":              int(float(vals[2]["value"])) if len(vals) > 2 else 0,
            "total_users":            int(float(vals[3]["value"])) if len(vals) > 3 else 0,
            "conversions":            int(float(vals[4]["value"])) if len(vals) > 4 else 0,
            "bounce_rate":            round(float(vals[5]["value"]), 6) if len(vals) > 5 else None,
            "avg_session_duration_s": round(float(vals[6]["value"]), 3) if len(vals) > 6 else None,
        })
    return rows


def _fetch_top_source_medium(svc, property_id: str, start: date, end: date) -> dict[str, str]:
    """Return {date_str: 'source / medium'} for the top source/medium per day."""
    body = {
        "dateRanges": [{"startDate": str(start), "endDate": str(end)}],
        "dimensions": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}],
        "metrics": [{"name": "sessions"}],
        "orderBys": [
            {"dimension": {"dimensionName": "date"}},
            {"metric": {"metricName": "sessions"}, "desc": True},
        ],
        "limit": 3000,
    }
    try:
        resp = (
            svc.properties()
               .runReport(property=f"properties/{property_id}", body=body)
               .execute()
        )
    except Exception:
        return {}

    top: dict[str, str] = {}
    for row in resp.get("rows", []):
        dims  = row.get("dimensionValues", [])
        d_str = dims[0]["value"] if dims else None
        if not d_str or len(d_str) != 8:
            continue
        iso_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
        if iso_date not in top:
            top[iso_date] = dims[1]["value"] if len(dims) > 1 else ""
    return top


def _ensure_table(bq: bigquery.Client) -> None:
    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"
    try:
        bq.get_table(table_ref)
    except Exception:
        bq.create_table(bigquery.Table(table_ref, schema=_BQ_SCHEMA))
        print(f"[ga4] created table {table_ref}")


def _upsert_rows(bq: bigquery.Client, rows: list[dict]) -> int:
    """Idempotent upsert: delete existing (date, property_id) rows, then insert."""
    if not rows:
        return 0

    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"
    dates     = list({r["date"] for r in rows})
    date_list = ", ".join(f"'{d}'" for d in dates)

    bq.query(f"""
        DELETE FROM `{table_ref}`
        WHERE property_id = '{PROPERTY_ID}'
          AND date IN ({date_list})
    """).result()

    ndjson = b"\n".join(json.dumps(r, default=str).encode() for r in rows)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        schema=_BQ_SCHEMA,
    )
    bq.load_table_from_file(BytesIO(ndjson), table_ref, job_config=job_config).result()
    return len(rows)


def collect_and_write(days: int = None, incremental: bool = False) -> int:
    if not PROPERTY_ID:
        print("[ga4] GA4_PROPERTY_ID not set — skipping")
        return 0
    if not PROJECT_ID:
        print("[ga4] BQ_PROJECT_ID not set — skipping")
        return 0

    start, end = _date_window(days, incremental)
    print(f"[ga4] sessions {start} -> {end}  property={PROPERTY_ID}")

    svc  = _ga4_client()
    bq   = _bq_client()
    _ensure_table(bq)

    now = datetime.now(timezone.utc).isoformat()

    rows       = _fetch_daily(svc, PROPERTY_ID, start, end)
    top_sm     = _fetch_top_source_medium(svc, PROPERTY_ID, start, end)

    for r in rows:
        r["top_source_medium"] = top_sm.get(r["date"], "")
        r["collected_at"]      = now

    written = _upsert_rows(bq, rows)
    print(f"[ga4] wrote {written} rows -> {TABLE}")
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",        type=int,  default=None)
    parser.add_argument("--incremental", action="store_true")
    args = parser.parse_args()
    collect_and_write(days=args.days, incremental=args.incremental)
