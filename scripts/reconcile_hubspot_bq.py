"""
HubSpot ↔ BigQuery reconciliation script.

Queries BQ and HubSpot for the last 7 days, compares lead/deal counts and
amounts, writes one result row to `reconciliation_results`, and prints a summary.

Run: python scripts/reconcile_hubspot_bq.py
Exit code: always 0 (failures are alerts, not pipeline stoppers).

Tolerances:
  leads  ≤ 2%
  deals  ≤ 2%
  amount ≤ 5%

BQ auth: from collectors.bq_writer import get_client
Write:   load_table_from_file(BytesIO(ndjson)) — no streaming inserts.
"""
import io
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv(override=True)

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID    = os.getenv("BQ_PROJECT_ID")
DATASET       = os.getenv("BQ_DATASET", "qoyod_marketing")
HS_TOKEN      = os.getenv("HUBSPOT_ACCESS_TOKEN", "")

LEADS_TOL_PCT  = 2.0
DEALS_TOL_PCT  = 2.0
AMOUNT_TOL_PCT = 5.0

SAR_TO_USD = 3.75  # HubSpot stores amounts in SAR natively

# ── Date window ───────────────────────────────────────────────────────────────

_tz_riyadh = timezone(timedelta(hours=3))
_today_riyadh = datetime.now(_tz_riyadh).date()
WINDOW_END   = _today_riyadh - timedelta(days=1)   # yesterday
WINDOW_START = _today_riyadh - timedelta(days=7)    # 7 days ago

# Millisecond timestamps for HubSpot API (UTC midnight boundaries)
_win_start_dt = datetime(WINDOW_START.year, WINDOW_START.month, WINDOW_START.day,
                         tzinfo=timezone.utc)
_win_end_dt   = datetime(WINDOW_END.year,   WINDOW_END.month,   WINDOW_END.day,
                         23, 59, 59, tzinfo=timezone.utc)
HS_START_MS = int(_win_start_dt.timestamp() * 1000)
HS_END_MS   = int(_win_end_dt.timestamp()   * 1000)

# ── BQ schema for reconciliation_results ─────────────────────────────────────

RECON_SCHEMA = [
    bigquery.SchemaField("run_date",          "DATE"),
    bigquery.SchemaField("window_start",       "DATE"),
    bigquery.SchemaField("window_end",         "DATE"),
    bigquery.SchemaField("leads_bq",           "INT64"),
    bigquery.SchemaField("leads_hs",           "INT64"),
    bigquery.SchemaField("leads_delta_pct",    "FLOAT64"),
    bigquery.SchemaField("deals_bq",           "INT64"),
    bigquery.SchemaField("deals_hs",           "INT64"),
    bigquery.SchemaField("deals_delta_pct",    "FLOAT64"),
    bigquery.SchemaField("amount_bq_usd",      "FLOAT64"),
    bigquery.SchemaField("amount_hs_usd",      "FLOAT64"),
    bigquery.SchemaField("amount_delta_pct",   "FLOAT64"),
    bigquery.SchemaField("passed",             "BOOL"),
    bigquery.SchemaField("note",               "STRING"),
]

TABLE_NAME = "reconciliation_results"

# ── Helpers ───────────────────────────────────────────────────────────────────

def delta_pct(bq_val: float, hs_val: float) -> float:
    """abs(bq - hs) / max(bq, hs, 1) * 100"""
    denom = max(bq_val, hs_val, 1.0)
    return abs(bq_val - hs_val) / denom * 100.0


def get_bq_client():
    from collectors.bq_writer import get_client
    return get_client()


def ensure_recon_table(client: bigquery.Client) -> str:
    table_id = f"{PROJECT_ID}.{DATASET}.{TABLE_NAME}"
    try:
        client.get_table(table_id)
    except Exception:
        table = bigquery.Table(table_id, schema=RECON_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="run_date",
        )
        client.create_table(table, exists_ok=True)
        print(f"[OK] Created table {TABLE_NAME}")
    return table_id


# ── BQ queries ────────────────────────────────────────────────────────────────

def query_bq_leads(client: bigquery.Client) -> tuple[int, int]:
    """Returns (leads_total, leads_qualified) from hubspot_leads_individual."""
    sql = f"""
    SELECT
      COUNT(*)                                AS leads_total,
      COUNTIF(is_qualified)                   AS leads_qualified
    FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_individual`
    WHERE DATE(hs_createdate, 'Asia/Riyadh')
        BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
            AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    """
    row = list(client.query(sql).result())[0]
    return int(row.leads_total), int(row.leads_qualified)


def query_bq_deals(client: bigquery.Client) -> tuple[int, float]:
    """Returns (deals_total, revenue_won_usd) from hubspot_deals_individual."""
    sql = f"""
    SELECT
      COUNT(*)                                              AS deals_total,
      ROUND(SUM(IF(is_won, amount, 0)), 2)                 AS revenue_won
    FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_individual`
    WHERE DATE(createdate, 'Asia/Riyadh')
        BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
            AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
    """
    row = list(client.query(sql).result())[0]
    return int(row.deals_total), float(row.revenue_won or 0.0)


# ── HubSpot API calls ─────────────────────────────────────────────────────────

_HS_HEADERS = {
    "Authorization": f"Bearer {HS_TOKEN}",
    "Content-Type":  "application/json",
}

_HS_CONTACTS_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"
_HS_DEALS_URL    = "https://api.hubapi.com/crm/v3/objects/deals/search"


def _hs_date_filter(prop: str, gte_ms: int, lte_ms: int) -> list[dict]:
    return [
        {"propertyName": prop, "operator": "GTE", "value": str(gte_ms)},
        {"propertyName": prop, "operator": "LTE", "value": str(lte_ms)},
    ]


def query_hs_leads() -> int:
    """Return total contact count created in the window."""
    payload = {
        "filterGroups": [{"filters": _hs_date_filter("createdate", HS_START_MS, HS_END_MS)}],
        "properties": ["createdate"],
        "limit": 1,
    }
    resp = requests.post(_HS_CONTACTS_URL, headers=_HS_HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    return int(resp.json().get("total", 0))


def query_hs_deals() -> tuple[int, float]:
    """Return (total_deals, sum_of_amount_in_usd) for deals created in the window.

    Paginates through all results and sums the `amount` property client-side.
    HubSpot stores amounts in SAR natively; we divide by 3.75 to convert to USD.
    """
    deals_total = 0
    amount_sar  = 0.0
    after       = None

    base_payload = {
        "filterGroups": [{"filters": _hs_date_filter("createdate", HS_START_MS, HS_END_MS)}],
        "properties": ["createdate", "amount"],
        "limit": 100,
    }

    while True:
        payload = dict(base_payload)
        if after:
            payload["after"] = after

        resp = requests.post(_HS_DEALS_URL, headers=_HS_HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if deals_total == 0 and after is None:
            deals_total = int(data.get("total", len(results)))

        for deal in results:
            amt = deal.get("properties", {}).get("amount")
            if amt:
                try:
                    amount_sar += float(amt)
                except (ValueError, TypeError):
                    pass

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        if not after or not results:
            break

    amount_usd = round(amount_sar / SAR_TO_USD, 2)
    return deals_total, amount_usd


# ── Write result row ──────────────────────────────────────────────────────────

def write_result(client: bigquery.Client, table_id: str, row: dict) -> None:
    ndjson_bytes = (json.dumps(row, default=str) + "\n").encode("utf-8")
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema=RECON_SCHEMA,
    )
    load_job = client.load_table_from_file(
        io.BytesIO(ndjson_bytes), table_id, job_config=job_config
    )
    load_job.result()
    print(f"[OK] Result written to {TABLE_NAME}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n=== HubSpot ↔ BQ Reconciliation ({WINDOW_START} to {WINDOW_END}) ===")

    client   = get_bq_client()
    table_id = ensure_recon_table(client)

    # --- BQ side ---
    print("Querying BQ leads...")
    leads_bq, _ = query_bq_leads(client)

    print("Querying BQ deals...")
    deals_bq, amount_bq = query_bq_deals(client)

    # --- HubSpot side ---
    print("Querying HubSpot leads (contacts)...")
    leads_hs = query_hs_leads()

    print("Querying HubSpot deals (paginating)...")
    deals_hs, amount_hs = query_hs_deals()

    # --- Deltas ---
    leads_delta  = delta_pct(float(leads_bq),  float(leads_hs))
    deals_delta  = delta_pct(float(deals_bq),  float(deals_hs))
    amount_delta = delta_pct(amount_bq,          amount_hs)

    leads_pass  = leads_delta  <= LEADS_TOL_PCT
    deals_pass  = deals_delta  <= DEALS_TOL_PCT
    amount_pass = amount_delta <= AMOUNT_TOL_PCT
    overall     = leads_pass and deals_pass and amount_pass

    # --- Print summary ---
    def tag(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    print(f"\nLeads:   BQ={leads_bq}  HS={leads_hs}  delta={leads_delta:.2f}%  [{tag(leads_pass)}]")
    print(f"Deals:   BQ={deals_bq}  HS={deals_hs}  delta={deals_delta:.2f}%  [{tag(deals_pass)}]")
    print(f"Amount:  BQ=${amount_bq:.2f}  HS=${amount_hs:.2f}  delta={amount_delta:.2f}%  [{tag(amount_pass)}]")
    print(f"Overall: {tag(overall)}\n")

    # Build note
    failures = []
    if not leads_pass:
        failures.append(f"leads delta {leads_delta:.2f}% > {LEADS_TOL_PCT}%")
    if not deals_pass:
        failures.append(f"deals delta {deals_delta:.2f}% > {DEALS_TOL_PCT}%")
    if not amount_pass:
        failures.append(f"amount delta {amount_delta:.2f}% > {AMOUNT_TOL_PCT}%")
    note = "; ".join(failures) if failures else "all checks within tolerance"

    # --- Write to BQ ---
    row = {
        "run_date":        _today_riyadh.isoformat(),
        "window_start":    WINDOW_START.isoformat(),
        "window_end":      WINDOW_END.isoformat(),
        "leads_bq":        leads_bq,
        "leads_hs":        leads_hs,
        "leads_delta_pct": round(leads_delta, 4),
        "deals_bq":        deals_bq,
        "deals_hs":        deals_hs,
        "deals_delta_pct": round(deals_delta, 4),
        "amount_bq_usd":   amount_bq,
        "amount_hs_usd":   amount_hs,
        "amount_delta_pct": round(amount_delta, 4),
        "passed":          overall,
        "note":            note,
    }
    write_result(client, table_id, row)

    # Always exit 0 — reconciliation failures are alerts, not pipeline stoppers.
    return 0


if __name__ == "__main__":
    sys.exit(main())
