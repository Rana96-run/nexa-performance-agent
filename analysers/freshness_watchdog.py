"""Freshness watchdog — never let BQ go stale.

Runs every 4h independent of the main scheduler. Checks each critical source
table on two dimensions:

  1. MAX(date) lag: is the most recent partition more than 1 day behind today?
  2. Re-attribution lag: when was today's (or yesterday's) partition LAST
     touched? HubSpot workflows re-classify leads after creation; if we
     haven't pulled in >24h, we miss the re-attributions.

If either condition trips, the watchdog triggers a targeted re-sync of the
specific collector(s) that are stale. Posts a one-line ping to #nexa-health
when it fires — so a human knows the catch-up happened.

Defense-in-depth: this catches the case where the scheduled 05:00/17:00 runs
were missed (Railway redeploy, scheduler crash, gate-blocked failure).
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from collectors.bq_writer import get_client
from notifications.slack_ping import post_ping

HEALTH_CHANNEL = os.getenv("SLACK_CHANNEL_HEALTH", "#nexa-health")
ACTIVITY_URL = (
    os.getenv("ACTIVITY_SHORT_URL")
    or "https://nexa-web-production-6a6b.up.railway.app/activity"
)

# Each entry: (table, date_field, collector_module, collector_fn, fn_kwargs)
# 'collector_fn' is called with **fn_kwargs to trigger a re-sync.
WATCHED_TABLES = [
    ("campaigns_daily",            "date", "collectors.google_ads_bq",     "collect_and_write",    {"days": 3}),
    ("campaigns_daily",            "date", "collectors.meta_bq",           "collect_and_write",    {"days": 3}),
    ("campaigns_daily",            "date", "collectors.microsoft_ads_bq",  "collect_and_write",    {"days": 3}),
    ("campaigns_daily",            "date", "collectors.snap_bq",           "collect_and_write",    {"days": 3}),
    ("campaigns_daily",            "date", "collectors.tiktok_bq",         "collect_and_write",    {"days": 3}),
    ("hubspot_leads_module_daily", "date", "collectors.hubspot_leads_bq",  "sync_full_mirror",     {}),
    ("hubspot_deals_daily",        "date", "collectors.hubspot_deals_bq",  "collect_and_write",    {"days": 10}),
]

# Two thresholds — re-sync if EITHER trips
MAX_LAG_DAYS         = 1     # MAX(date) must be within today-1 (yesterday)
MAX_UPDATE_AGE_HOURS = 25    # most recent partition must have been written < 25h ago


def _check_all() -> list[dict]:
    """Return list of stale table/collector combos that need re-sync."""
    c = get_client()
    proj = os.environ["BQ_PROJECT_ID"]
    ds   = os.environ["BQ_DATASET"]
    now = datetime.now(timezone.utc)

    # Group by table — query each table once, decide per collector
    table_state = {}
    seen = set()
    for tbl, dfield, _, _, _ in WATCHED_TABLES:
        if tbl in seen: continue
        seen.add(tbl)
        sql = f"""
        SELECT
          DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX({dfield}), DAY) AS lag_days,
          TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(updated_at), HOUR) AS update_age_h,
          MAX({dfield}) AS last_date,
          MAX(updated_at) AS last_write
        FROM `{proj}.{ds}.{tbl}`
        WHERE {dfield} >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
        """
        r = list(c.query(sql).result())[0]
        # NB: do NOT use `or` defaults — 0 hours is falsy but valid (table just
        # written). Use explicit None checks.
        lag_days = r.lag_days if r.lag_days is not None else 999
        age_h    = r.update_age_h if r.update_age_h is not None else 999
        table_state[tbl] = {
            "lag_days":      int(lag_days),
            "update_age_h":  int(age_h),
            "last_date":     r.last_date,
            "last_write":    r.last_write,
        }

    stale = []
    for tbl, dfield, mod, fn, kwargs in WATCHED_TABLES:
        s = table_state.get(tbl, {})
        why = []
        if s.get("lag_days", 999) > MAX_LAG_DAYS:
            why.append(f"date_lag={s['lag_days']}d")
        if s.get("update_age_h", 999) > MAX_UPDATE_AGE_HOURS:
            why.append(f"last_write={s['update_age_h']}h ago")
        if why:
            stale.append({
                "table": tbl, "collector": f"{mod}.{fn}", "kwargs": kwargs,
                "reason": " AND ".join(why),
                "last_date": str(s.get("last_date")),
                "last_write": str(s.get("last_write")),
            })
    return stale


def _trigger_resync(collector: str, kwargs: dict) -> tuple[bool, str]:
    """Import the collector module and run the named function. Returns (ok, msg)."""
    try:
        mod_name, fn_name = collector.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name)
        result = fn(**kwargs)
        return True, f"{result} rows"
    except Exception as e:
        return False, str(e)[:120]


def run_watchdog(post_slack: bool = True) -> dict:
    """Main entry point — called by the scheduler every 4h."""
    stale = _check_all()
    if not stale:
        print("[watchdog] All BQ tables fresh — no action")
        return {"stale_count": 0, "resyncs": []}

    print(f"[watchdog] {len(stale)} stale collector(s) — triggering re-sync")
    resyncs = []
    for item in stale:
        print(f"[watchdog]   {item['table']:30s} {item['reason']:30s} → {item['collector']}")
        ok, msg = _trigger_resync(item["collector"], item["kwargs"])
        resyncs.append({**item, "ok": ok, "msg": msg})
        print(f"[watchdog]     {'OK' if ok else 'FAIL'}: {msg}")

    if post_slack:
        failed = [r for r in resyncs if not r["ok"]]
        if failed:
            headline = (
                f"Watchdog tried to refresh {len(stale)} stale table(s), "
                f"{len(failed)} failed: {', '.join(f['table'] for f in failed)}"
            )
            try:
                post_ping(channel=HEALTH_CHANNEL, status="alert",
                          headline=headline, link=ACTIVITY_URL)
            except Exception as e:
                print(f"[watchdog] Slack ping failed: {e}")
    return {"stale_count": len(stale), "resyncs": resyncs}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, ".")
    from dotenv import load_dotenv; load_dotenv()
    r = run_watchdog(post_slack=False)
    print(f"\nWatchdog done: {r['stale_count']} stale, {sum(1 for x in r['resyncs'] if x['ok'])} ok")
