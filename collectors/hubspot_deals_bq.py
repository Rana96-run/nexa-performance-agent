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


def _to_riyadh_date(ts_iso: str) -> str:
    """Convert an ISO-8601 UTC timestamp (HubSpot's format) to a Riyadh
    (UTC+3) YYYY-MM-DD date string. Returns '' on parse failure.

    Why: HubSpot UI filters and Qoyod ops thinking are in Riyadh time.
    Storing BQ partitions in Riyadh date aligns BQ counts to what the user
    sees in HubSpot's "yesterday" / "this week" filters.
    """
    if not ts_iso:
        return ""
    try:
        ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return (ts + timedelta(hours=3)).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return ts_iso[:10]  # fallback to UTC truncation


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


def _classify_stage(stage_id, hs_is_closed_won=None, hs_is_closed=None):
    """Return (pipeline_label, stage_label, status) where status ∈ {won,lost,open,unknown}.

    Priority order for `status`:
      1. HubSpot's `hs_is_closed_won` flag (authoritative — set by HubSpot whenever
         the deal sits in a stage marked Closed Won in pipeline settings).
      2. HubSpot's `hs_is_closed` flag combined with stage label/probability for
         distinguishing closed-lost from closed-won.
      3. Stage label substring match ("won" / "lost") — fallback for older deals
         where the hs_is_closed_* flags weren't set.
      4. Stage probability (1.0 = won, 0.0 = lost, between = open).
    """
    if not stage_id:
        return None, None, "unknown"
    info = _CACHE["stages"].get(stage_id)
    if not info:
        return None, None, "unknown"
    _pid, plabel, slabel, prob = info

    # 1. Authoritative HubSpot flag — only count revenue when HS itself says won.
    if (str(hs_is_closed_won or "").lower() == "true"):
        return plabel, slabel, "won"

    sl = (slabel or "").lower()
    closed = str(hs_is_closed or "").lower() == "true"

    # 2. If HS says closed but NOT closed_won, treat as lost (regardless of label).
    if closed:
        return plabel, slabel, "lost"

    # 3. Stage-label fallback for legacy deals with missing flags.
    if "won" in sl:
        status = "won"
    elif "lost" in sl or "closed lost" in sl:
        status = "lost"
    # 4. Probability fallback.
    elif prob == 1.0:
        status = "won"
    elif prob == 0.0:
        status = "lost"
    elif prob is not None:
        status = "open"
    else:
        status = "open"
    return plabel, slabel, status


def _search_deals(since_ms, until_ms=None, after=None, date_field="createdate"):
    """Search deals by createdate (default) or closedate.

    Using closedate in incremental mode catches deals created months ago
    that recently closed — these are missed by createdate-only searches
    because their createdate falls outside the short lookback window.
    """
    filters = [{"propertyName": date_field, "operator": "GTE", "value": str(since_ms)}]
    if until_ms is not None:
        filters.append({"propertyName": date_field, "operator": "LT", "value": str(until_ms)})
    body = {
        "filterGroups": [{"filters": filters}],
        "properties": PROPERTIES,
        "limit": 100,
        "sorts": [{"propertyName": date_field, "direction": "ASCENDING"}],
    }
    if after:
        body["after"] = after
    r = requests.post(f"{BASE}/crm/v3/objects/deals/search",
                      headers={"Authorization": f"Bearer {TOKEN}",
                               "Content-Type": "application/json"},
                      json=body)
    if r.status_code >= 400:
        print(f"[deals] HTTP {r.status_code} on search ({date_field}):")
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
      - incremental=True: last 30 days by createdate + last 365 days by closedate.
        The closedate pass catches deals created at any point that recently closed
        (long sales cycles) — these are invisible to a createdate-only search.
      - days=N: last N days by createdate + same window by closedate
      - start_date=date(Y,M,D): custom window by createdate + same window by closedate
      - default: YTD (Jan 1 of current year) by createdate + same window by closedate

    In all modes, the closedate pass runs over the SAME date window as the
    createdate pass. This ensures any deal closed in the window is captured,
    regardless of when it was created — even deals created years ago.
    """
    _load_pipelines()
    print(f"[deals] Loaded {len(_CACHE['pipelines'])} pipelines, "
          f"{len(_CACHE['stages'])} stages")

    end = date.today()
    if incremental:
        # 30-day createdate window: catches new deals and recently-created ones.
        # The closedate pass below uses a wider 365-day window so long-cycle
        # deals (created >1 year ago) are still found when they close.
        start = end - timedelta(days=30)
        closedate_start = end - timedelta(days=365)
    elif start_date:
        start = start_date
        closedate_start = start_date   # same window — any deal closed in range
    elif days:
        start = end - timedelta(days=days)
        closedate_start = start
    else:
        start = date(end.year, 1, 1)   # YTD default
        closedate_start = start
    print(f"[deals] Window: {start} -> {end}")
    since_ms = int(datetime(start.year, start.month, start.day).timestamp() * 1000)

    # bucket by (date, channel, pipeline, stage_status, utm_*)
    # date = createdate for ALL deals (won/open/lost).
    # Revenue is attributed to when the deal was created — aligns with the spend
    # date so ROAS reflects "deals sourced by this spend", not "deals that closed
    # this period". Closedate pass still searches by closedate to FIND newly-won
    # deals, but writes them to their createdate partition.
    # Amounts are accumulated twice: once in USD (primary), once in native currency.
    buckets = defaultdict(lambda: {
        "n": 0, "won": 0, "lost": 0, "open": 0,
        "amount": 0.0, "won_amount": 0.0, "lost_amount": 0.0, "open_amount": 0.0,
        "amount_native": 0.0, "won_amount_native": 0.0,
        "lost_amount_native": 0.0, "open_amount_native": 0.0,
        "time_in_stage_sum": 0.0, "time_in_stage_n": 0,
        "native_currencies": set(),
    })

    # Track deal IDs processed in the createdate pass so the closedate pass
    # (incremental only) can skip duplicates and avoid double-counting.
    seen_ids: set = set()

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
                deal_id = row.get("id")
                if deal_id in seen_ids:
                    continue
                if deal_id:
                    seen_ids.add(deal_id)
                p = row.get("properties", {})
                created = _to_riyadh_date(p.get("createdate") or "")
                if not created:
                    continue
                closed = _to_riyadh_date(p.get("closedate") or "") or None
                plabel, slabel, status = _classify_stage(
                    p.get("dealstage"),
                    hs_is_closed_won=p.get("hs_is_closed_won"),
                    hs_is_closed=p.get("hs_is_closed"),
                )
                amount_native = _to_float(p.get("amount"))
                native_cur = normalize_currency(
                    p.get("deal_currency_code") or DEFAULT_DEAL_CURRENCY
                )
                amount = to_usd(amount_native, native_cur)
                tis = _to_float(p.get("hs_v2_time_in_current_stage"))

                explicit_src = (p.get("deal_qoyod_source") or "").strip()
                # Explicit deal_qoyod_source only — no UTM inference.
                # Matches HubSpot's own "Deal Qoyod Source" filter exactly.
                # Deals without an explicit source fall to "Other" and are
                # excluded from paid-channel queries.
                src_label = explicit_src if (explicit_src and explicit_src != "Other") else "Other"

                # Won deals use closedate as the partition date so ROAS can be
                # filtered by when revenue was actually recognised, not when the
                # deal was created. Open/lost use createdate for pipeline reporting.
                #
                # Sanity guard: HubSpot users sometimes set closedate to a far-
                # future placeholder (e.g. 2026-12-31). That partitions revenue
                # months in the future and pollutes "won this week" queries.
                # If closedate > today OR closedate < createdate by more than
                # a year, fall back to createdate.
                from datetime import date as _date, datetime as _dt
                today_str = _date.today().isoformat()
                if status == "won" and closed:
                    if closed > today_str:
                        closed = created                # future date → use createdate
                    elif created and (closed < created):
                        closed = created                # closedate before createdate → use createdate
                partition_date = created  # always createdate — revenue attributed to deal origin
                key = (
                    partition_date,
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

    # ── Closedate pass (all modes) ───────────────────────────────────────────
    # Finds ANY won deal whose closedate falls in the window, regardless of
    # when the deal was created. This is the authoritative pass for revenue —
    # a deal created 2 years ago that closed today belongs in today's revenue.
    # Runs in ALL modes (incremental, days, start_date, YTD).
    # Deduplicates against seen_ids so deals already in the createdate pass
    # are not double-counted.
    if True:  # always run — replaces the old incremental-only guard
        cd_win_start = closedate_start
        cd_end_dt = end + timedelta(days=1)
        closedate_fetched = 0
        while cd_win_start < cd_end_dt:
            cd_win_end = min(cd_win_start + window, cd_end_dt)
            w_since = int(datetime(cd_win_start.year, cd_win_start.month,
                                   cd_win_start.day).timestamp() * 1000)
            w_until = int(datetime(cd_win_end.year, cd_win_end.month,
                                   cd_win_end.day).timestamp() * 1000)
            after = None
            pages = 0
            while True:
                try:
                    data = _search_deals(w_since, until_ms=w_until, after=after,
                                         date_field="closedate")
                except Exception as e:
                    print(f"[deals][closedate] search error: {e}")
                    break
                for row in data.get("results", []):
                    deal_id = row.get("id")
                    if deal_id in seen_ids:
                        continue          # already processed in createdate pass
                    if deal_id:
                        seen_ids.add(deal_id)
                    p = row.get("properties", {})
                    created = (p.get("createdate") or "")[:10]
                    if not created:
                        continue
                    closed = (p.get("closedate") or "")[:10] or None
                    plabel, slabel, status = _classify_stage(
                        p.get("dealstage"),
                        hs_is_closed_won=p.get("hs_is_closed_won"),
                        hs_is_closed=p.get("hs_is_closed"),
                    )
                    # Only care about won deals in the closedate pass —
                    # open/lost deals are correctly captured by createdate.
                    if status != "won":
                        continue
                    amount_native = _to_float(p.get("amount"))
                    native_cur = normalize_currency(
                        p.get("deal_currency_code") or DEFAULT_DEAL_CURRENCY
                    )
                    amount = to_usd(amount_native, native_cur)
                    tis = _to_float(p.get("hs_v2_time_in_current_stage"))
                    explicit_src = (p.get("deal_qoyod_source") or "").strip()
                    src_label = explicit_src if (explicit_src and explicit_src != "Other") else "Other"
                    from datetime import date as _date
                    today_str = _date.today().isoformat()
                    if closed and closed > today_str:
                        closed = created
                    elif created and closed and (closed < created):
                        closed = created
                    partition_date = created  # always createdate — revenue attributed to deal origin
                    key = (
                        partition_date, src_label, plabel or "Unknown", status,
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
                    b["won"] += 1
                    b["won_amount"] += amount
                    b["won_amount_native"] += amount_native
                    if tis:
                        b["time_in_stage_sum"] += tis
                        b["time_in_stage_n"] += 1
                    total_fetched += 1
                    closedate_fetched += 1
                pages += 1
                paging = data.get("paging", {}).get("next", {})
                after = paging.get("after")
                if not after or pages >= 100:
                    break
            cd_win_start = cd_win_end
        print(f"[deals][closedate] {closedate_fetched} additional won deals "
              f"captured via closedate pass (created before createdate window)")
    # ── end closedate pass ────────────────────────────────────────────────────

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
    import sys, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("days", nargs="?", type=int, default=None,
                        help="Number of days to look back (positional)")
    parser.add_argument("--start-date", type=lambda s: date.fromisoformat(s),
                        default=None, help="Explicit start date YYYY-MM-DD")
    args = parser.parse_args()
    n = collect_and_write(days=args.days, start_date=args.start_date)
    print(f"HubSpot Deals backfill complete: {n} rows")
