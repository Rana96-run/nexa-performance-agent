"""
Operational scheduler — fires the performance agent at the right cadences.

All times in Riyadh (UTC+3). Heavy work at 3 AM so tasks and summaries
are ready when the team wakes up.

  03:00 Riyadh = 00:00 UTC  -> daily (always)
  Mon   03:00               -> + weekly analysis
  1st   03:00               -> + monthly analysis
  Jan/Apr/Jul/Oct 1st 03:00 -> + quarterly analysis
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


def _post_report_ready(spikes: list | None = None,
                       audit_tasks: list | None = None,
                       health_tasks: list | None = None,
                       health_findings: list | None = None):
    """Post two Slack messages:
    1. Main: report link + peak numbers + agent actions + task counts
    2. Follow-up: recommended actions per campaign (summarised, one line each)
    """
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY
        from notifications.quiet import is_quiet, quiet_log
        from notifications.daily_summary import build_daily_summary_text, build_recommendations_text

        main_text = build_daily_summary_text(
            spikes=spikes or [],
            audit_tasks=audit_tasks or [],
            health_tasks=health_tasks or [],
        )
        rec_text = build_recommendations_text(health_findings or [])

        if is_quiet():
            quiet_log("ops-scheduler", SLACK_CHANNEL_NOTIFY, main_text)
            if rec_text:
                quiet_log("ops-scheduler", SLACK_CHANNEL_NOTIFY, rec_text)
            return

        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=main_text)
        if rec_text:
            client.chat_postMessage(channel=SLACK_CHANNEL_NOTIFY, text=rec_text)
        print(f"[ops-scheduler] Posted daily summary + recommendations to Slack")
    except Exception as e:
        print(f"[ops-scheduler] Daily summary post failed (non-fatal): {e}")


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
    audit_tasks = _run_google_ads_audit()

    # 3c. Cross-channel CPQL/CPL health check -> Asana tasks + force-executes scale/pause
    #     Cost: channel source | Leads: HubSpot Lead Module | Window: 14d
    health_tasks, health_findings = _run_campaign_health()

    # 4. Main Slack message + follow-up recommendations message
    _post_report_ready(
        spikes=spikes,
        audit_tasks=audit_tasks,
        health_tasks=health_tasks,
        health_findings=health_findings,
    )

    today = date.today()
    if today.weekday() == 0:                              # Monday -> weekly
        _run_with_heartbeat("weekly")
    if today.day == 1:                                    # 1st -> monthly
        _run_with_heartbeat("monthly")
    if today.day == 1 and today.month in (1, 4, 7, 10):  # Quarter start
        _run_with_heartbeat("quarterly")


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
    # Health check: every morning at 07:00 Riyadh (04:00 UTC) so Amar sees it at start of day
    schedule.every().day.at("04:00").do(_run_health_check)

    print("=" * 52)
    print("  Qoyod Operational Scheduler — LIVE")
    print("=" * 52)
    print("  Nightly  03:00 Riyadh (00:00 UTC)")
    print("  Weekly   added Mon nights")
    print("  Monthly  added on 1st of month")
    print("  Health   07:00 Riyadh (04:00 UTC) — daily")
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
