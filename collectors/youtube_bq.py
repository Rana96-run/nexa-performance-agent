"""
YouTube organic -> BigQuery.
Channel-level daily metrics via YouTube Analytics API (needs OAuth, not API key).

Writes:
  - Updates organic_page_daily with yt_subscribers / yt_views / yt_watch_time_min
  - Top videos snapshot -> organic_youtube_videos (created separately if desired)

Needs in .env:
  YT_CLIENT_ID
  YT_CLIENT_SECRET
  YT_REFRESH_TOKEN
  YT_CHANNEL_ID  (UC...)
"""
import os
from datetime import date, datetime, timedelta, timezone
import requests
from dotenv import load_dotenv
from collectors.bq_writer import upsert_rows

load_dotenv()
TOKEN_URL = "https://oauth2.googleapis.com/token"
YTA_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
YT_DATA = "https://www.googleapis.com/youtube/v3"


def _access_token():
    r = requests.post(TOKEN_URL, data={
        "client_id": os.getenv("YT_CLIENT_ID"),
        "client_secret": os.getenv("YT_CLIENT_SECRET"),
        "refresh_token": os.getenv("YT_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    })
    r.raise_for_status()
    return r.json()["access_token"]


def _daily_channel_report(token, start, end):
    r = requests.get(YTA_URL, params={
        "ids": f"channel=={os.getenv('YT_CHANNEL_ID')}",
        "startDate": str(start),
        "endDate": str(end),
        "metrics": "views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        "dimensions": "day",
    }, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        print(f"[yt] {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()


def _current_sub_count(token):
    r = requests.get(f"{YT_DATA}/channels", params={
        "part": "statistics",
        "id": os.getenv("YT_CHANNEL_ID"),
    }, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return 0
    return int(items[0].get("statistics", {}).get("subscriberCount", 0))


def collect_and_write(days: int = None, incremental: bool = False):
    if not os.getenv("YT_REFRESH_TOKEN") or not os.getenv("YT_CHANNEL_ID"):
        print("[yt] missing YT_REFRESH_TOKEN or YT_CHANNEL_ID — skipping")
        return 0

    token = _access_token()
    end = date.today()
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)
    print(f"[yt] Window {start} -> {end}")

    report = _daily_channel_report(token, start, end)
    sub_total = _current_sub_count(token)
    headers = [h["name"] for h in report.get("columnHeaders", [])]
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for row in report.get("rows", []):
        rec = dict(zip(headers, row))
        d = rec.get("day")
        views = int(rec.get("views", 0) or 0)
        mins = float(rec.get("estimatedMinutesWatched", 0) or 0)
        rows.append({
            "date": d,
            "channel": "youtube",
            "yt_views": views,
            "yt_watch_time_min": round(mins, 2),
            "yt_subscribers": sub_total,  # lifetime snapshot per row (fine for daily)
            "updated_at": now,
        })

    return upsert_rows("organic_page_daily", rows,
                       key_fields=["date", "channel"])


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    n = collect_and_write(days=days)
    print(f"YouTube backfill complete: {n} rows")
