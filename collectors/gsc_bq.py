"""
Google Search Console -> BigQuery collector.

Pulls daily organic search data from GSC Search Analytics API and writes
to `gsc_organic_daily`.

Table: gsc_organic_daily
  property     STRING     GSC site URL / property identifier
  date         DATE
  query        STRING     search query
  page         STRING     landing page URL
  clicks       INTEGER
  impressions  INTEGER
  ctr          FLOAT
  position     FLOAT      average position (1 = top)
  loaded_at    TIMESTAMP

Run:
  railway run python -m collectors.gsc_bq          # default: last 3 days
  railway run python -m collectors.gsc_bq 7         # last 7 days
  railway run python -m collectors.gsc_bq 30        # last 30 days

Note: GSC data has a ~2 day lag, so we start from today-3 by default.

PREREQUISITE: The service account referenced by GOOGLE_APPLICATION_CREDENTIALS
must be granted "Full" or "Restricted" user permission on the GSC property
(sc-domain:qoyod.com) in Google Search Console > Settings > Users and permissions.
"""
import os
import sys
import json
from datetime import date, timedelta, datetime, timezone
from io import BytesIO

from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv(override=True)

PROJECT_ID = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
DATASET    = os.getenv("BQ_DATASET", "qoyod_marketing")
TABLE      = "gsc_organic_daily"

# GSC property to query — override with env var GSC_SITE_URL if needed.
# sc-domain: properties cover all subdomains and protocols.
GSC_SITE_URL = os.getenv("GSC_SITE_URL", "sc-domain:qoyod.com")

# GSC API returns at most 25 000 rows per request.
GSC_PAGE_SIZE = 25_000

_BQ_SCHEMA = [
    bigquery.SchemaField("property",    "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("date",        "DATE",      mode="NULLABLE"),
    bigquery.SchemaField("query",       "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("page",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("clicks",      "INTEGER",   mode="NULLABLE"),
    bigquery.SchemaField("impressions", "INTEGER",   mode="NULLABLE"),
    bigquery.SchemaField("ctr",         "FLOAT",     mode="NULLABLE"),
    bigquery.SchemaField("position",    "FLOAT",     mode="NULLABLE"),
    bigquery.SchemaField("loaded_at",   "TIMESTAMP", mode="NULLABLE"),
]


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _bq_client() -> bigquery.Client:
    raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if raw_key and os.path.exists(raw_key):
        creds = service_account.Credentials.from_service_account_file(raw_key)
        return bigquery.Client(project=PROJECT_ID, credentials=creds)
    return bigquery.Client(project=PROJECT_ID)


def _gsc_client():
    """Build Search Console API client using the service account."""
    raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    scopes  = ["https://www.googleapis.com/auth/webmasters.readonly"]
    if raw_key and os.path.exists(raw_key):
        creds = service_account.Credentials.from_service_account_file(
            raw_key, scopes=scopes
        )
    else:
        import google.auth
        creds, _ = google.auth.default(scopes=scopes)
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


# ── Data fetch ────────────────────────────────────────────────────────────────

def _fetch_day(svc, site_url: str, day: date) -> list[dict]:
    """Fetch all GSC rows for a single date, handling pagination."""
    day_str = day.isoformat()
    rows: list[dict] = []
    start_row = 0

    while True:
        body = {
            "startDate":  day_str,
            "endDate":    day_str,
            "dimensions": ["date", "query", "page", "country", "device"],
            "rowLimit":   GSC_PAGE_SIZE,
            "startRow":   start_row,
        }
        resp = svc.searchanalytics().query(siteUrl=site_url, body=body).execute()
        page_rows = resp.get("rows", [])
        if not page_rows:
            break

        for r in page_rows:
            keys = r.get("keys", [])
            rows.append({
                "property":    site_url,
                "date":        keys[0] if len(keys) > 0 else day_str,
                "query":       keys[1] if len(keys) > 1 else None,
                "page":        keys[2] if len(keys) > 2 else None,
                # country + device are fetched but not stored in current schema
                "clicks":      int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr":         round(float(r.get("ctr", 0.0)), 6),
                "position":    round(float(r.get("position", 0.0)), 4),
            })

        if len(page_rows) < GSC_PAGE_SIZE:
            # Last page — no more rows to fetch
            break
        start_row += GSC_PAGE_SIZE

    return rows


def _fetch_range(svc, site_url: str, start: date, end: date) -> list[dict]:
    """Fetch GSC data for a date range, day by day."""
    all_rows: list[dict] = []
    cur = start
    while cur <= end:
        day_rows = _fetch_day(svc, site_url, cur)
        print(f"[gsc]   {cur.isoformat()}: {len(day_rows)} rows")
        all_rows.extend(day_rows)
        cur += timedelta(days=1)
    return all_rows


# ── BigQuery write ────────────────────────────────────────────────────────────

def _ensure_table(bq: bigquery.Client) -> None:
    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"
    try:
        bq.get_table(table_ref)
    except Exception:
        bq.create_table(bigquery.Table(table_ref, schema=_BQ_SCHEMA))
        print(f"[gsc] created table {table_ref}")


def _upsert_rows(bq: bigquery.Client, rows: list[dict], site_url: str) -> int:
    """Idempotent upsert: delete existing (property, date) rows then insert."""
    if not rows:
        return 0

    table_ref = f"{PROJECT_ID}.{DATASET}.{TABLE}"
    dates     = list({r["date"] for r in rows})
    date_list = ", ".join(f"'{d}'" for d in dates)

    # Delete existing rows for this property × date range
    bq.query(f"""
        DELETE FROM `{table_ref}`
        WHERE property = '{site_url}'
          AND date IN ({date_list})
    """).result()

    # Stamp loaded_at
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        r["loaded_at"] = now

    ndjson = b"\n".join(json.dumps(r, default=str).encode() for r in rows)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=_BQ_SCHEMA,
    )
    bq.load_table_from_file(BytesIO(ndjson), table_ref, job_config=job_config).result()
    return len(rows)


# ── Entry point ───────────────────────────────────────────────────────────────

def collect_and_write(days: int = 3) -> int:
    """
    Pull `days` days of GSC data ending yesterday-2 (GSC lag) and write to BQ.

    Returns the number of rows written.
    """
    if not PROJECT_ID:
        print("[gsc] BQ_PROJECT_ID not set — skipping")
        return 0

    # GSC data lags ~2 days; end at yesterday-2 to avoid incomplete days.
    end   = date.today() - timedelta(days=2)
    start = end - timedelta(days=days - 1)

    site_url = GSC_SITE_URL
    print(f"[gsc] {start} -> {end}  site={site_url}")

    svc = _gsc_client()
    bq  = _bq_client()
    _ensure_table(bq)

    rows    = _fetch_range(svc, site_url, start, end)
    written = _upsert_rows(bq, rows, site_url)
    print(f"[gsc] wrote {written} rows -> {TABLE}")
    return written


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    collect_and_write(days=days)
