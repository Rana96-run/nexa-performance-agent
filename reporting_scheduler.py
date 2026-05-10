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
from datetime import datetime, timezone, timedelta, date

from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY
from collectors import google_ads_bq, meta_bq, snap_bq
from collectors import meta_organic_bq, youtube_bq, linkedin_bq
from collectors import hubspot_leads_bq, hubspot_deals_bq
from collectors import tiktok_bq, microsoft_ads_bq
from collectors.views import refresh_all_views
from collectors.hex_refresh import refresh_all as refresh_hex
from logs.logger import get_logger, setup_global_logging
from logs.activity_logger import log_activity_async

setup_global_logging("bq-refresh")  # captures every print() into logs/
log = get_logger("bq-refresh")


# ── Paid-channel guardrails ──────────────────────────────────────────────────
# Collectors that MUST write ≥1 row every incremental pass when credentials
# are present.  A zero-row result is a silent failure (API bug, auth expiry,
# bad date window) — treat it as an error and force a Slack alert.
ZERO_ROW_WARN: set[str] = {
    "google_ads", "meta", "snapchat", "tiktok",
}

# BQ channels to monitor for staleness (MAX date > 3 days old = alert)
_STALENESS_CHANNELS = ("google_ads", "meta", "snapchat", "tiktok")
_STALENESS_WARN_DAYS = 3


def _check_bq_staleness() -> list[str]:
    """
    Query MAX(date) per paid channel in campaigns_daily.
    Returns list of warning strings for channels whose latest date is
    more than _STALENESS_WARN_DAYS days behind today.
    """
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        client = get_client()
        threshold = (date.today() - timedelta(days=_STALENESS_WARN_DAYS)).isoformat()
        channels_str = ", ".join(f"'{c}'" for c in _STALENESS_CHANNELS)
        q = f"""
        SELECT channel, MAX(date) AS latest_date
        FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
        WHERE channel IN ({channels_str})
        GROUP BY channel
        """
        stale = []
        found = {row.channel: str(row.latest_date) for row in client.query(q).result()}
        # Also catch channels that have NO rows at all
        for ch in _STALENESS_CHANNELS:
            ld = found.get(ch)
            if ld is None:
                stale.append(f"`{ch}` — no data in BQ at all")
            elif ld < threshold:
                stale.append(f"`{ch}` — last data: {ld}")
        return stale
    except Exception as e:
        log.warning(f"staleness check failed (non-fatal): {e}")
        return []


COLLECTORS = [
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
    ("snapchat_ads",         snap_bq.collect_ads_and_write),
    ("linkedin_adsets",      linkedin_bq.collect_adsets_and_write),
    ("microsoft_ads_adgroups", microsoft_ads_bq.collect_adsets_and_write),
    ("microsoft_ads_keywords", microsoft_ads_bq.collect_keywords_and_write),
    ("microsoft_ads_ads",      microsoft_ads_bq.collect_ads_and_write),
    ("google_ads_pmax_assets", google_ads_bq.collect_pmax_asset_groups_and_write),
]


def _post_refresh_digest(results: dict, elapsed: float, utc_hour: int,
                          stale_warnings: list[str] | None = None) -> None:
    """Post a short Slack digest after a BQ refresh pass.

    Fires when ANY of the following is true:
      - there are hard failures (exception from a collector)
      - a paid-channel collector wrote 0 rows (silent API/auth failure)
      - BQ staleness check found a channel whose data is >3 days old
      - it is the first run of the day (06:00 UTC pass)

    Args:
        results:        dict of name -> (ok: bool, val, dt) from run_refresh().
        elapsed:        total wall-clock seconds for the full refresh.
        utc_hour:       UTC hour at which the refresh started (0-23).
        stale_warnings: list of human-readable staleness warnings from
                        _check_bq_staleness(), or None/[] if all clean.
    """
    stale_warnings = stale_warnings or []

    ok_items   = [n for n, (o, _, _) in results.items() if o]
    bad_items  = [n for n, (o, _, _) in results.items() if not o]
    has_errors = bool(bad_items)
    is_morning = (utc_hour == 6)

    # Zero-row warnings: paid channels that succeeded but wrote nothing
    zero_row_items = [
        n for n in ZERO_ROW_WARN
        if n in results and results[n][0] and isinstance(results[n][1], int)
        and results[n][1] == 0
    ]
    has_zero_row  = bool(zero_row_items)
    has_stale     = bool(stale_warnings)

    if not has_errors and not has_zero_row and not has_stale and not is_morning:
        return  # silent pass — nothing to report

    try:
        from slack_sdk import WebClient
        client = WebClient(token=SLACK_BOT_TOKEN)

        total_rows = sum(v for _, (o, v, _) in results.items()
                         if o and isinstance(v, int))

        # Build per-collector status lines (flag zero-row paid collectors)
        lines = []
        for name, (ok, val, _) in results.items():
            if not ok:
                icon = ":x:"
            elif name in ZERO_ROW_WARN and isinstance(val, int) and val == 0:
                icon = ":warning:"  # succeeded but wrote nothing
            else:
                icon = ":white_check_mark:"
            suffix = f"  ({val:,} rows)" if ok and isinstance(val, int) else (f"  `{val}`" if not ok else "")
            lines.append(f"{icon} `{name}`{suffix}")

        status_block = "\n".join(lines)
        summary = f"{total_rows:,} rows across {len(ok_items)} collectors in {elapsed:.0f}s"

        # Determine header and alert sections
        alert_parts = []
        if has_errors:
            alert_parts.append(f":x: *{len(bad_items)} collector(s) threw exceptions:* "
                                + ", ".join(f"`{n}`" for n in bad_items))
        if has_zero_row:
            alert_parts.append(f":warning: *Paid channels wrote 0 rows (silent failure):* "
                                + ", ".join(f"`{n}`" for n in zero_row_items))
        if has_stale:
            alert_parts.append(":clock3: *Stale BQ data detected:*\n"
                                + "\n".join(f"  • {w}" for w in stale_warnings))

        is_alert = has_errors or has_zero_row or has_stale
        if is_alert:
            header = ":rotating_light: *BQ Refresh — action required*"
        else:
            header = ":large_green_circle: *BQ Refresh — daily 06:00 UTC pass*"

        alert_section = ("\n\n" + "\n".join(alert_parts)) if alert_parts else ""

        text = (
            f"{header}\n"
            f"{summary}"
            f"{alert_section}\n\n"
            f"{status_block}"
        )

        client.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=text)
        log.info(f"refresh digest posted to {SLACK_CHANNEL_NOTIFY}"
                 + (" [ALERT]" if is_alert else ""))

    except Exception as e:
        log.warning(f"_post_refresh_digest failed (non-fatal): {e}")


def run_refresh(incremental: bool = True, days: int | None = None):
    """One pass: run all collectors, then refresh all views.

    Args:
        incremental: True = last 2 days only (fast). False = full historical.
        days:        If set, overrides incremental — pulls last N days for each
                     collector that supports it. e.g. days=30 -> 30-day backfill.
    """
    started = datetime.now(timezone.utc)
    utc_hour = started.hour
    mode = "backfill" if days else ("incremental" if incremental else "full")
    print(f"\n{'='*60}\n[scheduler] Refresh start @ {started.isoformat()}"
          f"  (mode={mode}{f' days={days}' if days else ''})\n{'='*60}")

    # Import here so a missing dep in cost_tracking can never block the refresh
    try:
        from executors.cost_tracking import track_api_calls, track_bq_bytes
    except Exception:
        track_api_calls = None
        track_bq_bytes  = None
    from contextlib import nullcontext

    results = {}
    for name, fn in COLLECTORS:
        t0 = time.time()
        # Count outbound HTTP calls + BQ bytes scanned this collector consumes.
        api_tracker = track_api_calls() if track_api_calls else nullcontext({"count": None})
        bq_tracker  = track_bq_bytes()  if track_bq_bytes  else nullcontext({"bytes": None})
        try:
            with api_tracker as api_counter, bq_tracker as bq_counter:
                if days is not None:
                    n = fn(days=days)
                else:
                    n = fn(incremental=incremental)
            dt = time.time() - t0
            results[name] = (True, n, dt)
            api_calls   = api_counter.get("count") if isinstance(api_counter, dict) else None
            bq_bytes    = bq_counter.get("bytes")  if isinstance(bq_counter,  dict) else None
            log.info(f"{name}: {n} rows in {dt:.1f}s ({api_calls} api calls, "
                     f"{(bq_bytes or 0)/1e6:.1f} MB BQ scan)")
            log_activity_async(
                role="bq_refresh", action=f"collect_{name}", status="success",
                channel=name, rows_affected=n, duration_s=dt,
                api_calls=api_calls,
                bq_bytes_scanned=bq_bytes,
                details={"mode": mode},
            )
        except Exception as e:
            dt = time.time() - t0
            results[name] = (False, str(e), dt)
            log.error(f"{name} FAILED after {dt:.1f}s: {e}")
            traceback.print_exc()
            api_calls = api_counter.get("count") if isinstance(api_counter, dict) else None
            bq_bytes  = bq_counter.get("bytes")  if isinstance(bq_counter,  dict) else None
            log_activity_async(
                role="bq_refresh", action=f"collect_{name}", status="failed",
                channel=name, duration_s=dt,
                api_calls=api_calls,
                bq_bytes_scanned=bq_bytes,
                details={"error": str(e), "mode": mode},
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

    # ── Silent auto-heal: future partitions, zero-row channels, etc. ────────
    # Runs every refresh pass. Fixes are logged silently; weekly summary
    # surfaces a one-line "🔧 Auto-healed: N" block. We don't alert.
    try:
        from analysers.data_quality import auto_heal
        heal_counts = auto_heal()
        results["data_quality"] = (True, heal_counts, 0)
    except Exception as e:
        print(f"[scheduler] auto-heal failed (non-fatal): {e}")

    # ── Sync Asana task completion status to BQ ──────────────────────────────
    try:
        from collectors.asana_sync import run_full_sync
        n_synced = run_full_sync()
        results["asana_sync"] = (True, n_synced, 0)
    except Exception as e:
        print(f"[scheduler] asana_sync failed (non-fatal): {e}")
        results["asana_sync"] = (False, str(e), 0)

    # ── Trigger Hex notebook re-runs so dashboards reflect fresh BQ data ─────
    try:
        hex_results = refresh_hex(wait=False)   # fire-and-forget; Hex queues the run
        if hex_results:
            ok_hex  = [n for n, v in hex_results.items() if v]
            bad_hex = [n for n, v in hex_results.items() if not v]
            status_hex = "success" if not bad_hex else "failed"
            log_activity_async(
                role="bq_refresh", action="refresh_hex_notebooks",
                status=status_hex,
                details={"triggered": ok_hex, "failed": bad_hex},
            )
    except Exception as e:
        print(f"[scheduler] Hex refresh failed (non-fatal): {e}")

    ended = datetime.now(timezone.utc)
    elapsed = (ended - started).total_seconds()
    print(f"\n[scheduler] Done in {elapsed:.0f}s")
    for name, (ok, val, dt) in results.items():
        flag = "OK " if ok else "ERR"
        print(f"  [{flag}] {name}: {val}")

    ok_items  = [n for n, (o, _, _) in results.items() if o]
    bad_items = [n for n, (o, _, _) in results.items() if not o]
    total_rows = sum(v for _, (o, v, _) in results.items()
                     if o and isinstance(v, int))
    status = "ok" if not bad_items else "failed"

    log_activity_async(
        role="bq_refresh", action="refresh_complete", status=status,
        rows_affected=total_rows, duration_s=elapsed,
        details={"mode": mode, "collectors_ok": ok_items,
                 "collectors_failed": bad_items, "total_rows": total_rows},
    )

    # Slack notifications for BQ refresh are intentionally disabled.
    # All results are logged to BQ activity log only.

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
