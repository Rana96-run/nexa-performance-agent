"""
Operational scheduler — fires the performance agent at the right cadences.

All times in Riyadh (UTC+3). Heavy work at 3 AM so tasks and summaries
are ready when the team wakes up.

  03:00 Riyadh = 00:00 UTC  -> daily (always)
  Mon   03:00               -> + weekly analysis
  1st   03:00               -> + monthly analysis
  Jan/Apr/Jul/Oct 1st 03:00 -> + quarterly analysis
"""
import json
import schedule
import time
import traceback
from datetime import date
from logs.logger import setup_global_logging

setup_global_logging("operational-scheduler")  # captures every print() into logs/
from main import run_cadence
from notifications.notify import send_heartbeat


def _run_with_heartbeat(cadence: str):
    """Run a cadence and emit a heartbeat on completion or failure."""
    t0 = time.time()
    try:
        run_cadence(cadence)
        send_heartbeat(f"agent-{cadence}", status="ok",
                       detail=f"{cadence} cadence completed",
                       duration_s=time.time() - t0)
    except Exception as e:
        traceback.print_exc()
        send_heartbeat(f"agent-{cadence}", status="failed",
                       detail=str(e)[:200],
                       duration_s=time.time() - t0)


def _refresh_bigquery():
    """Run all BQ collectors + view refresh once before report generation."""
    print("[ops-scheduler] Refreshing BigQuery before report generation…")
    try:
        from reporting_scheduler import run_refresh
        run_refresh(incremental=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] BQ refresh failed: {e}")


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
            role="keyword_approval",
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


def _read_data_quality_summary() -> dict:
    """Read the latest 'data_quality_autoheal' BQ activity log row from the
    last 8 days (so the Monday weekly summary covers a full week of refresh
    runs). Aggregates the counts across all runs in that window."""
    try:
        from collectors.bq_writer import get_client
        c = get_client()
        q = """
          SELECT details
          FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
          WHERE role = 'bq_refresh'
            AND action = 'data_quality_autoheal'
            AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 8 DAY)
        """
        agg = {
            "future_partitions_removed":              0,
            "zero_row_channels_recovered":            0,
            "zero_row_channels_still_empty":          0,
            "negative_partitions_recovered":          0,
            "inconsistent_lead_partitions_recovered": 0,
        }
        for r in c.query(q).result():
            d = json.loads(r.details) if r.details else {}
            for k in agg:
                agg[k] += d.get(k, 0) or 0
        return agg
    except Exception as e:
        print(f"[data-quality] BQ read failed: {e}")
    return {}


def _read_weekly_autofix_summary() -> dict:
    """Read the latest 'weekly_autofix' BQ activity log row (within last 36h
    so we capture Sunday's run when Monday summary fires Riyadh-time)."""
    try:
        from collectors.bq_writer import get_client
        import json
        c = get_client()
        q = """
          SELECT details
          FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
          WHERE role = 'keyword_approval'
            AND action = 'weekly_autofix'
            AND ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 36 HOUR)
          ORDER BY ts DESC
          LIMIT 1
        """
        for r in c.query(q).result():
            return json.loads(r.details) if r.details else {}
    except Exception as e:
        print(f"[weekly-autofix] BQ read failed: {e}")
    return {}


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

    # 3b. Google Ads daily audit — IS, QS, search terms, keyword auto-pause -> Asana tasks
    # (Keyword Slack-approval flow has been removed — keywords go to Asana, negatives direct-execute.)
    audit_tasks = _run_google_ads_audit()

    # 3c. Cross-channel CPQL/CPL health check -> Asana tasks + force-executes scale/pause
    #     Cost: channel source | Leads: HubSpot Lead Module | Window: 14d
    health_tasks, health_findings = _run_campaign_health()

    # 3d. Asana housekeeping — roll stale due dates forward, send overdue reminders
    try:
        from executors.asana_maintenance import run_daily_maintenance
        run_daily_maintenance()
    except Exception as e:
        print(f"[ops-scheduler] Asana maintenance failed (non-fatal): {e}")

    # 3e. Zapier monitor — auto-replay errored zap runs, alert on persistent failures
    try:
        from collectors.zapier import run as zapier_run
        zapier_run()
    except Exception as e:
        print(f"[ops-scheduler] Zapier monitor failed (non-fatal): {e}")

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

        # Append "what we auto-fixed yesterday" block — read from BQ.
        autofix = _read_weekly_autofix_summary()
        if autofix:
            paused  = autofix.get("kw_paused", 0)
            deleted = autofix.get("kw_deleted", 0)
            neg_rm  = autofix.get("neg_removed", 0)
            age_sk  = autofix.get("age_skipped", 0)
            if (paused + deleted + neg_rm + age_sk) > 0:
                fix_lines = ["\n*🔧 Auto-fixed this week*"]
                if paused:  fix_lines.append(f"  • {paused} keyword(s) paused (always-neg / brand / competitor / lang-mismatch / QS+IS-lost)")
                if deleted: fix_lines.append(f"  • {deleted} keyword(s) deleted (QS<5, lost-IS>80%, zero historical spend)")
                if neg_rm:  fix_lines.append(f"  • {neg_rm} negative(s) removed (competitor names / brand terms wrongly excluded)")
                if age_sk:  fix_lines.append(f"  • {age_sk} keyword(s) skipped — under 10-day age guard, will reconsider next week")
                text += "\n" + "\n".join(fix_lines)

        # Append data-quality auto-heal block — silent fixes from the BQ
        # refresh pipeline (future partitions, zero-row channels, etc.)
        dq = _read_data_quality_summary()
        if dq:
            fp = dq.get("future_partitions_removed", 0)
            zr_ok = dq.get("zero_row_channels_recovered", 0)
            zr_no = dq.get("zero_row_channels_still_empty", 0)
            ne = dq.get("negative_partitions_recovered", 0)
            inc = dq.get("inconsistent_lead_partitions_recovered", 0)
            if (fp + zr_ok + zr_no + ne + inc) > 0:
                dq_lines = ["\n*🩹 Data quality (silent auto-heal)*"]
                if fp:    dq_lines.append(f"  • {fp} future-dated row(s) removed")
                if zr_ok: dq_lines.append(f"  • {zr_ok} silent-failing channel(s) re-fetched successfully")
                if zr_no: dq_lines.append(f"  • {zr_no} channel(s) still 0 rows — likely paused / token issue")
                if ne:    dq_lines.append(f"  • {ne} negative-spend partition(s) cleaned + re-fetched")
                if inc:   dq_lines.append(f"  • {inc} inconsistent lead partition(s) cleaned + re-fetched")
                text += "\n" + "\n".join(dq_lines)

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
    """Run the self-contained health check and post results to Slack."""
    try:
        from scripts.health_check import main as hc_main
        hc_main(post_slack=True)
    except Exception as e:
        print(f"[ops-scheduler] Health check failed: {e}")
        traceback.print_exc()


def run():
    schedule.every().day.at("00:00").do(_nightly)   # 03:00 Riyadh = 00:00 UTC
    # Full audit every 6 hours: 03:00 / 09:00 / 15:00 / 21:00 Riyadh
    # (00:00 / 06:00 / 12:00 / 18:00 UTC)
    # The 00:00 slot is already covered by _nightly which embeds the startup check.
    schedule.every(6).hours.do(_run_health_check)

    print("=" * 52)
    print("  Qoyod Operational Scheduler — LIVE")
    print("=" * 52)
    print("  Nightly  03:00 Riyadh (00:00 UTC)")
    print("  Weekly   added Mon nights")
    print("  Monthly  added on 1st of month")
    print("  Health   every 6h — Railway, listener, all APIs")
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
