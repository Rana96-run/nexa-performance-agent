"""
Meta organic (Facebook Page + Instagram Business) -> BigQuery.
Writes to: organic_page_daily

Needs in .env:
  META_PAGE_ACCESS_TOKEN   long-lived page token
  META_FB_PAGE_ID
  META_IG_BUSINESS_ID
"""
import os
from datetime import date, datetime, timedelta, timezone
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows, get_client

load_dotenv()
GRAPH = f"https://graph.facebook.com/{os.getenv('META_GRAPH_VERSION', 'v22.0')}"
TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN")
FB_PAGE = os.getenv("META_FB_PAGE_ID")
IG_BIZ = os.getenv("META_IG_BUSINESS_ID")


def _get(path, params):
    params = dict(params, access_token=TOKEN)
    r = requests.get(f"{GRAPH}/{path}", params=params)
    if r.status_code >= 400:
        print(f"[meta_organic] {r.status_code} {path}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()


# Post-Nov-2025 deprecation survivors. Many classic metrics (page_impressions,
# page_fans, page_fan_adds) were removed.
FB_PAGE_METRICS = [
    "page_impressions_unique",     # daily reach
    "page_post_engagements",       # engagements
    "page_follows",                # lifetime follower count snapshot
    "page_daily_follows_unique",   # new followers that day (unique)
    "page_views_total",            # page profile views
]

# IG v21: `reach` is the only true daily time-series metric left.
# Others (profile_views, website_clicks, accounts_engaged, total_interactions)
# require metric_type=total_value (period aggregate, not daily) and are fetched
# as a period snapshot written to the end_date row.
IG_METRICS_DAY = ["reach"]
IG_METRICS_TOTAL = ["profile_views", "website_clicks",
                    "accounts_engaged", "total_interactions"]


def _fetch_fb_page_daily(start, end):
    data = _get(f"{FB_PAGE}/insights", {
        "metric": ",".join(FB_PAGE_METRICS),
        "since": str(start),
        "until": str(end + timedelta(days=1)),
        "period": "day",
    })
    # Flatten to {(date): {metric: value}}
    by_day = {}
    for m in data.get("data", []):
        name = m["name"]
        for v in m.get("values", []):
            d = v.get("end_time", "")[:10]
            if not d:
                continue
            by_day.setdefault(d, {})[name] = v.get("value") or 0
    return by_day


def _fetch_ig_daily(start, end):
    if not IG_BIZ:
        return {}
    since_ts = int(datetime(start.year, start.month, start.day).timestamp())
    until_ts = int(datetime(end.year, end.month, end.day).timestamp()) + 86400

    by_day = {}

    # 1. True daily time-series (reach)
    data = _get(f"{IG_BIZ}/insights", {
        "metric": ",".join(IG_METRICS_DAY),
        "since": since_ts,
        "until": until_ts,
        "period": "day",
    })
    for m in data.get("data", []):
        name = m["name"]
        for v in m.get("values", []):
            d = v.get("end_time", "")[:10]
            if not d:
                continue
            by_day.setdefault(d, {})[name] = v.get("value") or 0

    # 2. Total-value period aggregates (profile_views, website_clicks, etc.)
    #    Returned as a single number for the whole window. Attribute to the end date.
    try:
        data = _get(f"{IG_BIZ}/insights", {
            "metric": ",".join(IG_METRICS_TOTAL),
            "metric_type": "total_value",
            "since": since_ts,
            "until": until_ts,
            "period": "day",
        })
        end_d = str(end)
        for m in data.get("data", []):
            name = m["name"]
            val = m.get("total_value", {}).get("value")
            if val is None and m.get("values"):
                val = m["values"][0].get("value")
            by_day.setdefault(end_d, {})[name] = val or 0
    except Exception as e:
        print(f"[meta_organic] ig total_value fetch skipped: {e}")

    # 3. Lifetime snapshot: followers + media count — today only
    try:
        snap = _get(f"{IG_BIZ}", {"fields": "followers_count,media_count"})
        today = str(date.today())
        by_day.setdefault(today, {})["ig_followers"] = snap.get("followers_count", 0)
        by_day[today]["ig_media_count"] = snap.get("media_count", 0)
    except Exception:
        pass
    return by_day


def _date_chunks(start: date, end: date, max_days: int = 90):
    """Yield (chunk_start, chunk_end) tuples of up to max_days each."""
    cur = start
    while cur <= end:
        yield cur, min(cur + timedelta(days=max_days - 1), end)
        cur = cur + timedelta(days=max_days)


def collect_and_write(days: int = None, incremental: bool = False):
    if not TOKEN or not FB_PAGE:
        print("[meta_organic] missing META_PAGE_ACCESS_TOKEN or META_FB_PAGE_ID — skipping")
        return 0

    end = date.today()
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)
    print(f"[meta_organic] Window {start} -> {end}")

    # FB Page Insights: 93-day cap. IG Insights: 30-day cap.
    # Use 30-day chunks for both to satisfy the stricter IG limit.
    fb: dict = {}
    ig: dict = {}
    for cs, ce in _date_chunks(start, end, max_days=30):
        fb.update(_fetch_fb_page_daily(cs, ce))
        ig.update(_fetch_ig_daily(cs, ce))

    now = datetime.now(timezone.utc).isoformat()
    all_days = sorted(set(fb) | set(ig))
    rows = []
    for d in all_days:
        f = fb.get(d, {})
        i = ig.get(d, {})
        rows.append({
            "date": d,
            "channel": "meta_organic",
            "fb_impressions":     int(f.get("page_impressions_unique", 0) or 0),  # reach (total impressions deprecated)
            "fb_reach":           int(f.get("page_impressions_unique", 0) or 0),
            "fb_engagements":     int(f.get("page_post_engagements", 0) or 0),
            "fb_fans":            int(f.get("page_follows", 0) or 0),            # lifetime followers (page_fans deprecated)
            "fb_new_followers":   int(f.get("page_daily_follows_unique", 0) or 0),
            "fb_page_views":      int(f.get("page_views_total", 0) or 0),
            "ig_impressions":     int(i.get("impressions", 0) or 0),
            "ig_reach":           int(i.get("reach", 0) or 0),
            "ig_profile_views":   int(i.get("profile_views", 0) or 0),
            "ig_website_clicks":  int(i.get("website_clicks", 0) or 0),
            "ig_followers":       int(i.get("ig_followers", 0) or 0),
            "ig_media_count":     int(i.get("ig_media_count", 0) or 0),
            "updated_at": now,
        })

    _ensure_table()
    return upsert_rows("organic_page_daily", rows,
                       key_fields=["date", "channel"])


def _ensure_table():
    from google.cloud import bigquery
    client = get_client()
    table_id = f"{os.getenv('BQ_PROJECT_ID')}.{os.getenv('BQ_DATASET')}.organic_page_daily"
    schema = [
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("channel", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fb_impressions", "INT64"),
        bigquery.SchemaField("fb_reach", "INT64"),
        bigquery.SchemaField("fb_engagements", "INT64"),
        bigquery.SchemaField("fb_fans", "INT64"),
        bigquery.SchemaField("fb_new_followers", "INT64"),
        bigquery.SchemaField("fb_page_views", "INT64"),
        bigquery.SchemaField("ig_impressions", "INT64"),
        bigquery.SchemaField("ig_reach", "INT64"),
        bigquery.SchemaField("ig_profile_views", "INT64"),
        bigquery.SchemaField("ig_website_clicks", "INT64"),
        bigquery.SchemaField("ig_followers", "INT64"),
        bigquery.SchemaField("ig_media_count", "INT64"),
        bigquery.SchemaField("yt_subscribers", "INT64"),
        bigquery.SchemaField("yt_views", "INT64"),
        bigquery.SchemaField("yt_watch_time_min", "FLOAT64"),
        bigquery.SchemaField("li_followers", "INT64"),
        bigquery.SchemaField("li_impressions", "INT64"),
        bigquery.SchemaField("li_clicks", "INT64"),
        bigquery.SchemaField("li_engagement", "INT64"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="date")
    table.clustering_fields = ["channel"]
    client.create_table(table, exists_ok=True)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"Meta organic backfill complete: {n} rows")
