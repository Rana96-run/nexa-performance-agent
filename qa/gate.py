"""QA Gate — the locked verification layer.

Auto-retry-once-then-hard-block, per the operator's chosen policy.

On hard-block:
  - raise QAGateError (caller's outbound call fails fast)
  - alert to Slack #health
  - log to BQ table `qa_gate_events`
"""
from __future__ import annotations
import os
import time
import logging
import traceback
from datetime import datetime, timezone

from .errors import QAGateError, QACheckResult
from . import checks

log = logging.getLogger("qa.gate")

RETRY_DELAY_S = 30          # wait between attempt 1 and attempt 2
HEALTH_CHANNEL = os.getenv("SLACK_CHANNEL_HEALTH", "#nexa-health")


def _disabled() -> bool:
    return os.getenv("QA_GATE_DISABLED", "").strip() in ("1", "true", "yes")


def _alert_health(surface: str, failures: list[QACheckResult]):
    """Post a one-line ping to Slack #health. Detail lives in qa_gate_events
    BQ table + dashboard. Best-effort, never raises."""
    try:
        from notifications.slack_ping import post_ping
        # Headline = surface + first failed check name; everything else is in BQ
        first = failures[0].name if failures else "unknown"
        n = len(failures)
        headline = (
            f"QA gate blocked {surface} ({n} check failure{'s' if n != 1 else ''}, "
            f"first: {first})"
        )
        post_ping(channel=HEALTH_CHANNEL, status="alert", headline=headline)
    except Exception:
        log.exception("qa.gate: failed to post health ping")


def _log_event(surface: str, passed: bool, results: list[QACheckResult]):
    """Append one row to BQ qa_gate_events (auto-creates on first write)."""
    try:
        from collectors.bq_writer import upsert_rows
        now = datetime.now(timezone.utc).isoformat()
        rows = [{
            "event_id":  f"{surface}-{int(time.time()*1000)}",
            "ts":        now,
            "surface":   surface,
            "passed":    passed,
            "check_name":   r.name,
            "check_passed": r.passed,
            "severity":     r.severity,
            "detail":       r.detail,
        } for r in results]
        # best-effort — do not let logging failures cascade
        upsert_rows("qa_gate_events", rows, key_fields=["event_id", "check_name"])
    except Exception:
        log.exception("qa.gate: failed to log event")


class QAGate:
    """Stateful gate — orchestrates checks with retry-then-block."""

    def _run_attempt(self, runners: list) -> list[QACheckResult]:
        results: list[QACheckResult] = []
        for fn, args, kwargs in runners:
            try:
                results.append(fn(*args, **kwargs))
            except Exception as e:
                results.append(QACheckResult(
                    name=getattr(fn, "__name__", "unknown"),
                    passed=False, severity="warn",
                    detail=f"check raised: {e!s}",
                    metrics={"trace": traceback.format_exc(limit=2)},
                ))
        return results

    def _verify(self, surface: str, runners: list) -> list[QACheckResult]:
        if _disabled():
            log.warning("qa.gate disabled via QA_GATE_DISABLED")
            return []

        # Attempt 1
        results = self._run_attempt(runners)
        blockers = [r for r in results if not r.passed and r.severity == "block"]
        if not blockers:
            _log_event(surface, passed=True, results=results)
            return results

        # Auto-retry once after transient delay (clears BQ staleness, rate limits)
        log.warning("qa.gate %s attempt 1 had %d blocker(s) — retrying in %ds",
                    surface, len(blockers), RETRY_DELAY_S)
        # Bypass cache for retry — get fresh facts
        checks._CACHE.clear()
        time.sleep(RETRY_DELAY_S)
        results = self._run_attempt(runners)
        blockers = [r for r in results if not r.passed and r.severity == "block"]

        if blockers:
            _log_event(surface, passed=False, results=results)
            _alert_health(surface, blockers)
            raise QAGateError(
                message=f"{len(blockers)} blocker(s) after retry",
                failures=blockers,
                surface=surface,
            )

        _log_event(surface, passed=True, results=results)
        return results

    # ── Per-surface entry points ──────────────────────────────────────────

    def verify_slack(self, text: str, channel: str = "") -> list[QACheckResult]:
        return self._verify("slack", [
            (checks.check_freshness,            (),                        {}),
            (checks.check_slack_format,         (text, channel),           {}),
            (checks.check_numeric_claims,       (text,),                   {}),
            (checks.check_multi_account_presence, (),                      {}),
        ])

    def verify_asana(self, task: dict) -> list[QACheckResult]:
        return self._verify("asana", [
            (checks.check_freshness,         (),       {}),
            (checks.check_asana_footer,      (task,),  {}),
            (checks.check_table_format,      (task,),  {}),   # structural + content check on all pipe tables
            (checks.check_pause_precedence,  (task,),  {}),   # blocks campaign-pause if ad-level cleanup pending
            (checks.check_numeric_claims,
             (task.get("notes", "") or task.get("name", ""),), {}),
        ])

    def verify_bq_write(self, table: str, rows: list[dict],
                        key_fields: list[str]) -> list[QACheckResult]:
        return self._verify("bq", [
            (checks.check_bq_write,  (table, rows, key_fields), {}),
        ])

    def dashboard_status(self) -> tuple[str, list[QACheckResult]]:
        """Returns ('green'|'yellow'|'red', results) for dashboard banner.
        Read-only — does NOT raise, does NOT retry, no alerts."""
        if _disabled():
            return "green", []
        results = self._run_attempt([
            (checks.check_freshness,              (), {}),
            (checks.check_multi_account_presence, (), {}),
            (checks.check_bq_hubspot_reconcile,   (), {}),  # settled window
            (checks.check_live_drift,             (), {}),  # current-week live drift
            (checks.check_deals_full_reconcile,   (), {}),  # counts + amounts
        ])
        blockers = [r for r in results if not r.passed and r.severity == "block"]
        warns    = [r for r in results if not r.passed and r.severity == "warn"]
        status = "red" if blockers else ("yellow" if warns else "green")
        return status, results


gate = QAGate()
