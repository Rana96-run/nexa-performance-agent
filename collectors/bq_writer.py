"""
BigQuery writer — shared helper for all collectors.

All channel collectors write daily rows into these tables:
  - campaigns_daily     (one row per campaign per day per channel)
  - ads_daily           (one row per ad per day — optional, heavier)
  - hubspot_leads_daily (HubSpot contacts aggregated by utm_campaign per day)
  - campaign_status     (current status snapshot, overwritten daily)

Idempotent: we MERGE on (date, channel, campaign_id) so re-runs overwrite
the same day's data instead of duplicating.
"""
import os
from datetime import date
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv(override=True)   # always prefer .env over stale system env vars

PROJECT_ID = os.getenv("BQ_PROJECT_ID")
DATASET    = os.getenv("BQ_DATASET", "qoyod_marketing")
LOCATION   = os.getenv("BQ_LOCATION", "europe-west1")

# Thresholds pulled from the central config — see config.py
try:
    from config import (
        CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
        CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
    )
except Exception:
    # Hard defaults so this module still works if config import fails
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING = 5.50, 7.50, 8.00
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING = 11.00, 17.00, 21.33

# Resolve the key path: honour absolute paths in .env; fall back to the file
# sitting next to this repo if nothing is set.
_raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if _raw_key and os.path.isabs(_raw_key):
    KEY_PATH = _raw_key
elif _raw_key:
    # Relative path in env — resolve relative to repo root (one level up from collectors/)
    KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), _raw_key.lstrip("./\\"))
else:
    KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bigquery-key.json")


def get_client():
    creds = service_account.Credentials.from_service_account_file(KEY_PATH)
    return bigquery.Client(project=PROJECT_ID, credentials=creds, location=LOCATION)


# ---------- SCHEMAS ----------

CAMPAIGNS_DAILY_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("channel", "STRING", mode="REQUIRED"),       # google_ads / meta / snapchat / tiktok
    bigquery.SchemaField("account_id", "STRING"),
    bigquery.SchemaField("campaign_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("campaign_name", "STRING"),
    bigquery.SchemaField("status", "STRING"),                          # ENABLED / PAUSED / LEARNING / REMOVED
    bigquery.SchemaField("objective", "STRING"),
    bigquery.SchemaField("spend", "FLOAT64"),
    bigquery.SchemaField("impressions", "INT64"),
    bigquery.SchemaField("clicks", "INT64"),
    bigquery.SchemaField("ctr", "FLOAT64"),
    bigquery.SchemaField("leads", "INT64"),                            # platform-reported leads
    bigquery.SchemaField("conversions", "FLOAT64"),
    bigquery.SchemaField("cpl", "FLOAT64"),
    bigquery.SchemaField("currency", "STRING"),                        # always "USD" — collectors convert before writing
    bigquery.SchemaField("spend_native", "FLOAT64"),                   # spend in the platform's native currency
    bigquery.SchemaField("currency_native", "STRING"),                 # e.g. "SAR", "USD"
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
]

HUBSPOT_LEADS_DAILY_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("utm_campaign", "STRING"),
    bigquery.SchemaField("utm_source", "STRING"),
    bigquery.SchemaField("utm_medium", "STRING"),
    bigquery.SchemaField("qoyod_source", "STRING"),
    bigquery.SchemaField("leads_count", "INT64"),
    bigquery.SchemaField("mqls_count", "INT64"),
    bigquery.SchemaField("sqls_count", "INT64"),
    bigquery.SchemaField("opportunities_count", "INT64"),
    bigquery.SchemaField("customers_count", "INT64"),
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
]

ADS_DAILY_SCHEMA = [
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("channel", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("campaign_id", "STRING"),
    bigquery.SchemaField("campaign_name", "STRING"),
    bigquery.SchemaField("adset_id", "STRING"),
    bigquery.SchemaField("adset_name", "STRING"),
    bigquery.SchemaField("ad_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("ad_name", "STRING"),
    bigquery.SchemaField("status", "STRING"),
    bigquery.SchemaField("spend", "FLOAT64"),
    bigquery.SchemaField("impressions", "INT64"),
    bigquery.SchemaField("clicks", "INT64"),
    bigquery.SchemaField("ctr", "FLOAT64"),
    bigquery.SchemaField("leads", "INT64"),
    bigquery.SchemaField("cpl", "FLOAT64"),
    bigquery.SchemaField("frequency", "FLOAT64"),
    bigquery.SchemaField("updated_at", "TIMESTAMP"),
]

TABLES = {
    "campaigns_daily": CAMPAIGNS_DAILY_SCHEMA,
    "ads_daily": ADS_DAILY_SCHEMA,
    "hubspot_leads_daily": HUBSPOT_LEADS_DAILY_SCHEMA,
}


# ---------- BOOTSTRAP ----------

TABLE_CLUSTERS = {
    "campaigns_daily":    ["channel", "campaign_id"],
    "ads_daily":          ["channel", "campaign_id", "ad_id"],
    "hubspot_leads_daily": ["qoyod_source"],
}


def ensure_dataset_and_tables():
    """Create dataset + all tables with partitioning + clustering."""
    client = get_client()
    dataset_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET}")
    dataset_ref.location = LOCATION
    try:
        client.create_dataset(dataset_ref, exists_ok=True)
        print(f"[OK] Dataset {PROJECT_ID}.{DATASET} ready.")
    except Exception as e:
        print(f"[ERROR] Could not create dataset: {e}")
        raise

    for table_name, schema in TABLES.items():
        table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"
        table = bigquery.Table(table_id, schema=schema)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="date",
        )
        if table_name in TABLE_CLUSTERS:
            table.clustering_fields = TABLE_CLUSTERS[table_name]
        try:
            client.create_table(table, exists_ok=True)
            print(f"[OK] Table {table_name} ready.")
        except Exception as e:
            print(f"[ERROR] Could not create table {table_name}: {e}")
            raise


# ---------- WRITE ----------

def upsert_rows(table_name: str, rows: list[dict], key_fields: list[str]):
    """
    Idempotent write: for each distinct DATE in `rows`, DELETE that partition's
    rows, then INSERT fresh. Replaces the whole day rather than per-key DELETE,
    which stays well under BQ's 1 MB query limit even for large backfills.
    """
    if not rows:
        print(f"[SKIP] {table_name}: no rows to write.")
        return 0

    client = get_client()
    table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"

    # Idempotent delete:
    #   - Always scope by date (cheap, uses partition pruning).
    #   - Also scope by the second key-field if present (e.g. "channel", "qoyod_source")
    #     so we don't wipe sibling data in shared tables like campaigns_daily.
    #   - Use IN (...) on the scoping value, one DELETE per date.
    from collections import defaultdict
    scope_field = key_fields[1] if len(key_fields) > 1 else None
    by_date = defaultdict(set)
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        if scope_field:
            by_date[d].add(str(r.get(scope_field, "")))
        else:
            by_date[d].add(None)

    for d, scope_vals in by_date.items():
        params = [bigquery.ScalarQueryParameter("d", "DATE", d)]
        if scope_field:
            sv_list = sorted(scope_vals)
            params.append(bigquery.ArrayQueryParameter("sv", "STRING", sv_list))
            delete_sql = (
                f"DELETE FROM `{table_id}` "
                f"WHERE date = @d AND {scope_field} IN UNNEST(@sv)"
            )
        else:
            delete_sql = f"DELETE FROM `{table_id}` WHERE date = @d"
        client.query(
            delete_sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()

    # Use a LOAD job (not streaming inserts) — load jobs land immediately in the
    # partition (not the streaming buffer) so subsequent DELETEs work, and they're
    # free. We upload NDJSON.
    import json as _json
    ndjson = "\n".join(_json.dumps(r, default=str) for r in rows).encode("utf-8")

    # Pass the explicit schema so ALLOW_FIELD_ADDITION can add new columns
    # (e.g. 'currency') to an existing table that was created before the field
    # was added to CAMPAIGNS_DAILY_SCHEMA.  Without an explicit schema the load
    # job validates against only the existing table schema and rejects extras.
    schema = TABLES.get(table_name)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        schema=schema,  # None → autodetect disabled but ALLOW_FIELD_ADDITION still triggers
    )
    from io import BytesIO
    load_job = client.load_table_from_file(
        BytesIO(ndjson), table_id, job_config=job_config
    )
    load_job.result()
    print(f"[OK] Wrote {len(rows)} rows to {table_name} ({len(by_date)} partitions, load job)")
    return len(rows)


# ---------- VIEWS ----------

CAMPAIGN_PERFORMANCE_VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT_ID}.{DATASET}.campaign_performance` AS
SELECT
  c.date,
  c.channel,
  c.campaign_name,
  c.status,
  c.spend,
  c.leads AS platform_leads,
  c.conversions,
  c.cpl AS platform_cpl,
  h.leads_count  AS hs_leads,
  h.sqls_count   AS hs_sqls,
  h.customers_count AS hs_customers,
  SAFE_DIVIDE(c.spend, h.sqls_count)                       AS cpql,
  SAFE_DIVIDE(h.sqls_count + h.customers_count, h.leads_count) AS qual_rate,
  -- Thresholds in USD — values injected from config.py at view-creation time
  CASE
    WHEN c.cpl < {CPL_SCALE} THEN 'scale'
    WHEN c.cpl <= {CPL_ACCEPTABLE} THEN 'acceptable'
    WHEN c.cpl <= {CPL_WARNING} THEN 'warning'
    ELSE 'pause_zone'
  END AS cpl_zone,
  CASE
    WHEN SAFE_DIVIDE(c.spend, h.sqls_count) IS NULL THEN 'no_data'
    WHEN SAFE_DIVIDE(c.spend, h.sqls_count) < {CPQL_SCALE} THEN 'scale'
    WHEN SAFE_DIVIDE(c.spend, h.sqls_count) <= {CPQL_ACCEPTABLE} THEN 'acceptable'
    WHEN SAFE_DIVIDE(c.spend, h.sqls_count) <= {CPQL_WARNING} THEN 'warning'
    ELSE 'pause_zone'
  END AS cpql_zone
FROM `{PROJECT_ID}.{DATASET}.campaigns_daily` c
LEFT JOIN `{PROJECT_ID}.{DATASET}.hubspot_leads_daily` h
  ON c.date = h.date
 AND LOWER(c.campaign_name) = LOWER(h.utm_campaign)
"""


def create_views():
    client = get_client()
    client.query(CAMPAIGN_PERFORMANCE_VIEW_SQL).result()
    print("[OK] View campaign_performance created.")


# ---------- TEST ----------

def test_connection():
    client = get_client()
    query = "SELECT 1 AS ok, CURRENT_TIMESTAMP() AS now"
    rows = list(client.query(query).result())
    print(f"[OK] Connected to {PROJECT_ID}. Test query returned: {rows[0].ok} at {rows[0].now}")
    return True


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "test":
        test_connection()
    elif cmd == "bootstrap":
        test_connection()
        ensure_dataset_and_tables()
        create_views()
    elif cmd == "views":
        create_views()
    else:
        print("Usage: python collectors/bq_writer.py [test|bootstrap|views]")
