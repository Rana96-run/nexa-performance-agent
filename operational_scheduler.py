"""
Operational scheduler — fires the performance agent at the right cadences.

All times in Riyadh (UTC+3). Heavy work at 8 AM so the team has fresh
tasks + summaries waiting at the start of the workday.

  08:00 Riyadh = 05:00 UTC  -> daily (always)
  Mon   08:00               -> + weekly analysis
  1st   08:00               -> + monthly analysis
  Jan/Apr/Jul/Oct 1st 08:00 -> + quarterly analysis
"""
import os
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

    # gclid_attribution daily refresh — rolling 30-day window of Google Ads
    # click_view data. Without this the table goes stale and Google ID
    # attribution degrades from 77% → 0% over 30 days.
    # Added 2026-05-15.
    try:
        from collectors import gclid_clickview
        rows = gclid_clickview.collect_clickview(days=30)
        print(f"[ops-scheduler] gclid_attribution refreshed: {rows} rows")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] gclid_clickview refresh failed (non-fatal): {e}")

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


def _run_period_compare_weekly() -> dict:
    """Last 7 days vs prior 7 days — auto-Apr-vs-May-style compare every day.
    Flags CPQL/ROAS/QUAL regressions and launch waves."""
    try:
        from analysers.period_compare import compare_weekly, to_markdown
        p = compare_weekly()
        flags = ", ".join(p.flags) if p.flags else "none"
        print(f"[ops-scheduler] period_compare(weekly): "
              f"{p.period_a[0]}..{p.period_a[1]} vs {p.period_b[0]}..{p.period_b[1]}, "
              f"flags=[{flags}]")
        # Print full markdown narrative to stdout (Railway log)
        print(to_markdown(p))
        return {"label": p.label, "flags": p.flags}
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] period_compare(weekly) error: {e}")
        return {}


def _run_period_compare_monthly() -> dict:
    """Monthly: current month-to-date vs same days of previous month.
    Runs on Mondays only — heavier query, weekly cadence is enough."""
    try:
        from analysers.period_compare import compare_monthly, to_markdown
        p = compare_monthly()
        flags = ", ".join(p.flags) if p.flags else "none"
        print(f"[ops-scheduler] period_compare(monthly): "
              f"{p.period_a[0]}..{p.period_a[1]} vs {p.period_b[0]}..{p.period_b[1]}, "
              f"flags=[{flags}]")
        print(to_markdown(p))
        return {"label": p.label, "flags": p.flags}
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] period_compare(monthly) error: {e}")
        return {}


def _run_forecaster() -> dict:
    """Project end-of-month and end-of-next-month spend/leads/SQLs/CPQL/ROAS
    based on trailing 14-day daily rate. Read-only."""
    try:
        from analysers.forecaster import forecast, to_markdown
        f = forecast()
        print(f"[ops-scheduler] forecaster: as of {f.today}, "
              f"trend window {f.trend_window_days}d")
        print(to_markdown(f))
        return {"today": f.today,
                "eom_spend": (f.end_of_month.projected or {}).get("spend") if f.end_of_month else None}
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] forecaster error: {e}")
        return {}


def _run_spend_drift() -> dict:
    """Nightly spend-drift detector — 3 rules:
      1. Scaling-an-underperformer (14d CPQL > $140 AND WoW spend > +20%)
      2. Silent-death (prior 30d > $500 AND last 7d < 5% of that)
      3. Launch-wave (≥3 first-spend within 7d on same channel)

    Returns the findings dict from analysers.spend_drift.run_all().
    Read-only — does NOT auto-create tasks. Findings appear in stdout and
    are printed into the nightly log so they can be folded into the
    Slack daily summary by a downstream task creator (TODO: build the
    spend_drift_tasks.py counterpart that turns findings into Asana posts).
    """
    try:
        from analysers.spend_drift import run_all
        findings = run_all()
        total = sum(len(v) for v in findings.values())
        print(f"[ops-scheduler] spend_drift: {total} total finding(s) — "
              + ", ".join(f"{k}={len(v)}" for k, v in findings.items()))
        for rule, items in findings.items():
            for f in items:
                print(f"[spend_drift/{rule}] {f}")
        return findings
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] spend_drift error: {e}")
        return {}


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


def _check_monitor_dates() -> None:
    """
    Auto-follow-up on approved pause/scale actions at +7 and +14 days.

    Reads agent_activity_log for actions with status='approved' that were
    logged 7 or 14 days ago. Posts a Slack check-in to #approvals asking
    the team to re-evaluate. Prevents approved actions from disappearing
    into Asana and never being measured.
    """
    try:
        from google.cloud import bigquery
        from slack_sdk import WebClient
        from config import BQ_PROJECT, BQ_DATASET, SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL

        bq  = bigquery.Client(project=BQ_PROJECT)
        today = date.today()

        sql = f"""
            SELECT action, details, ts, role
            FROM `{BQ_PROJECT}.{BQ_DATASET}.agent_activity_log`
            WHERE status = 'approved'
              AND action IN ('scale_campaign','pause_keyword','pause_ad','budget_increase')
              AND DATE(ts, 'Asia/Riyadh') IN (
                  DATE_SUB('{today}', INTERVAL 7 DAY),
                  DATE_SUB('{today}', INTERVAL 14 DAY)
              )
            ORDER BY ts DESC
            LIMIT 20
        """
        rows = list(bq.query(sql).result())
        if not rows:
            print("[ops-scheduler] Monitor dates: nothing due today")
            return

        # Group by interval
        due_7d, due_14d = [], []
        for r in rows:
            action_date = r.ts.date() if hasattr(r.ts, 'date') else today
            delta = (today - action_date).days
            (due_7d if delta <= 7 else due_14d).append(r)

        lines = []
        if due_7d:
            lines.append(f"*7-day check-in ({today}) — {len(due_7d)} action(s) approved on "
                         f"{today - __import__('datetime').timedelta(days=7)}:*")
            for r in due_7d:
                d = r.details if isinstance(r.details, dict) else {}
                lines.append(f"  • {r.action}: {d.get('campaign','') or d.get('keyword','') or str(d)[:80]}")
        if due_14d:
            lines.append(f"*14-day check-in ({today}) — {len(due_14d)} action(s) approved on "
                         f"{today - __import__('datetime').timedelta(days=14)}:*")
            for r in due_14d:
                d = r.details if isinstance(r.details, dict) else {}
                lines.append(f"  • {r.action}: {d.get('campaign','') or d.get('keyword','') or str(d)[:80]}")

        msg = (
            "*Automated monitor check — approved actions due for review*\n"
            + "\n".join(lines)
            + "\n\nPull the period-compare on each campaign above and reply here "
            "with the outcome (working / not working / reversed). "
            "No ✅ needed — this is a review prompt only."
        )
        WebClient(token=SLACK_BOT_TOKEN).chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL, text=msg
        )
        print(f"[ops-scheduler] Monitor dates: posted {len(rows)} check-in(s) to #approvals")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Monitor dates check failed (non-fatal): {e}")


def _run_budget_redeployment_proposal() -> None:
    """
    Automatically propose budget redeployment when:
      - One or more campaigns are in PAUSE zone (CPQL > $100, 14d window)
      - One or more campaigns are in SCALE zone (CPQL < $60, 14d window)
      - The wasted spend is > $50/day

    For each destination (scale) campaign:
      - Creates an Asana task with the full campaign card + date range
      - Pre-adds ✅/❌ reactions to the Slack message
      - Saves asana_gid in the pending_approvals metadata so execution
        comments back to the task on approval

    For each drain campaign:
      - Creates a separate review-only Asana task (no ✅ execution)

    Runs only when _should_run_scale_pause() is True (cadence: every 4 days).
    """
    try:
        from google.cloud import bigquery
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        from config import (BQ_PROJECT, BQ_DATASET, SLACK_BOT_TOKEN,
                            SLACK_CHANNEL_APPROVAL, CPQL_PAUSE, CPQL_SCALE)
        from executors.asana import create_task
        from logs.activity_logger import log_activity_async

        bq    = bigquery.Client(project=BQ_PROJECT)
        today = date.today()
        date_from = (today - __import__("datetime").timedelta(days=14)).isoformat()
        date_to   = (today - __import__("datetime").timedelta(days=1)).isoformat()
        date_range_str = f"{date_from} to {date_to}"

        # Single query — fetches perf + most-recent campaign_id/account_id in one pass.
        # Pre-aggregate HubSpot first to avoid spend fan-out.
        sql = f"""
        WITH last_complete AS (
          SELECT MAX(date) AS d
          FROM `{BQ_PROJECT}.{BQ_DATASET}.campaigns_daily`
          WHERE spend > 0
        ),
        window_start AS (
          SELECT DATE_SUB((SELECT d FROM last_complete), INTERVAL 14 DAY) AS d
        ),
        hs AS (
          SELECT date, lead_utm_campaign,
                 SUM(leads_qualified) AS sqls
          FROM `{BQ_PROJECT}.{BQ_DATASET}.hubspot_leads_module_daily`
          WHERE date >= (SELECT d FROM window_start)
          GROUP BY date, lead_utm_campaign
        ),
        perf AS (
          SELECT
            c.channel,
            c.campaign_name,
            -- Grab most-recent campaign_id and account_id for this campaign name
            MAX(c.campaign_id)               AS campaign_id,
            MAX(c.account_id)                AS account_id,
            MIN(c.date)                      AS date_from,
            MAX(c.date)                      AS date_to,
            SUM(c.spend)                     AS spend_14d,
            COALESCE(SUM(hs.sqls), 0)        AS sqls_14d,
            SAFE_DIVIDE(SUM(c.spend), 14.0)  AS daily_avg,
            SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0)) AS cpql
          FROM `{BQ_PROJECT}.{BQ_DATASET}.campaigns_daily` c
          LEFT JOIN hs
            ON c.date = hs.date
           AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
          WHERE c.date >= (SELECT d FROM window_start)
            AND c.channel != 'microsoft_ads'   -- MS Ads budget API not wired yet
          GROUP BY c.channel, c.campaign_name
        )
        SELECT * FROM perf
        WHERE spend_14d > 50
        ORDER BY cpql ASC
        """
        rows = list(bq.query(sql).result())
        if not rows:
            print("[ops-scheduler] Budget redeployment: no campaigns with spend > $50 in 14d")
            return

        pause_zone = [r for r in rows if r.cpql and r.cpql > CPQL_PAUSE]
        scale_zone = [r for r in rows if r.cpql and r.cpql < CPQL_SCALE]

        if not pause_zone or not scale_zone:
            print("[ops-scheduler] Budget redeployment: no clear drain→scaler pair found")
            return

        wasted_per_day = sum(r.daily_avg or 0 for r in pause_zone)
        if wasted_per_day < 50:
            print(f"[ops-scheduler] Budget redeployment: ${wasted_per_day:.0f}/day freed — "
                  "below $50 threshold, skipping")
            return

        # ── Destination campaigns (scale) ──────────────────────────────────────
        freed        = wasted_per_day
        n_dest       = min(len(scale_zone), 4)
        share_each   = round(freed / n_dest, 0)
        dest_campaigns = sorted(scale_zone, key=lambda x: x.cpql or 999)[:4]

        scale_findings = []   # for Slack lines + Asana
        for r in dest_campaigns:
            new_budget = round((r.daily_avg or 0) + share_each, 2)
            # Create Asana task for each scale destination
            body = (
                f"Budget redeployment — scale destination\n\n"
                f"**Campaign:** {r.campaign_name}\n"
                f"**Channel:** {r.channel}\n"
                f"**Data window:** {date_range_str}\n\n"
                f"**Current spend:** ${r.daily_avg:.0f}/day (14d avg)\n"
                f"**Proposed budget:** ${new_budget:.0f}/day "
                f"(+${share_each:.0f} freed from drain campaigns)\n"
                f"**CPQL:** ${r.cpql:.0f}  ·  "
                f"**SQLs in window:** {int(r.sqls_14d)}  ·  "
                f"**Total spend:** ${r.spend_14d:.0f}\n\n"
                f"**Why scale:** CPQL is in scale zone (< ${CPQL_SCALE:.0f}). "
                f"Budget freed from drain campaigns (CPQL > ${CPQL_PAUSE:.0f}) is "
                f"being reallocated here.\n\n"
                f"React with ✅ in #approvals to execute this budget increase.\n\n"
                f"---\n"
                f"Created: {today.isoformat()}  ·  "
                f"Due: {(today + __import__('datetime').timedelta(days=1)).isoformat()}  ·  "
                f"Priority: High  ·  Type: Recommendation  ·  "
                f"Channel: {r.channel}  ·  Asset level: Campaign  ·  Action: Scale"
            )
            gid = create_task(
                title=f"PENDING APPROVAL: Budget Redeployment — Scale {r.campaign_name} "
                      f"+${share_each:.0f}/day ({date_range_str})",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=r.channel,
                asset_level="campaign",
                action="scale",
                campaign_name=r.campaign_name,
            )
            log_activity_async(
                role="performance_audit", action="budget_redeployment_scale_task_created",
                status="pending_approval",
                channel=r.channel, campaign_name=r.campaign_name,
                details={
                    "new_budget": new_budget, "freed_per_day": freed,
                    "cpql": r.cpql, "date_from": date_from, "date_to": date_to,
                    "asana_gid": gid,
                },
            )
            scale_findings.append({
                "action":      "scale",
                "channel":     r.channel,
                "campaign":    r.campaign_name,
                "campaign_id": str(r.campaign_id) if r.campaign_id else "",
                "account_id":  str(r.account_id)  if r.account_id  else "",
                "new_budget":  new_budget,
                "cpql":        r.cpql,
                "avg_spend":   r.daily_avg,
                "date_from":   date_from,
                "date_to":     date_to,
                "asana_gid":   gid or "",
            })

        # ── Drain campaigns (review-only Asana tasks, no auto-execution) ───────
        for r in pause_zone[:5]:
            drain_body = (
                f"Budget redeployment — drain campaign review\n\n"
                f"**Campaign:** {r.campaign_name}\n"
                f"**Channel:** {r.channel}\n"
                f"**Data window:** {date_range_str}\n\n"
                f"**CPQL:** ${r.cpql:.0f} (pause zone — threshold > ${CPQL_PAUSE:.0f})\n"
                f"**Daily spend:** ${r.daily_avg:.0f}/day  ·  "
                f"**SQLs in window:** {int(r.sqls_14d)}\n\n"
                f"**Recommended action:** Reduce budget or pause this campaign. "
                f"Freed budget has been redirected to higher-efficiency campaigns "
                f"(see linked scale tasks).\n\n"
                f"---\n"
                f"Created: {today.isoformat()}  ·  "
                f"Due: {(today + __import__('datetime').timedelta(days=2)).isoformat()}  ·  "
                f"Priority: High  ·  Type: Review  ·  "
                f"Channel: {r.channel}  ·  Asset level: Campaign  ·  Action: Review"
            )
            drain_gid = create_task(
                title=f"Review: Drain Campaign — {r.campaign_name} "
                      f"CPQL ${r.cpql:.0f} ({date_range_str})",
                description=drain_body,
                project_key="optimization",
                task_type="Review",
                channel=r.channel,
                asset_level="campaign",
                action="review",
                campaign_name=r.campaign_name,
            )
            log_activity_async(
                role="performance_audit", action="budget_redeployment_drain_task_created",
                status="needs_review",
                channel=r.channel, campaign_name=r.campaign_name,
                details={"cpql": r.cpql, "daily_avg": r.daily_avg,
                         "date_from": date_from, "date_to": date_to,
                         "asana_gid": drain_gid},
            )

        # ── Build Slack message ─────────────────────────────────────────────────
        lines = [
            f"*Budget redeployment proposal — {today.isoformat()} · 14d window: "
            f"{date_range_str}*\n",
            "*Drain campaigns (CPQL > ${:.0f} — reduce budget):*".format(CPQL_PAUSE),
        ]
        for r in pause_zone[:5]:
            lines.append(
                f"  • `{r.campaign_name}`  CPQL ${r.cpql:.0f}  ·  "
                f"${r.daily_avg:.0f}/day  →  cut budget"
            )

        lines.append(f"\n*Freed: ~${freed:.0f}/day*\n")
        lines.append("*Destination campaigns (CPQL < ${:.0f} — absorb freed budget):*".format(CPQL_SCALE))
        for f in scale_findings:
            lines.append(
                f"  • `{f['campaign']}`  CPQL ${f['cpql']:.0f}  ·  "
                f"${f['avg_spend']:.0f} → ${f['new_budget']:.0f}/day  (+${share_each:.0f})"
            )
        n_tasks = len(scale_findings) + min(len(pause_zone), 5)
        lines.append(
            f"\n{n_tasks} Asana task(s) created.\n"
            "React :white_check_mark: to execute all budget increases  ·  :x: to skip all\n"
            "_Drain-campaign tasks are review-only — no auto-execution._"
        )

        slack = WebClient(token=SLACK_BOT_TOKEN)
        resp  = slack.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL, text="\n".join(lines)
        )
        ts = resp["ts"]

        # Pre-add ✅/❌ reactions (same as post_nightly_approvals_digest)
        for emoji in ("white_check_mark", "x"):
            try:
                slack.reactions_add(channel=SLACK_CHANNEL_APPROVAL, name=emoji, timestamp=ts)
            except SlackApiError:
                pass

        # Save structured metadata keyed by ts so _handle_reaction() can execute on ✅
        from notifications.slack import save_pending_approval
        save_pending_approval(ts, {
            "action":        "budget_redeployment",
            "findings":      scale_findings,   # only scale items are executed
            "freed_per_day": round(freed, 2),
        })

        print(f"[ops-scheduler] Budget redeployment: posted to #approvals — "
              f"${freed:.0f}/day freed, {len(scale_findings)} scale task(s), "
              f"{min(len(pause_zone),5)} drain review task(s)")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Budget redeployment proposal failed (non-fatal): {e}")


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

    # 1a. Daily reconciliation: BQ vs HubSpot — catch silent data drift.
    # Logs result to BQ activity. Posts Slack alert to #health channel if
    # total or per-channel delta exceeds threshold (5% / 10%).
    # Non-fatal — never breaks the nightly pipeline.
    try:
        from analysers.daily_reconciliation import reconcile_daily
        reconcile_daily(post_slack=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] daily reconciliation failed (non-fatal): {e}")

    # 1b. Collector failure ping — closes the gap that allowed the May 18-20
    # deals/leads silent failures. Scans agent_activity_log for any collector
    # that failed in the last 24h with no recovery success since. Pings
    # #nexa-health with a one-liner; the dashboard has the full audit trail.
    try:
        from analysers.collector_failures import check_collector_failures
        check_collector_failures(window_hours=24, post_slack=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] collector failure check failed (non-fatal): {e}")

    # 1c. Connector Police — proactive 5-check health scan for all 9 connectors.
    # Runs freshness + row integrity + spend sanity + attribution + credentials.
    # Writes to connector_health_log BQ table. Posts to #nexa-health only if
    # any connector is BROKEN. Morning-analysis-flow gates on this check.
    try:
        from analysers.connector_tracker import run_all_checks
        tracker_result = run_all_checks(post_slack=True, write_bq=True)
        print(
            f"[ops-scheduler] Connector health: {tracker_result['overall']} — "
            f"{tracker_result['healthy_count']} healthy, "
            f"{tracker_result['warning_count']} warning, "
            f"{tracker_result['broken_count']} broken"
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] connector tracker failed (non-fatal): {e}")

    # 1b. Re-index Drive so role prompts pick up newly shared files.
    _refresh_drive_index()

    # 2. Run the daily Claude cadence (collectors, role analysis, Asana tasks,
    #    Slack summary, HTML report rendering with Drive upload).
    _run_with_heartbeat("daily")

    # 3. Spike detector — returns list, folded into summary message.
    spikes = _run_spike_detector()

    # 3a. Spend-drift detector — 3 nightly rules (scaling-underperformer,
    #     silent-death, launch-wave). Read-only — produces findings that
    #     show up in the operational log. To be wired into Slack
    #     #approvals via a follow-up spend_drift_tasks.py module.
    drift_findings = _run_spend_drift()

    # 3a-bis. Period-over-period auto-comparator + forecaster.
    #         CLAUDE.md mandates: every nightly run includes a weekly compare
    #         (last 7d vs prior 7d) and a forward-looking forecast. Monday
    #         additionally runs the monthly compare. Read-only — findings
    #         feed downstream digests.
    _run_period_compare_weekly()
    if date.today().weekday() == 0:   # Monday in Riyadh
        _run_period_compare_monthly()
    _run_forecaster()

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
        # 3c-bis. Budget redeployment proposal — when CPQL zones diverge,
        #         auto-generate a $/day reallocation proposal to #approvals.
        #         Same 4-day cadence as campaign health. No execution — ✅ gate applies.
        _run_budget_redeployment_proposal()
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

    # 3g. Monitor date follow-ups — auto-check approved actions at +7 and +14 days.
    #     Reads agent_activity_log for approved pause/scale/budget actions from
    #     7 and 14 days ago. Posts a Slack re-evaluation prompt to #approvals.
    #     No ✅ needed — review-only. Runs nightly (never misses a follow-up).
    _check_monitor_dates()

    # 3h. WEEKLY KEYWORD AUTO-FIX — Sunday Riyadh only.
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


def _catchup_if_stale():
    """On container start, check if paid_channel_daily is stale (nightly missed due to redeploy).
    If data is > 1 day behind AND it's past 06:00 UTC (nightly window safely past), run a BQ
    refresh in the background — data only, no Slack/Asana actions."""
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    # Don't catch up if we're still before the nightly window — it hasn't fired yet
    if now_utc.hour < 6:
        print("[ops-scheduler] Startup: before nightly window — skipping catch-up check")
        return
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        bq = get_client()
        # Check EACH source table independently — a join view masks per-table
        # staleness (May 18 incident: campaigns_daily was current, but
        # hubspot_leads_module_daily was 24h behind, and the view showed fresh).
        sql = f"""
        SELECT
          (SELECT DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY)
           FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`) AS spend_behind,
          (SELECT DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY)
           FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`) AS leads_behind,
          (SELECT DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY)
           FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`) AS deals_behind
        """
        r = list(bq.query(sql).result())[0]
        worst = max(int(r.spend_behind or 0), int(r.leads_behind or 0), int(r.deals_behind or 0))
        if worst <= 1:
            print(f"[ops-scheduler] Startup: all tables fresh "
                  f"(spend={r.spend_behind}d, leads={r.leads_behind}d, deals={r.deals_behind}d)")
            return
        print(f"[ops-scheduler] Startup: stale data (spend={r.spend_behind}d, "
              f"leads={r.leads_behind}d, deals={r.deals_behind}d) — running catch-up BQ refresh")
        import threading
        threading.Thread(target=_refresh_bigquery, name="startup-catchup", daemon=True).start()
    except Exception as e:
        print(f"[ops-scheduler] Startup catch-up check failed (non-fatal): {e}")


def _watchdog_tick():
    """Every-4h tick: never let BQ go stale. Independent of the nightly run —
    catches missed schedules (Railway redeploy, scheduler crash, gate-block)
    AND triggers re-pulls to catch HubSpot workflow re-attributions."""
    try:
        from analysers.freshness_watchdog import run_watchdog
        run_watchdog(post_slack=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] watchdog failed (non-fatal): {e}")


def _update_action_sheet():
    """Append team-visible actions to the master ZATCA Action Log sheet.

    Scans agent_activity_log since the last logged date in the sheet,
    appends new team-visible action rows. Idempotent — uses sheet's own
    last-row date as cursor. Runs nightly at 02:00 UTC = 05:00 Riyadh,
    so the team sees yesterday's actions by 8 AM Riyadh standup.
    """
    try:
        from analysers.sheet_action_logger import update_sheet
        result = update_sheet()
        print(f"[ops-scheduler] Sheet logger: {result['detail']}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Sheet update failed (non-fatal): {e}")

    # Action Points tab — live Asana mirror (dedup'd, grouped by channel,
    # real status from Asana custom Status field). Rebuilt fresh each run so
    # it never drifts from Asana like the old hand-curated snapshot did.
    try:
        from analysers.action_points_sync import update_action_points
        ap = update_action_points()
        print(f"[ops-scheduler] Action Points: {ap['detail']}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Action Points sync failed (non-fatal): {e}")


def _refresh_spend_only():
    """Lightweight refresh — only the 5 paid spend collectors.

    Runs every 2 hours during the workday to close the same-day spend gap
    from platform retroactive adjustments (Meta click-fraud refunds, Snap/MS
    impression billing finalization, Google invalid-click reversals).
    Skips HubSpot collectors (heavy) and view refresh (no schema change).

    Each platform takes ~30s; total ~3 min per cycle.
    Added 2026-05-25 after dashboard showed $1670 vs platforms' $1700.
    """
    from collectors import (google_ads_bq, meta_bq, snap_bq, tiktok_bq,
                             microsoft_ads_bq)
    SPEND_COLLECTORS = [
        ("google_ads",     google_ads_bq.collect_and_write),
        ("meta",           meta_bq.collect_and_write),
        ("snapchat",       snap_bq.collect_and_write),
        ("tiktok",         tiktok_bq.collect_and_write),
        ("microsoft_ads",  microsoft_ads_bq.collect_and_write),
    ]
    print("[ops-scheduler] Workday spend refresh starting…")
    total = 0
    for name, fn in SPEND_COLLECTORS:
        try:
            n = fn(incremental=True)
            total += n or 0
            print(f"  {name}: {n} rows")
        except Exception as e:
            print(f"  {name}: FAILED {e}")
    print(f"[ops-scheduler] Workday spend refresh wrote {total} rows total")


def _daily_full_mirror():
    """Daily 06:00 UTC (09:00 Riyadh) — full sync_full_mirror of HubSpot.
    The 12h scheduled refresh runs incremental; this is the BELT-AND-BRACES
    full re-pull that guarantees re-attributed leads are picked up every day."""
    try:
        from collectors import hubspot_leads_bq
        print("[ops-scheduler] Daily HubSpot full mirror starting…")
        rows = hubspot_leads_bq.sync_full_mirror()
        print(f"[ops-scheduler] Daily HubSpot mirror wrote {rows} rows")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Daily HubSpot mirror failed (non-fatal): {e}")


def _compliance_monitor():
    """Daily 03:45 UTC — focused monitor for the 4 Google compliance campaigns
    (ZATCAPhase2, ZATCAVendorShop, ZATCACompetitor, FinancialStatement).

    Auto-actions (reversible, low risk):
      - Kickstart graduation: TARGET_SPEND → MAXIMIZE_CONVERSIONS once campaign
        accumulates 5+ HubSpot leads in 14d.

    Flags (require human action — flagged in stdout + memory/audit_findings.md):
      - Under-spending (< 50% of budget daily avg over 7d)
      - Max CPC cap too low (full budget spent but < 10 clicks/week)
      - High CPL (> $80 over 30+ clicks)
      - Disapproved ads on enabled campaigns
      - tCPA readiness (30+ conversions in 30d)

    See scripts/audit_compliance_monitor.py for the full logic.
    """
    try:
        import subprocess
        r = subprocess.run(
            ["python", "scripts/audit_compliance_monitor.py"],
            capture_output=True, timeout=180, cwd=os.path.dirname(__file__),
        )
        print(f"[ops-scheduler] Compliance monitor exit={r.returncode}")
        if r.stdout:
            tail = r.stdout.decode("utf-8", errors="replace").splitlines()[-30:]
            for line in tail:
                print(f"[compliance] {line}")
        if r.returncode == 2:
            print("[ops-scheduler] ⚠ HIGH-severity compliance finding — review")
    except Exception as e:
        print(f"[ops-scheduler] Compliance monitor crashed (non-fatal): {e}")


def _daily_deep_audit():
    """Daily 03:30 UTC — deep audit catching bugs the QA gate misses.

    Adversarial-tests the KPI rule hook, checks UTM suffix integrity on every
    enabled Search campaign, flags disapproved ads on enabled campaigns,
    checks attribution drift per channel/account, scans naming conventions.
    See scripts/audit_daily.py for the full check list.

    Auto-fixes safe categories (e.g. re-applies canonical UTM suffix if
    missing). Flags risky ones for human review.

    Caught its first real bug 2026-05-19: 3 enabled compliance campaigns
    had their UTM suffix silently cleared during UI renames — broke HubSpot
    attribution on ~$300/day of spend. Re-applied automatically.
    """
    try:
        import subprocess
        r = subprocess.run(
            ["python", "scripts/audit_daily.py"],
            capture_output=True, timeout=300, cwd=os.path.dirname(__file__),
        )
        print(f"[ops-scheduler] Daily audit exit={r.returncode}")
        if r.stdout:
            tail = r.stdout.decode("utf-8", errors="replace").splitlines()[-30:]
            for line in tail:
                print(f"[audit] {line}")
        if r.returncode == 2:
            print("[ops-scheduler] ⚠ critical audit finding — review history")
    except Exception as e:
        print(f"[ops-scheduler] Daily audit crashed (non-fatal): {e}")


def _gate_self_test():
    """Daily 04:00 UTC — verifies every QA gate check still behaves correctly
    against synthetic fixtures. Catches the 'silently broken check' failure
    mode where a refactor turns a check into security theater. Logs to
    qa_gate_events with surface='self_test'."""
    try:
        from qa.self_test import run_self_test
        r = run_self_test(post_to_bq=True)
        if r["broken_checks"]:
            print(f"[ops-scheduler] Gate self-test FAILED: {r['broken_checks']}")
        else:
            print(f"[ops-scheduler] Gate self-test: {r['passed']}/{r['total']} OK")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[ops-scheduler] Gate self-test failed (non-fatal): {e}")


def _self_heal():
    """Daily 06:30 UTC (09:30 Riyadh) — detect and fix known failure modes silently.
    No alerts. Runs AFTER the nightly cycle so views are already fresh.
    Healers: stale_views, failed_collectors, dashboard_errors, stuck_approvals, memory_update.
    All actions logged to agent_activity_log (action='self_heal')."""
    try:
        from analysers.self_healer import run_self_heal
        run_self_heal()
    except Exception as e:
        print(f"[ops-scheduler] self-heal failed (non-fatal): {e}")


def run():
    schedule.every().day.at("05:00").do(_nightly)   # 08:00 Riyadh = 05:00 UTC
    # Second BQ refresh 12h later — picks up workflow re-classifications and
    # late-arriving leads from the day. Doesn't run the full _nightly cadence,
    # just refreshes BQ data so dashboards reflect current state.
    # Added 2026-05-15 to halve attribution lag (was 24h, now 12h).
    schedule.every().day.at("17:00").do(_refresh_bigquery)  # 20:00 Riyadh = 17:00 UTC

    # ── Freshness watchdog: every 4h, NEVER let BQ go stale ──────────────────
    # Checks each source table for MAX(date) lag > 1d OR last_write > 25h ago,
    # and triggers a targeted re-sync of just the stale collector. This is the
    # safety net for the case where the 05:00/17:00 scheduled runs were missed.
    # Added 2026-05-20.
    for _utc_h in (1, 5, 9, 13, 21):   # every ~4h, spread across the day
        schedule.every().day.at(f"{_utc_h:02d}:30").do(_watchdog_tick)

    # ── Action sheet auto-update — daily 02:00 UTC = 05:00 Riyadh ───────────
    # Appends yesterday's team-visible actions to the master ZATCA Action Log
    # sheet. Replaces the manual _log_session_to_sheet.py workflow. Runs
    # before the 05:00 nightly so the sheet is current by 8 AM Riyadh standup.
    # Added 2026-05-25.
    schedule.every().day.at("02:00").do(_update_action_sheet)

    # ── Workday spend refresh — every 2h during business hours ──────────────
    # Paid platforms apply retroactive spend adjustments throughout the day
    # (Meta click-fraud refunds, Snap/MS auction finalization, Google invalid
    # click reversals — typically 1–3% of spend). Without mid-day refreshes,
    # the dashboard shows yesterday's spend with up to 12h of unfinalized
    # adjustments. Refreshing every 2h closes the gap to <0.5%.
    # Added 2026-05-25 after user reported $30 gap on $1700 yesterday spend.
    for _utc_h in (6, 8, 10, 12):  # 09:00, 11:00, 13:00, 15:00 Riyadh
        schedule.every().day.at(f"{_utc_h:02d}:00").do(_refresh_spend_only)

    # ── HubSpot full mirror — 3× daily to keep stage counts within ~4h ──────
    # Workflows re-classify leads throughout the workday (qualified, disq,
    # SQL transitions). Three explicit mirrors + the 4h watchdog guarantees
    # Hex stage counts are at most ~4h behind HubSpot reality.
    # Tightened on 2026-05-25 after the user observed yesterday's qualified
    # count was still wrong this morning (16/10 vs reality 21/21).
    schedule.every().day.at("06:00").do(_daily_full_mirror)   # 09:00 Riyadh — after nightly
    schedule.every().day.at("12:00").do(_daily_full_mirror)   # 15:00 Riyadh — midday catch
    schedule.every().day.at("19:00").do(_daily_full_mirror)   # 22:00 Riyadh — end of workday

    # ── QA gate self-test (every day at 04:00 UTC, before nightly) ───────────
    # Synthetic fixtures + known-good/known-bad inputs verify each check.
    # If a refactor silently breaks a check, this catches it.
    schedule.every().day.at("04:00").do(_gate_self_test)
    schedule.every().day.at("03:30").do(_daily_deep_audit)     # 06:30 Riyadh
    schedule.every().day.at("03:45").do(_compliance_monitor)   # 06:45 Riyadh
    schedule.every().day.at("06:30").do(_self_heal)            # 09:30 Riyadh — after nightly
    schedule.every().day.at("15:00").do(_compliance_monitor)   # 18:00 Riyadh — midday recheck
    # Health check every hour 09:00–17:00 Riyadh (06:00–14:00 UTC)
    # On-demand outside those hours via POST /api/run-health-check
    for _utc_h in range(6, 15):  # 06,07,...,14 UTC = 09,10,...,17 Riyadh
        schedule.every().day.at(f"{_utc_h:02d}:00").do(_run_health_check)

    print("=" * 60)
    print("  Qoyod Operational Scheduler — LIVE")
    print("=" * 60)
    print("  Daily    08:00 Riyadh (05:00 UTC)  — full nightly + BQ refresh")
    print("  BQ       20:00 Riyadh (17:00 UTC)  — second BQ refresh only")
    print("  Sheet   05:00 Riyadh (02:00 UTC) — append actions to master sheet")
    print("  Spend   09/11/13/15 Riyadh (06/08/10/12 UTC) — workday spend refresh")
    print("  Mirror   09/15/22 Riyadh (06/12/19 UTC) — HubSpot full mirror (3×/day)")
    print("  Self-test 07:00 Riyadh (04:00 UTC) — QA gate check verification")
    print("  Self-heal 09:30 Riyadh (06:30 UTC) — detect+fix stale views, failed collectors, 500s")  # noqa
    print("  Watchdog every ~4h — never let BQ go stale, auto-resync (4h threshold)")
    print("  Weekly   added Mon mornings")
    print("  Monthly  added on 1st of month")
    print("  Health   09:00–17:00 Riyadh hourly (on-demand outside hours)")
    print("  Manual:  python main.py on_demand")
    print("=" * 60)

    # Startup health check — logs to console only; no Slack post.
    # Only the 07:00 scheduled run posts to Slack (and only on failures).
    try:
        from scripts.health_check import main as hc_main
        hc_main(post_slack=False)  # console-only on startup
    except Exception as e:
        print(f"[ops-scheduler] Startup health check error: {e}")

    # Catch-up: if a redeploy happened during the 05:00 UTC nightly window,
    # the data refresh was killed mid-run. Fix it silently on next startup.
    _catchup_if_stale()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run()
