"""
HubSpot Deals -> BigQuery.
One row per (create-date, qoyod_source, pipeline, stage_status, utm_*) bucket.
Key: classifies deals as won / lost / open via stage.probability.
  probability == 1.0 -> won
  probability == 0.0 -> lost
  0 < probability < 1 -> open (in progress)
"""
import os
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows, get_client
from collectors.currency import to_usd, normalize_currency

load_dotenv()
TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
BASE = "https://api.hubapi.com"

# Qoyod is a Saudi company — deals are booked in SAR unless the deal record
# explicitly overrides via deal_currency_code. All amounts in BQ are stored
# in USD (currency="USD"); native SAR values are kept in *_native columns.
DEFAULT_DEAL_CURRENCY = "SAR"

PROPERTIES = [
    "createdate", "closedate", "dealstage", "pipeline", "dealname",
    "amount", "hs_acv", "hs_tcv",
    "deal_currency_code",
    "deal_qoyod_source",
    "deal_utm_campaign", "deal_utm_audience", "deal_utm_content",
    "deal_utm_term", "deal_utm_source", "deal_utm_medium",
    # Fallback chain — see analysers/channel_inference.py.
    "deal_original_traffic_source",
    "deal_latest_traffic_source",
    "deal_original_traffic_source_drilldown_1",
    "deal_latest_traffic_source_drilldown_1",
    "deal_original_traffic_source_drilldown_2",
    "deal_latest_traffic_source_drilldown_2",
    "hs_v2_time_in_current_stage",
    "hs_is_closed_won", "hs_is_closed",
]

# stage_id -> (pipeline_id, pipeline_label, stage_label, probability)
_CACHE = {"stages": None, "pipelines": None}


def _load_pipelines():
    if _CACHE["stages"] is not None:
        return
    r = requests.get(f"{BASE}/crm/v3/pipelines/deals",
                     headers={"Authorization": f"Bearer {TOKEN}"})
    r.raise_for_status()
    pipelines, stages = {}, {}
    for p in r.json().get("results", []):
        pipelines[p["id"]] = p["label"]
        for s in p.get("stages", []):
            prob = s.get("metadata", {}).get("probability")
            try:
                prob = float(prob) if prob is not None else None
            except (TypeError, ValueError):
                prob = None
            stages[s["id"]] = (p["id"], p["label"], s["label"], prob)
    _CACHE["pipelines"] = pipelines
    _CACHE["stages"] = stages


def _classify_stage(stage_id):
    """Return (pipeline_label, stage_label, status) where status ∈ {won,lost,open,unknown}."""
    if not stage_id:
        return None, None, "unknown"
    info = _CACHE["stages"].get(stage_id)
    if not info:
        return None, None, "unknown"
    _pid, plabel, slabel, prob = info
    if prob == 1.0:
        status = "won"
    elif prob == 0.0:
        status = "lost"
    elif prob is not None:
        status = "open"
    else:
        # fallback by stage label
        sl = (slabel or "").lower()
        if "won" in sl:
            status = "won"
        elif "lost" in sl:
            status = "lost"
        else:
            status = "open"
    return plabel, slabel, status


def _search_deals(since_ms, until_ms=None, after=None):
    filters = [{"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)}]
    if until_ms is not None:
        filters.append({"propertyName": "createdate", "operator": "LT", "value": str(until_ms)})
    body = {
        "filterGroups": [{"filters": filters}],
        "properties": PROPERTIES,
        "limit": 100,
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
    }
    if after:
        body["after"] = after
    r = requests.post(f"{BASE}/crm/v3/objects/deals/search",
                      headers={"Authorization": f"Bearer {TOKEN}",
                               "Content-Type": "application/json"},
                      json=body)
    if r.status_code >= 400:
        print(f"[deals] HTTP {r.status_code} on search:")
        print(r.text[:1500].encode("ascii", "replace").decode())
    r.raise_for_status()
    return r.json()


def _to_float(x):
    try:
        return float(x) if x not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def collect_and_write(days: int = None, start_date: date = None,
                       incremental: bool = False):
    """
    Modes:
      - incremental=True: only last 2 days (normal 12h scheduled runs, light on BQ)
      - days=N: last N days (for a targeted re-pull)
      - start_date=date(Y,M,D): custom window
      - default: YTD (Jan 1 of current year) — use once for initial backfill
    """
    _load_pipelines()
    print(f"[deals] Loaded {len(_CACHE['pipelines'])} pipelines, "
          f"{len(_CACHE['stages'])} stages")

    end = date.today()
    if incremental:
        start = end - timedelta(days=2)
    elif start_date:
        start = start_date
    elif days:
        start = end - timedelta(days=days)
    else:
        start = date(end.year, 1, 1)  # YTD default
    print(f"[deals] Window: {start} -> {end}")
    since_ms = int(datetime(start.year, start.month, start.day).timestamp() * 1000)

    # bucket by (date, channel, pipeline, stage_status, utm_*)
    # Amounts are accumulated twice: once in USD (primary), once in native currency.
    buckets = defaultdict(lambda: {
        "n": 0, "won": 0, "lost": 0, "open": 0,
        "amount": 0.0, "won_amount": 0.0, "lost_amount": 0.0, "open_amount": 0.0,
        "amount_native": 0.0, "won_amount_native": 0.0,
        "lost_amount_native": 0.0, "open_amount_native": 0.0,
        "time_in_stage_sum": 0.0, "time_in_stage_n": 0,
        "native_currencies": set(),
    })

    # HubSpot Search is capped at 10,000 results per query. Walk 7-day windows.
    # pages counter resets per window so long backfills never exhaust the cap.
    total_fetched = 0
    window = timedelta(days=7)
    win_start = start
    end_dt = end + timedelta(days=1)  # inclusive today

    while win_start < end_dt:
        win_end = min(win_start + window, end_dt)
        w_since = int(datetime(win_start.year, win_start.month, win_start.day).timestamp() * 1000)
        w_until = int(datetime(win_end.year, win_end.month, win_end.day).timestamp() * 1000)
        after = None
        win_count = 0
        pages = 0  # reset per window
        while True:
            try:
                data = _search_deals(w_since, until_ms=w_until, after=after)
            except Exception as e:
                print(f"[deals] search error: {e}")
                break
            for row in data.get("results", []):
                p = row.get("properties", {})
                created = (p.get("createdate") or "")[:10]
                if not created:
                    continue
                plabel, slabel, status = _classify_stage(p.get("dealstage"))
                amount_native = _to_float(p.get("amount"))
                native_cur = normalize_currency(
                    p.get("deal_currency_code") or DEFAULT_DEAL_CURRENCY
                )
                amount = to_usd(amount_native, native_cur)
                tis = _to_float(p.get("hs_v2_time_in_current_stage"))

                # Same fallback chain as the leads collector.
                from analysers.channel_inference import (
                    resolve_channel, CHANNEL_TO_QOYOD_SOURCE,
                )
                explicit_src = (p.get("deal_qoyod_source") or "").strip()
                inferred_slug = resolve_channel(
                    qoyod_source=explicit_src,
                    lead_utm_source=p.get("deal_utm_source") or "",
                    lead_utm_campaign=p.get("deal_utm_campaign") or "",
                    lead_original_traffic_source=p.get("deal_original_traffic_source") or "",
                    lead_latest_traffic_source=p.get("deal_latest_traffic_source") or "",
                    lead_original_traffic_source_drilldown_1=
                        p.get("deal_original_traffic_source_drilldown_1") or "",
                    lead_latest_traffic_source_drilldown_1=
                        p.get("deal_latest_traffic_source_drilldown_1") or "",
                    lead_original_traffic_source_drilldown_2=
                        p.get("deal_original_traffic_source_drilldown_2") or "",
                    lead_latest_traffic_source_drilldown_2=
                        p.get("deal_latest_traffic_source_drilldown_2") or "",
                    lead_utm_audience=p.get("deal_utm_audience") or "",
                    lead_utm_content=p.get("deal_utm_content") or "",
                    lead_utm_medium=p.get("deal_utm_medium") or "",
                )
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
                    status,
                    (p.get("deal_utm_campaign") or "").strip() or "__none__",
                    (p.get("deal_utm_audience") or "").strip() or None,
                    (p.get("deal_utm_content") or "").strip() or None,
                    (p.get("deal_utm_source") or "").strip() or None,
                    (p.get("deal_utm_medium") or "").strip() or None,
                    (p.get("deal_utm_term") or "").strip() or None,
                )
                b = buckets[key]
                b["n"] += 1
                b["amount"] += amount
                b["amount_native"] += amount_native
                b["native_currencies"].add(native_cur)
                if status == "won":
                    b["won"] += 1
                    b["won_amount"] += amount
                    b["won_amount_native"] += amount_native
                elif status == "lost":
                    b["lost"] += 1
                    b["lost_amount"] += amount
                    b["lost_amount_native"] += amount_native
                else:
                    b["open"] += 1
                    b["open_amount"] += amount
                    b["open_amount_native"] += amount_native
                if tis:
                    b["time_in_stage_sum"] += tis
                    b["time_in_stage_n"] += 1
                total_fetched += 1
                win_count += 1

            pages += 1
            paging = data.get("paging", {}).get("next", {})
            after = paging.get("after")
            if not after or pages >= 100:   # 100 pages × 100 rows = 10k cap per window
                break
        print(f"[deals] {win_start}..{win_end}: {win_count} deals")
        win_start = win_end

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for key, b in buckets.items():
        (d, src, pipeline, status,
         utm_c, utm_a, utm_co, utm_s, utm_m, utm_t) = key
        avg_time = (b["time_in_stage_sum"] / b["time_in_stage_n"]
                    if b["time_in_stage_n"] else None)
        # If a bucket contains multiple native currencies (e.g. SAR + USD mixed),
        # collapse to "MIXED" so downstream readers don't treat the native sum as
        # a single-currency value.
        currencies = b["native_currencies"]
        native_label = next(iter(currencies)) if len(currencies) == 1 else "MIXED"
        rows.append({
            "date": d,
            "qoyod_source": src,
            "pipeline": pipeline,
            "stage_status": status,
            "deal_utm_campaign": utm_c or "__none__",
            "deal_utm_audience": utm_a,
            "deal_utm_content": utm_co,
            "deal_utm_source": utm_s,
            "deal_utm_medium": utm_m,
            "deal_utm_term": utm_t,
            "deals_total": b["n"],
            "deals_won": b["won"],
            "deals_lost": b["lost"],
            "deals_open": b["open"],
            # USD (primary — use these in all reports)
            "amount_total": round(b["amount"], 2),
            "amount_won": round(b["won_amount"], 2),
            "amount_lost": round(b["lost_amount"], 2),
            "amount_open": round(b["open_amount"], 2),
            "currency": "USD",
            # Native (audit only)
            "amount_total_native": round(b["amount_native"], 2),
            "amount_won_native": round(b["won_amount_native"], 2),
            "amount_lost_native": round(b["lost_amount_native"], 2),
            "amount_open_native": round(b["open_amount_native"], 2),
            "currency_native": native_label,
            "avg_time_in_current_stage_ms": avg_time,
            "updated_at": now,
        })

    print(f"[deals] Processed {total_fetched} deals -> {len(rows)} daily buckets")
    _ensure_table_exists()
    return upsert_rows("hubspot_deals_daily", rows,
                       key_fields=["date", "qoyod_source", "pipeline",
                                   "stage_status", "deal_utm_campaign"])


def _ensure_table_exists():
    from google.cloud import bigquery
    client = get_client()
    table_id = f"{os.getenv('BQ_PROJECT_ID')}.{os.getenv('BQ_DATASET')}.hubspot_deals_daily"
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("qoyod_source", "STRING"),
        bigquery.SchemaField("pipeline", "STRING"),
        bigquery.SchemaField("stage_status", "STRING"),  # won | lost | open | unknown
        bigquery.SchemaField("deal_utm_campaign", "STRING"),
        bigquery.SchemaField("deal_utm_audience", "STRING"),
        bigquery.SchemaField("deal_utm_content", "STRING"),
        bigquery.SchemaField("deal_utm_source", "STRING"),
        bigquery.SchemaField("deal_utm_medium", "STRING"),
        bigquery.SchemaField("deal_utm_term", "STRING"),
        bigquery.SchemaField("deals_total", "INT64"),
        bigquery.SchemaField("deals_won", "INT64"),
        bigquery.SchemaField("deals_lost", "INT64"),
        bigquery.SchemaField("deals_open", "INT64"),
        bigquery.SchemaField("amount_total", "FLOAT64"),
        bigquery.SchemaField("amount_won", "FLOAT64"),
        bigquery.SchemaField("amount_lost", "FLOAT64"),
        bigquery.SchemaField("amount_open", "FLOAT64"),
        bigquery.SchemaField("currency", "STRING"),
        bigquery.SchemaField("amount_total_native", "FLOAT64"),
        bigquery.SchemaField("amount_won_native", "FLOAT64"),
        bigquery.SchemaField("amount_lost_native", "FLOAT64"),
        bigquery.SchemaField("amount_open_native", "FLOAT64"),
        bigquery.SchemaField("currency_native", "STRING"),
        bigquery.SchemaField("avg_time_in_current_stage_ms", "FLOAT64"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="date")
    table.clustering_fields = ["qoyod_source", "pipeline", "stage_status"]
    client.create_table(table, exists_ok=True)

    # Patch schema on existing table: add any columns missing from the live
    # table (e.g. after we added USD `currency` + `*_native` fields).
    existing   = client.get_table(table_id)
    have       = {f.name for f in existing.schema}
    new_fields = [f for f in schema if f.name not in have]
    if new_fields:
        existing.schema = list(existing.schema) + new_fields
        client.update_table(existing, ["schema"])
        print(f"[deals] Added {len(new_fields)} new columns to "
              f"hubspot_deals_daily: {[f.name for f in new_fields]}")


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"HubSpot Deals backfill complete: {n} rows")
