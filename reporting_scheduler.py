"""
6-hour reporting refresh scheduler.

ONLY refreshes the BigQuery reporting layer that backs the dashboard.
Runs every 6h (00:00, 06:00, 12:00, 18:00 UTC = 03:00, 09:00, 15:00, 21:00 Riyadh).

NOTE: This is separate from the operational agent loop (Slack approvals,
threshold watchers, optimization decisions) which run always-on.

All collectors run in incremental mode (last 2 days lookback). A full YTD
backfill can be forced via `python reporting_scheduler.py backfill`.
"""
import sys
import time
import traceback
from datetime import datetime, timezone

from collectors import google_ads_bq, meta_bq, snap_bq
from collectors import meta_organic_bq, youtube_bq, linkedin_bq
from collectors import hubspot_leads_bq, hubspot_deals_bq
from collectors import tiktok_bq, microsoft_ads_bq
from collectors import windsor_bq
from collectors.views import refresh_all_views
from notifications.notify import send_heartbeat
from logs.logger import get_logger, setup_global_logging
from logs.activity_logger import log_activity_async

setup_global_logging("bq-refresh")  # captures every print() into logs/
log = get_logger("bq-refresh")


COLLECTORS = [
    # ── Windsor.ai managed pipeline (Google, Meta, Snap, TikTok, LinkedIn, Bing)
    # Windsor runs FIRST — it's the single source for all channels it covers.
    # Direct collectors below serve as fallback if Windsor key is missing.
    ("windsor",         windsor_bq.collect_and_write),

    # ── Campaign-level direct collectors ──────────────────────────────────────
    ("google_ads",      google_ads_bq.collect_and_write),
    ("meta",            meta_bq.collect_and_write),
    ("snapchat",        snap_bq.collect_and_write),
    ("tiktok",          tiktok_bq.collect_and_write),
    ("microsoft_ads",   microsoft_ads_bq.collect_and_write),
    # Organic
    ("meta_organic",    meta_organic_bq.collect_and_write),
    ("youtube",         youtube_bq.collect_and_write),
    ("linkedin",        linkedin_bq.collect_and_write),
    # CRM
    ("hubspot_leads",   hubspot_leads_bq.collect_and_write),
    ("hubspot_deals",   hubspot_deals_bq.collect_and_write),

    # ── Sub-campaign collectors (adset / ad / keyword grain) ──────────────────
    # These use the same API credentials — no new infrastructure needed.
    ("google_ads_adgroups",  google_ads_bq.collect_adgroups_and_write),
    ("google_ads_keywords",  google_ads_bq.collect_keywords_and_write),
    ("google_ads_ads",       google_ads_bq.collect_ads_and_write),
    ("meta_adsets",          meta_bq.collect_adsets_and_write),
    ("meta_ads",             meta_bq.collect_ads_and_write),
    ("tiktok_adgroups",      tiktok_bq.collect_adgroups_and_write),
    ("tiktok_ads",           tiktok_bq.collect_ads_and_write),
    ("snapchat_adsets",      snap_bq.collect_adsets_and_write),
    ("linkedin_adsets",      linkedin_bq.collect_adsets_and_write),
    ("microsoft_ads_adgroups", microsoft_ads_bq.collect_adsets_and_write),
    ("microsoft_ads_keywords", microsoft_ads_bq.collect_keywords_and_write),
]


def run_refresh(incremental: bool = True, days: int | None = None):
    """One pass: run all collectors, then refresh all views.

    Args:
        incremental: True = last 2 days only (fast). False = full historical.
        days:        If set, overrides incremental — pulls last N days for each
                     collector that supports it. e.g. days=30 -> 30-day backfill.
    """
    started = datetime.now(timezone.utc)
    mode = "backfill" if days else ("incremental" if incremental else "full")
    print(f"\n{'='*60}\n[scheduler] Refresh start @ {started.isoformat()}"
          f"  (mode={mode}{f' days={days}' if days else ''})\n{'='*60}")

    results = {}
    for name, fn in COLLECTORS:
        t0 = time.time()
        try:
            if days is not None:
                n = fn(days=days)
            else:
                n = fn(incremental=incremental)
            dt = time.time() - t0
            results[name] = (True, n, dt)
            log.info(f"{name}: {n} rows in {dt:.1f}s")
            log_activity_async(
                role="bq_refresh", action=f"collect_{name}", status="success",
                channel=name, rows_affected=n, duration_s=dt,
                details={"mode": mode},
            )
        except Exception as e:
            dt = time.time() - t0
            results[name] = (False, str(e), dt)
            log.error(f"{name} FAILED after {dt:.1f}s: {e}")
            traceback.print_exc()
            log_activity_async(
                role="bq_refresh", action=f"collect_{name}", status="failed",
                channel=name, duration_s=dt, details={"error": str(e), "mode": mode},
            )

    try:
        refresh_all_views()
        results["views"] = (True, "ok", 0)
        log_activity_async(role="bq_refresh", action="refresh_views", status="success")
    except Exception as e:
        results["views"] = (False, str(e), 0)
        print(f"[scheduler] view refresh FAILED: {e}")
        log_activity_async(role="bq_refresh", action="refresh_views",
                           status="failed", details={"error": str(e)})

    ended = datetime.now(timezone.utc)
    elapsed = (ended - started).total_seconds()
    print(f"\n[scheduler] Done in {elapsed:.0f}s")
    for name, (ok, val, dt) in results.items():
        flag = "OK " if ok else "ERR"
        print(f"  [{flag}] {name}: {val}")

    # Heartbeat: one-line beacon so the team notices if the refresh stops.
    ok_items  = [n for n, (o, _, _) in results.items() if o]
    bad_items = [n for n, (o, _, _) in results.items() if not o]
    total_rows = sum(v for _, (o, v, _) in results.items()
                     if o and isinstance(v, int))
    status = "ok" if not bad_items else "failed"
    detail = (f"{total_rows:,} rows across {len(ok_items)} collectors"
              + (f" | FAILED: {', '.join(bad_items)}" if bad_items else ""))
    try:
        send_heartbeat("bq-refresh", status=status,
                       detail=detail, duration_s=elapsed)
    except Exception as e:
        log.warning(f"heartbeat emit failed: {e}")

    log_activity_async(
        role="bq_refresh", action="refresh_complete", status=status,
        rows_affected=total_rows, duration_s=elapsed,
        details={"mode": mode, "collectors_ok": ok_items,
                 "collectors_failed": bad_items, "total_rows": total_rows},
    )

    return results


def run_loop():
    """Run every 24h forever. Exits on Ctrl+C."""
    interval = 24 * 60 * 60
    while True:
        try:
            run_refresh(incremental=True)
        except Exception as e:
            print(f"[scheduler] loop error: {e}")
            traceback.print_exc()
        print(f"[scheduler] sleeping {interval}s until next run...")
        time.sleep(interval)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if cmd == "once":
        run_refresh(incremental=True)
    elif cmd == "backfill":
        run_refresh(incremental=False)
    elif cmd == "loop":
        run_loop()
    else:
        print("Usage: python reporting_scheduler.py [once|backfill|loop]")
