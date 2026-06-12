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


def _run_weekly_creative_audit() -> dict:
    """
    Sunday-only: run creative performance audit across all social channels.
    Ranks creatives by qual rate + SQLs, creates an Asana task for Creative Strategist.
    Silent on non-Sunday days.
    """
    from analysers.google_ads_audit_tasks import _is_weekly_keyword_day
    if not _is_weekly_keyword_day():
        return {}
    try:
        from analysers.creative_performance import (
            audit_creative_performance,
            audit_creative_by_campaign_type,
            format_creative_section,
        )
        from executors.asana import create_task
        from datetime import date
        from logs.activity_logger import log_activity_async

        days = 30
        social_result = audit_creative_performance(days=days, min_leads=3)
        tier_result   = audit_creative_by_campaign_type(days=days, min_leads=3)
        best  = social_result.get("best",  [])
        worst = social_result.get("worst", [])

        if not best and not worst:
            print("[weekly-creative-audit] no creative data — skipping Asana task")
            return {"skipped": True}

        creative_section = format_creative_section(social_result)
        tier_insights    = "\n".join(f"- {i}" for i in tier_result.get("insights", []))
        today = date.today().isoformat()

        description = (
            f"Creative performance audit — last {days} days (auto-generated Sunday)\n\n"
            f"CREATIVE RANKINGS (by SQL qual rate):\n{creative_section}\n\n"
            + (f"AUDIENCE TIER INSIGHTS:\n{tier_insights}\n\n" if tier_insights else "")
            + "ACTION ITEMS FOR CREATIVE STRATEGIST:\n"
            + (f"1. Scale: '{best[0]['name']}' ({best[0]['sqls']} SQLs, "
               f"{best[0]['qual_rate']*100:.0f}% qual) — duplicate into a new variant "
               "with a fresh hook, same format.\n" if best else "")
            + (f"2. Replace: '{worst[0]['name']}' ({worst[0]['disquals']} disqualified leads, "
               f"{worst[0]['qual_rate']*100:.0f}% qual) — pause and test a variant "
               "targeting the qualified buyer more explicitly.\n" if worst else "")
            + "\nScope at least 2 A/B variants per winning creative × audience tier.\n\n"
            f"Created: {today}\nDue: {today}\nPriority: Medium\n"
            f"Type: Recommendation\nChannel: social\nAsset level: ad\n"
            f"Action: optimize → [Creative Strategist]"
        )
        create_task(
            title=f"[Weekly] Creative Performance Audit — {today}",
            description=description,
            project_key="daily_activity",
            task_type="Recommendation",
            channel="meta",
            asset_level="ad",
            action="optimize",
            log_role="creative_strategy",
        )
        log_activity_async(
            role="creative_strategy", action="creative_audit_auto",
            status="success",
            details={"best_count": len(best), "worst_count": len(worst), "days": days},
        )
        result = {"best": len(best), "worst": len(worst)}
        print(f"[weekly-creative-audit] {result}")
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[weekly-creative-audit] failed (non-fatal): {e}")
        return {}


def _run_weekly_lp_briefs() -> dict:
    """
    Sunday-only: for each active product, find the worst-CPQL campaign above
    the warning threshold and auto-create the LP brief Asana chain
    (CRO Specialist → UI/UX Designer → Developer).
    Silent when all products are healthy (no campaign above threshold).
    """
    from analysers.google_ads_audit_tasks import _is_weekly_keyword_day
    if not _is_weekly_keyword_day():
        return {}
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        from analysers.lp_tasks import create_lp_brief
        from config import CPQL_WARNING
        from datetime import date, timedelta
        from logs.activity_logger import log_activity_async

        products = ["Invoice", "Bookkeeping", "Qflavours", "General"]
        days  = 14
        today = date.today()
        since = (today - timedelta(days=days)).isoformat()
        to    = (today - timedelta(days=1)).isoformat()

        created, skipped = 0, 0
        for product in products:
            sql = f"""
                WITH hs AS (
                    SELECT lead_utm_campaign,
                           SUM(leads_total)     AS leads,
                           SUM(leads_qualified) AS sqls
                    FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
                    WHERE date BETWEEN '{since}' AND '{to}'
                      AND lead_utm_campaign IS NOT NULL
                      AND LOWER(lead_utm_campaign) LIKE '%{product.lower()}%'
                    GROUP BY lead_utm_campaign
                    HAVING SUM(leads_total) >= 5
                ),
                sp AS (
                    SELECT campaign_name, SUM(spend) AS spend
                    FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
                    WHERE date BETWEEN '{since}' AND '{to}'
                      AND LOWER(campaign_name) LIKE '%{product.lower()}%'
                    GROUP BY campaign_name
                )
                SELECT sp.campaign_name, hs.leads, hs.sqls, sp.spend,
                       SAFE_DIVIDE(sp.spend, NULLIF(hs.sqls, 0)) AS cpql
                FROM sp
                LEFT JOIN hs ON LOWER(sp.campaign_name) = LOWER(hs.lead_utm_campaign)
                WHERE SAFE_DIVIDE(sp.spend, NULLIF(hs.sqls, 0)) > {CPQL_WARNING}
                   OR hs.sqls IS NULL
                ORDER BY cpql DESC LIMIT 1
            """
            rows = list(get_client().query(sql).result())
            if not rows:
                skipped += 1
                continue

            row       = rows[0]
            camp_name = row.campaign_name or f"{product} campaign"
            cpql      = round(float(row.cpql or 0), 2)
            leads     = int(row.leads or 0)
            sqls      = int(row.sqls  or 0)
            qual_rate = round(sqls / leads * 100, 1) if leads > 0 else 0.0
            spend     = round(float(row.spend or 0), 2)
            conv_pct  = round(leads / max(spend / 3, 1) * 100, 2)

            channel = "meta"
            for ch in ("google", "snap", "tiktok", "linkedin", "bing"):
                if ch in camp_name.lower():
                    channel = ch
                    break

            try:
                create_lp_brief(
                    product=product,
                    hypothesis_slug="cpql-optimisation",
                    channel=channel,
                    hypothesis=(
                        f"A new LP variant with a clearer value proposition will reduce CPQL "
                        f"below ${CPQL_WARNING} (currently ${cpql}) for '{camp_name}'."
                    ),
                    current_cpql=cpql,
                    current_conversion_pct=conv_pct,
                    destination_url="",
                    audience="SMB accountants and business owners",
                    ocean_notes=(
                        "High Conscientiousness segment — emphasise accuracy, VAT compliance, "
                        "and time-saving. Lead with social proof (number of businesses using Qoyod)."
                    ),
                    offer_message=f"Try {product} free — no credit card required",
                    page_structure=(
                        "Hero: headline + sub-headline + CTA button above fold. "
                        "Section 2: 3 key benefits (icons). "
                        "Section 3: social proof / customer count. "
                        "Section 4: ZATCA compliance badge. "
                        "Section 5: final CTA."
                    ),
                    success_criteria=(
                        f"CPQL < ${CPQL_WARNING} over 14-day window. "
                        f"Qual rate >= {qual_rate + 10:.0f}% (current: {qual_rate}%). "
                        "Min 30 leads per variant before calling winner."
                    ),
                    risks="Low traffic risk if campaign spend < $5/day — brief may need 21-day window.",
                    window_days=days,
                )
                created += 1
                print(f"[weekly-lp-briefs] {product}: LP brief created (CPQL ${cpql})")
            except ValueError as e:
                print(f"[weekly-lp-briefs] {product}: skipped — {e}")
                skipped += 1
            except Exception as e:
                print(f"[weekly-lp-briefs] {product}: failed — {e}")

        log_activity_async(
            role="cro_analysis", action="lp_brief_auto",
            status="success",
            details={"products_briefed": created, "products_healthy": skipped},
        )
        result = {"briefs_created": created, "products_healthy": skipped}
        print(f"[weekly-lp-briefs] {result}")
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"[weekly-lp-briefs] failed (non-fatal): {e}")
        return {}


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

    # 3a. Period-over-period auto-comparator + forecaster.
    #         CLAUDE.md mandates: every nightly run includes a weekly compare
    #         (last 7d vs prior 7d) and a forward-looking forecast. Monday
    #         additionally runs the monthly compare. Read-only — findings
    #         feed downstream digests.
    _run_period_compare_weekly()
    if date.today().weekday() == 0:   # Monday in Riyadh
        _run_period_compare_monthly()
    _run_forecaster()

    # 3b. Audit tasks now run via Cowork (google-ads-audit, display-audit, wasted-spend-finder).
    audit_tasks = []

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

    # 3g. Monitor outcome follow-ups now run via Cowork (monitor-outcomes skill).

    # 3h. WEEKLY KEYWORD AUTO-FIX — Sunday Riyadh only.
    # Silently scans all ENABLED keywords + active negatives, applies the
    # rule-mandated action (pause / delete / remove-negative), and logs the
    # counts to BQ so Monday's weekly summary picks them up.
    weekly_fix_counts = _run_weekly_keyword_autofix()

    # 3i. WEEKLY CREATIVE AUDIT — Sunday Riyadh only.
    # Ranks creatives by qual rate + SQLs → Asana task for Creative Strategist.
    _run_weekly_creative_audit()

    # 3j. WEEKLY LP BRIEFS — Sunday Riyadh only.
    # For each product with a campaign above CPQL warning threshold → full
    # Asana chain (CRO Specialist → UI/UX Designer → Developer). Silent when healthy.
    _run_weekly_lp_briefs()

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
        _run_monthly_creative_report()                    # Creative sheet + Asana
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
    """Hourly health check — owned by project-coordinator.
    Runs the full connector tracker so alert_consecutive_broken() can escalate
    to an Asana task when any connector has been BROKEN for 3+ consecutive hours.
    Results written to connector_health_log (BQ). No Slack post from here —
    escalation goes to Asana (project-coordinator → growth-analyst review chain)."""
    try:
        from analysers.connector_tracker import run_all_checks
        result = run_all_checks(post_slack=False, write_bq=True)
        print(
            f"[ops-scheduler] Hourly health: {result['overall']} — "
            f"{result['healthy_count']} healthy, "
            f"{result['warning_count']} warning, "
            f"{result['broken_count']} broken"
        )
    except Exception as e:
        print(f"[ops-scheduler] Hourly health check failed: {e}")
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


def _run_slack_audit():
    """Daily 07:00 UTC (10:00 Riyadh) — approval flow audit.

    Reads #approvals history for the last 26h. For each bot-posted digest:
      - No reaction, 2–24h old  → reply in-thread once (reminder)
      - No reaction, > 24h old  → reply + create Asana escalation task
      - ✅ received              → check BQ execution log; create Asana task if gap
      - ❌ received              → log 'rejected', no further action

    Runs 2h after the nightly digest (08:00 Riyadh) so reactions have time to land.
    Added 2026-06-12.
    """
    try:
        import time as _time
        import json as _json
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
        from logs.activity_logger import log_activity_async

        slack = WebClient(token=SLACK_BOT_TOKEN)
        now_ts = _time.time()
        window = 26 * 3600  # 26h lookback

        # ── Step 1: fetch recent digest messages ─────────────────────────────
        history = slack.conversations_history(
            channel=SLACK_CHANNEL_APPROVAL,
            oldest=str(now_ts - window),
            limit=50,
        )
        messages = history.get("messages", [])
        digests = [
            m for m in messages
            if m.get("bot_id") and "ACTIONS" in m.get("text", "")
        ]
        print(f"[slack-audit] {len(digests)} digest(s) found in last 26h")

        reminders_sent = 0
        escalations = 0
        execution_gaps = 0

        for msg in digests:
            ts      = msg["ts"]
            age_h   = (now_ts - float(ts)) / 3600
            text    = msg.get("text", "")[:200]
            reacts  = {r["name"] for r in msg.get("reactions", [])}

            if "white_check_mark" in reacts:
                # ── Check execution in BQ ─────────────────────────────────────
                try:
                    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
                    bq = get_client()
                    sql = f"""
                        SELECT action, status, ts AS log_ts
                        FROM `{PROJECT_ID}.{DATASET}.agent_activity_log`
                        WHERE action IN (
                            'scale_campaign_executed', 'pause_campaign_executed',
                            'pause_ad_executed', 'budget_redeployment_executed',
                            'action_approved_via_slack'
                        )
                        AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), ts, HOUR) <= 4
                        ORDER BY ts DESC LIMIT 20
                    """
                    rows = list(bq.query(sql).result())
                    approved = any(r.action == "action_approved_via_slack" for r in rows)
                    executed = any("_executed" in r.action for r in rows)
                    if approved and not executed:
                        # Gap: approved but no execution entry within 4h
                        from executors.asana import create_task
                        create_task(
                            title=f"APPROVAL NOT EXECUTED — {date.today().isoformat()}",
                            description=(
                                f"An action was approved in #approvals but no execution "
                                f"was logged in BQ.\n\nApproval timestamp: {ts}\n"
                                f"Digest summary: {text}\n\n"
                                "WHAT TO CHECK:\n"
                                "1. Railway logs for the operational scheduler around approval time\n"
                                "2. agent_activity_log for any errors from the executor\n"
                                "3. Was the approval reaction added after the 30-min timeout?\n\n"
                                f"Created: {date.today().isoformat()} | Due: {date.today().isoformat()} | "
                                "Priority: High | Type: System Health | Channel: all | "
                                "Asset level: campaign | Action: investigate → [Project Coordinator]"
                            ),
                            project_key="optimization",
                            task_type="System Health",
                            channel="all",
                            asset_level="campaign",
                            action="investigate",
                            log_role="project_coordinator",
                        )
                        execution_gaps += 1
                        print(f"[slack-audit] Execution gap found for digest ts={ts}")
                except Exception as bq_err:
                    print(f"[slack-audit] BQ execution check failed (non-fatal): {bq_err}")
                continue

            if "x" in reacts:
                print(f"[slack-audit] Digest ts={ts} rejected — no action")
                continue

            # No reaction yet
            if age_h < 2:
                continue  # too early

            # Check if we already replied
            try:
                replies = slack.conversations_replies(
                    channel=SLACK_CHANNEL_APPROVAL, ts=ts
                )
                already_reminded = any(
                    "No approval received yet" in r.get("text", "")
                    for r in replies.get("messages", [])[1:]  # skip parent
                )
            except SlackApiError:
                already_reminded = False

            if already_reminded:
                continue

            reminder = (
                "No approval received yet on this digest. "
                "Please react with ✅ to approve all scale/pause actions, "
                "or ❌ to skip. Review-only items (Asana tasks) don't need a reaction."
            )
            try:
                slack.chat_postMessage(
                    channel=SLACK_CHANNEL_APPROVAL,
                    thread_ts=ts,
                    text=reminder,
                )
                reminders_sent += 1
                print(f"[slack-audit] Reminder posted for digest ts={ts} (age {age_h:.1f}h)")
            except SlackApiError as e:
                print(f"[slack-audit] Failed to post reminder: {e}")

            if age_h > 24:
                # Escalate to Asana as well
                try:
                    from executors.asana import create_task
                    create_task(
                        title=f"#approvals digest unanswered > 24h — {date.today().isoformat()}",
                        description=(
                            f"A nightly digest in #approvals has had no ✅ or ❌ reaction "
                            f"for over 24 hours.\n\nDigest timestamp: {ts}\n"
                            f"Digest summary: {text}\n\n"
                            f"Created: {date.today().isoformat()} | Due: {date.today().isoformat()} | "
                            "Priority: High | Type: System Health | Channel: all | "
                            "Asset level: campaign | Action: investigate → [Project Coordinator]"
                        ),
                        project_key="optimization",
                        task_type="System Health",
                        channel="all",
                        asset_level="campaign",
                        action="investigate",
                        log_role="project_coordinator",
                    )
                    escalations += 1
                except Exception as e:
                    print(f"[slack-audit] Escalation task creation failed (non-fatal): {e}")

        log_activity_async(
            role="project_coordinator",
            action="slack_audit_complete",
            status="success",
            details={
                "digests_checked": len(digests),
                "reminders_sent": reminders_sent,
                "escalations": escalations,
                "execution_gaps": execution_gaps,
            },
        )
        print(f"[slack-audit] Done — {len(digests)} checked, "
              f"{reminders_sent} reminded, {escalations} escalated, "
              f"{execution_gaps} execution gap(s)")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ops-scheduler] Slack audit failed (non-fatal): {e}")


def _run_monthly_creative_report():
    """1st of month, 05:00 UTC (08:00 Riyadh) — winning creative analysis.

    Queries v_ad_performance for the last 30 days, classifies ads as
    winner / optimise / underperformer, writes a Google Sheet with one tab
    per channel, and creates an Asana task for the design team.
    Non-fatal — never blocks the monthly cadence.
    Added 2026-06-12.
    """
    try:
        import subprocess
        r = subprocess.run(
            ["python", "scripts/monthly_creative_report.py"],
            capture_output=True, timeout=300,
            cwd=os.path.dirname(__file__),
        )
        print(f"[ops-scheduler] Monthly creative report exit={r.returncode}")
        if r.stdout:
            tail = r.stdout.decode("utf-8", errors="replace").splitlines()[-20:]
            for line in tail:
                print(f"[monthly-creative] {line}")
        if r.returncode != 0 and r.stderr:
            tail = r.stderr.decode("utf-8", errors="replace").splitlines()[-10:]
            for line in tail:
                print(f"[monthly-creative][err] {line}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ops-scheduler] Monthly creative report failed (non-fatal): {e}")


def run():
    schedule.every().day.at("05:00").do(_nightly)   # 08:00 Riyadh = 05:00 UTC
    # Second BQ refresh 12h later — picks up workflow re-classifications and
    # late-arriving leads from the day. Doesn't run the full _nightly cadence,
    # just refreshes BQ data so dashboards reflect current state.
    # Added 2026-05-15 to halve attribution lag (was 24h, now 12h).
    schedule.every().day.at("17:00").do(_refresh_bigquery)  # 20:00 Riyadh = 17:00 UTC

    # ── Slack approval audit — 10:00 Riyadh = 07:00 UTC ──────────────────────
    # Checks #approvals for unanswered digests (2h+ old), posts in-thread
    # reminders, and flags approved-but-unexecuted actions to Asana.
    # Runs 2h after the nightly digest so reactions have time to land.
    # Added 2026-06-12.
    schedule.every().day.at("07:00").do(_run_slack_audit)

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
    print("  Sheet    05:00 Riyadh (02:00 UTC)  — append actions to master sheet")
    print("  Spend    09/11/13/15 Riyadh (06/08/10/12 UTC) — workday spend refresh")
    print("  Mirror   09/15/22 Riyadh (06/12/19 UTC) — HubSpot full mirror (3×/day)")
    print("  Audit    10:00 Riyadh (07:00 UTC)  — #approvals Slack audit + reminders")
    print("  Self-test 07:00 Riyadh (04:00 UTC) — QA gate check verification")
    print("  Self-heal 09:30 Riyadh (06:30 UTC) — detect+fix stale views, failed collectors, 500s")  # noqa
    print("  Watchdog every ~4h — never let BQ go stale, auto-resync (4h threshold)")
    print("  Weekly   added Mon mornings")
    print("  Monthly  added on 1st of month (+ creative report Google Sheet)")
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
