"""
Operational scheduler — fires the performance agent at the right cadences.

All times in Riyadh (UTC+3). Heavy work at 8 AM so the team has fresh
tasks + summaries waiting at the start of the workday.

  08:00 Riyadh = 05:00 UTC  -> daily (always)
  Mon   08:00               -> + weekly analysis
  1st   08:00               -> + monthly analysis
  Jan/Apr/Jul/Oct 1st 08:00 -> + quarterly analysis
"""
import schedule
import time
import traceback
from datetime import date
from logs.logger import setup_global_logging

setup_global_logging("operational-scheduler")  # captures every print() into logs/
from main import run_cadence
from notifications.notify import send_heartbeat


def _run_with_heartbeat(cadence: str):
    """Run a cadence and emit a heartbeat on completion or failure.

    Wraps the cadence in track_bq_bytes() + track_api_calls() so all
    consumption (BQ scans, outbound HTTP) is attributed to this cadence
    run and surfaces in the consumption dashboard.
    """
    from contextlib import nullcontext
    try:
        from executors.cost_tracking import track_api_calls, track_bq_bytes
        from logs.activity_logger import log_activity_async
    except Exception:
        track_api_calls = track_bq_bytes = None
        log_activity_async = None

    api_tracker = track_api_calls() if track_api_calls else nullcontext({"count": None})
    bq_tracker  = track_bq_bytes()  if track_bq_bytes  else nullcontext({"bytes": None})

    t0 = time.time()
    try:
        with api_tracker as api_counter, bq_tracker as bq_counter:
            run_cadence(cadence)
        duration = time.time() - t0
        send_heartbeat(f"agent-{cadence}", status="ok",
                       detail=f"{cadence} cadence completed",
                       duration_s=duration)
        if log_activity_async:
            try:
                log_activity_async(
                    role="ops_scheduler",
                    action=f"cadence_{cadence}_complete",
                    status="success",
                    duration_s=duration,
                    api_calls=api_counter.get("count") if isinstance(api_counter, dict) else None,
                    bq_bytes_scanned=bq_counter.get("bytes") if isinstance(bq_counter, dict) else None,
                    details={"cadence": cadence},
                )
            except Exception:
                pass
    except Exception as e:
        duration = time.time() - t0
        traceback.print_exc()
        send_heartbeat(f"agent-{cadence}", status="failed",
                       detail=str(e)[:200],
                       duration_s=duration)
        if log_activity_async:
            try:
                log_activity_async(
                    role="ops_scheduler",
                    action=f"cadence_{cadence}_complete",
                    status="failed",
                    duration_s=duration,
                    api_calls=api_counter.get("count") if isinstance(api_counter, dict) else None,
                    bq_bytes_scanned=bq_counter.get("bytes") if isinstance(bq_counter, dict) else None,
                    details={"cadence": cadence, "error": str(e)[:500]},
                )
            except Exception:
                pass


def _refresh_bigquery():
    """Run all BQ collectors + view refresh once before report generation."""
    print("[ops-scheduler] Refreshing BigQuery before report generation…")
    try:
        from reporting_scheduler import run_refresh
        run_refresh(incremental=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] BQ refresh failed: {e}")

    # Freshness audit: catch silent collector failures (collector ran but
    # fetched zero rows). Distinguishes platform-paused (legitimate, e.g.
    # Microsoft/LinkedIn currently dark) from collector-broken (real bug).
    # Posts a Slack alert to #notifications when any channel is ≥2 days stale.
    try:
        from scripts.check_freshness import audit, post_slack_alert
        stale = audit()
        if stale:
            print(f"[ops-scheduler] Freshness: {len(stale)} stale channel(s)")
            post_slack_alert(stale)
    except Exception as e:
        print(f"[ops-scheduler] Freshness check failed (non-fatal): {e}")


def _refresh_drive_index():
    """Re-index Drive assets so role prompts reference the latest files."""
    try:
        from analysers.drive_knowledge import index_shared_drive
        index_shared_drive()
    except Exception as e:
        print(f"[ops-scheduler] Drive index refresh failed (non-fatal): {e}")


def _run_spike_detector() -> list:
    """Detect daily anomalies. Returns the spikes list for the daily summary."""
    try:
        from analysers.spike_detector import detect_spikes
        spikes = detect_spikes() or []
        print(f"[ops-scheduler] Spike detector found {len(spikes)} spike(s)")
        return spikes
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Spike detector error: {e}")
        return []


def _run_weekly_keyword_autofix() -> dict:
    """
    Sunday-only: silently scan ENABLED keywords + active negatives, apply
    the rule-mandated action, log counts to BQ for Monday's weekly summary.

    Returns: {paused, deleted, negatives_removed, age_skipped, errors}.
    On non-Sunday days, returns {} and does nothing.
    """
    counts = {}
    try:
        from analysers.google_ads_audit_tasks import _is_weekly_keyword_day
        if not _is_weekly_keyword_day():
            return {}

        # ── Active keyword violations (always-neg / brand / competitor /
        #    language-mismatch / QS+IS-lost) ────────────────────────────
        from scripts.audit_active_keywords import (
            scan_active_keywords as scan_kw,
            write_csv as write_kw_csv,
        )
        kw_violations = scan_kw()
        kw_csv = write_kw_csv(kw_violations)
        skipped_age = sum(1 for v in kw_violations if v.get("age_guard_skip"))

        if kw_violations:
            from scripts.action_audit_violations import execute as execute_kw
            kw_counts = execute_kw(kw_violations, dry_run=False)
            counts.update({
                "kw_paused":  kw_counts.get("paused", 0),
                "kw_deleted": kw_counts.get("deleted", 0),
                "kw_errors":  kw_counts.get("errors", 0),
                "age_skipped": skipped_age,
            })
        else:
            counts.update({"kw_paused": 0, "kw_deleted": 0, "kw_errors": 0,
                           "age_skipped": skipped_age})

        # ── Active negative violations (competitors + brand-only as
        #    negatives — remove them silently, no spend at risk) ────────
        from scripts.audit_active_negatives import (
            scan_active_negatives as scan_neg,
            remove_negatives as exec_neg,
        )
        neg_violations = scan_neg()
        if neg_violations:
            removed = exec_neg(neg_violations)
            counts["neg_removed"] = removed
        else:
            counts["neg_removed"] = 0

        # Log to BQ so Monday's summary can pick it up
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="keyword_management",
            action="weekly_autofix",
            status="success",
            details=counts,
            rows_affected=(counts.get("kw_paused", 0)
                           + counts.get("kw_deleted", 0)
                           + counts.get("neg_removed", 0)),
        )
        print(f"[weekly-autofix] {counts}")
        return counts
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[weekly-autofix] failed (non-fatal): {e}")
        return counts


def _run_google_ads_audit() -> list:
    """Daily impression-share, quality-score, and search-terms audit.
    Creates Asana tasks with consolidated recommendations."""
    try:
        from analysers.google_ads_audit_tasks import create_audit_tasks
        tasks = create_audit_tasks()
        print(f"[ops-scheduler] Google Ads audit: {len(tasks)} task(s) created")
        return tasks
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Google Ads audit error: {e}")
        return []


def _run_microsoft_ads_audit() -> list:
    """Daily Microsoft Ads IS, QS, and search-terms audit. Mirrors the Google
    Ads audit shape, logged under role=performance_audit, channel=microsoft_ads."""
    try:
        from analysers.microsoft_ads_audit_tasks import create_audit_tasks
        tasks = create_audit_tasks()
        print(f"[ops-scheduler] Microsoft Ads audit: {len(tasks)} task(s) created")
        return tasks
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Microsoft Ads audit error: {e}")
        return []


def _run_display_audit() -> list:
    """Per-channel display/social audit (Meta, Snap, TikTok, LinkedIn) —
    creative fatigue, frequency saturation, zero-conv high-spend pause.
    Logs under role=performance_audit with channel as a dimension."""
    try:
        from analysers.display_audit_tasks import create_audit_tasks
        tasks = create_audit_tasks()
        print(f"[ops-scheduler] Display audit (Meta/Snap/TT/LI): {len(tasks)} task(s) created")
        return tasks
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Display audit error: {e}")
        return []


# ── Scale/pause digest cadence ──────────────────────────────────────────────
# The team asked for the #approvals digest every N days, not nightly.
# Tracked via a state file under .cache/ so the cadence survives restarts.
_SCALE_PAUSE_STATE_FILE = ".cache/last_scale_pause_run.txt"


def _read_last_scale_pause_date() -> "date | None":
    from pathlib import Path
    p = Path(_SCALE_PAUSE_STATE_FILE)
    if not p.exists():
        return None
    try:
        return date.fromisoformat(p.read_text().strip())
    except Exception:
        return None


def _should_run_scale_pause() -> bool:
    """Return True if SCALE_PAUSE_DIGEST_INTERVAL_DAYS+ days since last run.

    Returns True on first ever run (state file missing) so we don't lock the
    team out of digests until the file is bootstrapped.
    """
    from config import SCALE_PAUSE_DIGEST_INTERVAL_DAYS
    last = _read_last_scale_pause_date()
    if last is None:
        return True
    return (date.today() - last).days >= SCALE_PAUSE_DIGEST_INTERVAL_DAYS


def _days_until_next_scale_pause() -> int:
    from config import SCALE_PAUSE_DIGEST_INTERVAL_DAYS
    last = _read_last_scale_pause_date()
    if last is None:
        return 0
    elapsed = (date.today() - last).days
    return max(0, SCALE_PAUSE_DIGEST_INTERVAL_DAYS - elapsed)


def _mark_scale_pause_ran() -> None:
    from pathlib import Path
    p = Path(_SCALE_PAUSE_STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(date.today().isoformat())


def _run_campaign_health() -> tuple[list, list]:
    """Cross-channel CPQL/CPL health check -> Asana tasks + force-executes scale/pause.
    Returns (tasks, findings) so findings can be used in the Slack recommendations message.
    """
    try:
        from analysers.campaign_health_tasks import create_health_tasks
        from analysers.campaign_health import audit_campaign_health
        findings = audit_campaign_health()
        tasks = create_health_tasks(findings=findings)
        print(f"[ops-scheduler] Campaign health: {len(tasks)} task(s) created")
        return tasks, findings
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Campaign health error: {e}")
        return [], []



def _nightly():
    """One combined nightly run — chains weekly/monthly/quarterly where applicable."""

    # 1. Refresh BigQuery once so the dashboard + report read fresh data.
    _refresh_bigquery()

    # 1b. Re-index Drive so role prompts pick up newly shared files.
    _refresh_drive_index()

    # 2. Run the daily Claude cadence (collectors, role analysis, Asana tasks,
    #    Slack summary, HTML report rendering with Drive upload).
    _run_with_heartbeat("daily")

    # 3. Spike detector — returns list, folded into summary message.
    spikes = _run_spike_detector()

    # 3b. Per-channel performance audits, all under role=performance_audit:
    #   - Google Ads:        IS / QS / search terms / keyword auto-pause
    #   - Microsoft Ads:     IS / QS / search terms (mirror of Google)
    #   - Meta/Snap/TT/LI:   creative fatigue / frequency saturation / zero-conv pause
    # Asana tasks created per channel × bucket.
    audit_tasks = _run_google_ads_audit()
    audit_tasks += _run_microsoft_ads_audit()
    audit_tasks += _run_display_audit()

    # 3c. Cross-channel CPQL/CPL health check -> Asana tasks + force-executes scale/pause
    #     Cost: channel source | Leads: HubSpot Lead Module | Window: 14d
    #     Cadence: every SCALE_PAUSE_DIGEST_INTERVAL_DAYS days (default 4) — NOT daily.
    #     Tracked via .cache/last_scale_pause_run.txt; resets across restarts.
    if _should_run_scale_pause():
        health_tasks, health_findings = _run_campaign_health()
        _mark_scale_pause_ran()
    else:
        from config import SCALE_PAUSE_DIGEST_INTERVAL_DAYS
        days_until = _days_until_next_scale_pause()
        print(f"[ops-scheduler] Skipping campaign health digest "
              f"(cadence {SCALE_PAUSE_DIGEST_INTERVAL_DAYS}d, "
              f"next run in {days_until}d)")
        health_tasks, health_findings = [], []

    # 3d. Asana housekeeping — roll stale due dates forward, send overdue reminders
    try:
        from executors.asana_maintenance import run_daily_maintenance
        run_daily_maintenance()
    except Exception as e:
        print(f"[ops-scheduler] Asana maintenance failed (non-fatal): {e}")

    # 3e. Asana completion sync — update asana_task_status in BQ so the
    #     Activity Dashboard shows accurate completed/open counts nightly.
    try:
        from collectors.asana_sync import run_full_sync
        n_synced = run_full_sync()
        print(f"[ops-scheduler] Asana sync: {n_synced} task status rows written")
    except Exception as e:
        print(f"[ops-scheduler] Asana sync failed (non-fatal): {e}")

    # 3f. LinkedIn token refresh — tokens expire every 60 days; refresh nightly
    try:
        from scripts.linkedin_refresh import refresh_token
        refresh_token()
    except Exception as e:
        print(f"[ops-scheduler] LinkedIn token refresh failed (non-fatal): {e}")

    # 3g. WEEKLY KEYWORD AUTO-FIX — Sunday Riyadh only.
    # Silently scans all ENABLED keywords + active negatives, applies the
    # rule-mandated action (pause / delete / remove-negative), and logs the
    # counts to BQ so Monday's weekly summary picks them up.
    weekly_fix_counts = _run_weekly_keyword_autofix()

    # 4. Audit is SILENT — Asana tasks are the record. No daily Slack post.
    #    Weekly Slack summary goes out Monday night (step below).
    _log_nightly_audit_to_bq(audit_tasks, health_tasks)

    today = date.today()
    if today.weekday() == 0:                              # Monday -> weekly
        _run_with_heartbeat("weekly")
        _post_weekly_summary(                             # Weekly Slack digest
            spikes=spikes,
            audit_tasks=audit_tasks,
            health_tasks=health_tasks,
            health_findings=health_findings,
        )
    if today.day == 1:                                    # 1st -> monthly
        _run_with_heartbeat("monthly")
    if today.day == 1 and today.month in (1, 4, 7, 10):  # Quarter start
        _run_with_heartbeat("quarterly")


def _log_nightly_audit_to_bq(audit_tasks: list, health_tasks: list):
    """Silently log nightly audit counts to BQ activity log — no Slack."""
    try:
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="ops_scheduler",
            action="nightly_audit_complete",
            status="success",
            details={
                "audit_tasks_created": len(audit_tasks),
                "health_tasks_created": len(health_tasks),
            },
        )
    except Exception as e:
        print(f"[ops-scheduler] BQ audit log failed (non-fatal): {e}")


def _post_weekly_summary(spikes: list | None = None,
                          audit_tasks: list | None = None,
                          health_tasks: list | None = None,
                          health_findings: list | None = None):
    """Post a consolidated weekly summary to #notify every Monday night."""
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY
        from notifications.quiet import is_quiet, quiet_log
        from notifications.daily_summary import build_daily_summary_text, build_recommendations_text
        from datetime import datetime, timezone, timedelta

        riyadh = timezone(timedelta(hours=3))
        week_end   = datetime.now(riyadh).strftime("%d %b")
        week_start = (datetime.now(riyadh) - timedelta(days=6)).strftime("%d %b")

        # Reuse daily summary builder — it already shows 7d performance,
        # alerts, and Asana counts, which is exactly the weekly read.
        base_text = build_daily_summary_text(
            spikes=spikes or [],
            audit_tasks=audit_tasks or [],
            health_tasks=health_tasks or [],
        )
        # Prepend week label
        header = f"*Weekly Summary  {week_start} – {week_end}*\n"
        text = header + base_text

        # Activity link — everything the agent did this week (keyword pauses,
        # deletions, negative cleanups, data-quality auto-heals, etc.) is
        # already logged to BQ and visible on the agent activity dashboard.
        # No need to duplicate counts in Slack — just point to the dashboard.
        import os as _os
        activity_url = (_os.getenv("ACTIVITY_SHORT_URL")
                        or "https://nexa-web-production-6a6b.up.railway.app/activity")
        text += f"\n\n_Agent activity this week:_ <{activity_url}|see what the agent did>"

        if is_quiet():
            quiet_log("ops-scheduler-weekly", SLACK_CHANNEL_NOTIFY, text)
            return

        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=text)

        # Follow-up recommendations thread if health findings exist
        if health_findings:
            rec_text = build_recommendations_text(health_findings)
            if rec_text:
                client.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=rec_text)

        print(f"[ops-scheduler] Posted weekly summary to Slack")

        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="ops_scheduler",
            action="post_weekly_summary",
            status="success",
            details={"spikes": len(spikes or []),
                     "audit_tasks": len(audit_tasks or []),
                     "health_tasks": len(health_tasks or [])},
        )
    except Exception as e:
        print(f"[ops-scheduler] Weekly summary post failed (non-fatal): {e}")


def _run_health_check():
    """Run health check — results logged to BQ only, visible in Activity Dashboard."""
    try:
        from scripts.health_check import main as hc_main
        hc_main(post_slack=False)
    except Exception as e:
        print(f"[ops-scheduler] Health check failed: {e}")
        traceback.print_exc()


def run():
    schedule.every().day.at("05:00").do(_nightly)   # 08:00 Riyadh = 05:00 UTC
    # Health check every hour 09:00–17:00 Riyadh (06:00–14:00 UTC)
    # On-demand outside those hours via POST /api/run-health-check
    for _utc_h in range(6, 15):  # 06,07,...,14 UTC = 09,10,...,17 Riyadh
        schedule.every().day.at(f"{_utc_h:02d}:00").do(_run_health_check)

    print("=" * 52)
    print("  Qoyod Operational Scheduler — LIVE")
    print("=" * 52)
    print("  Daily    08:00 Riyadh (05:00 UTC)")
    print("  Weekly   added Mon mornings")
    print("  Monthly  added on 1st of month")
    print("  Health   09:00–17:00 Riyadh hourly (on-demand outside hours)")
    print("  Manual:  python main.py on_demand")
    print("=" * 52)

    # Startup health check — logs to console only; no Slack post.
    # Only the 07:00 scheduled run posts to Slack (and only on failures).
    try:
        from scripts.health_check import main as hc_main
        hc_main(post_slack=False)  # console-only on startup
    except Exception as e:
        print(f"[ops-scheduler] Startup health check error: {e}")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
