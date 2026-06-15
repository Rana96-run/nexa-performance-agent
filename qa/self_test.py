"""QA gate self-test layer — fires synthetic fixtures through every check.

Runs daily after _nightly() to confirm each gate check still works as designed.
Catches the "silently broken check" failure mode — e.g. a refactor changes a
field name and a check starts always-passing, becoming security theater.

For each check, fixtures define:
  - 1 known-good input (should pass)
  - 1 known-bad input (should fail with expected reason)

If a check returns the WRONG outcome for either fixture, the test layer logs
to stdout and pings #nexa-health. (qa_gate_events BQ table dropped 2026-06-16
— write-only sink with 0 decision-logic reads, removed in dataset consolidation.)
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

from .checks import (
    check_slack_format, check_asana_footer, check_bq_write,
    check_numeric_claims, check_freshness, check_multi_account_presence,
    check_deals_full_reconcile, check_live_drift,
)
from .errors import QACheckResult

# Each fixture: (test_name, check_fn, args, expected_pass, expected_reason_substr)
FIXTURES = [
    # ── Slack format ─────────────────────────────────────────────────────
    ("slack_format_good",
     check_slack_format,
     ("Daily report 2026-05-20 to 2026-05-20 — https://hex.tech/qoyod (Impression Share 45%)", "daily"),
     True, ""),
    ("slack_format_bad_abbrev",
     check_slack_format,
     ("Daily report — IS at 45% lost", "daily"),
     False, "forbidden abbreviation"),
    ("slack_format_bad_no_url",
     check_slack_format,
     ("Daily report 2026-05-20 to 2026-05-20", "daily"),
     False, "missing dashboard URL"),

    # ── Asana footer ─────────────────────────────────────────────────────
    ("asana_footer_good",
     check_asana_footer,
     ({"notes": "Pause campaign.\nCreated: 2026-05-20\nDue: 2026-05-21\n"
                "Priority: High\nType: Recommendation\nChannel: meta"},),
     True, ""),
    ("asana_footer_bad",
     check_asana_footer,
     ({"notes": "Pause campaign — no footer"},),
     False, "footer missing fields"),

    # ── BQ write sanity ──────────────────────────────────────────────────
    ("bq_write_good",
     check_bq_write,
     ("campaigns_daily",
      [{"date": "2026-05-20", "channel": "meta", "campaign_id": "A", "spend": 10}],
      ["date", "channel", "campaign_id"]),
     True, ""),
    ("bq_write_bad_dupes",
     check_bq_write,
     ("campaigns_daily",
      [{"date": "2026-05-20", "channel": "meta", "campaign_id": "A", "spend": 10},
       {"date": "2026-05-20", "channel": "meta", "campaign_id": "A", "spend": 12}],
      ["date", "channel", "campaign_id"]),
     False, "internal duplicate rows"),
    ("bq_write_partition_rebuild_allowed",
     check_bq_write,
     ("hubspot_leads_module_daily",
      [{"date": "2026-05-20", "qoyod_source": "Google Ads", "leads_total": 1},
       {"date": "2026-05-20", "qoyod_source": "Meta Ads",   "leads_total": 1}],
      ["date"]),   # ["date"] = partition rebuild sentinel — dupes OK
     True, ""),

    # ── Numeric claims (heuristic — warn only, should always pass struct) ─
    ("numeric_claims_no_dollars",
     check_numeric_claims,
     ("No dollar figures in this text.",),
     True, "no dollar figures"),

    # ── Live drift — current-week BQ vs HS, fills the gap reconciler misses ─
    ("live_drift_current_week",
     check_live_drift,
     (),
     True, ""),

    # ── Deals reconcile — live BQ↔HS check, fixtures use real data ───────
    # No "bad" fixture: this check IS the production data. Pass = drift
    # under thresholds (1% counts / 2% amounts). Fail = real production
    # drift that needs attention. Self-test row will mirror gate output.
    ("deals_full_reconcile_live",
     check_deals_full_reconcile,
     (),
     True, ""),
]


def run_self_test(post_to_bq: bool = True) -> dict:
    """Run all fixtures. Returns summary + writes results to qa_gate_events."""
    now_iso = datetime.now(timezone.utc).isoformat()
    results = []
    broken_checks = []

    for name, fn, args, expected_pass, expected_substr in FIXTURES:
        try:
            r: QACheckResult = fn(*args)
            actual_pass = r.passed
            actual_detail = r.detail or ""
            outcome_ok = (actual_pass == expected_pass)
            reason_ok = (not expected_substr) or (expected_substr.lower() in actual_detail.lower())
            test_passed = outcome_ok and reason_ok
        except Exception as e:
            test_passed = False
            actual_pass = None
            actual_detail = f"check raised: {e!s}"
            outcome_ok = False
            reason_ok = False

        results.append({
            "test_name":      name,
            "check":          fn.__name__,
            "expected_pass":  expected_pass,
            "actual_pass":    actual_pass,
            "outcome_ok":     outcome_ok,
            "reason_ok":      reason_ok,
            "test_passed":    test_passed,
            "detail":         actual_detail[:200],
        })
        if not test_passed:
            broken_checks.append(name)

    # qa_gate_events BQ table dropped 2026-06-16 (write-only sink, 0 decision reads).
    # Self-test results are still surfaced via Slack ping below on failures.
    if post_to_bq:
        # Log to stdout only — BQ table no longer exists
        for r in results:
            if not r["test_passed"]:
                print(f"[qa.self_test] FAIL {r['check']}::{r['test_name']} — {r['detail'][:200]}")

    # Slack ping only on real failures
    if broken_checks:
        try:
            from notifications.slack_ping import post_ping
            post_ping(
                channel=os.getenv("SLACK_CHANNEL_HEALTH", "#nexa-health"),
                status="alert",
                headline=f"QA gate self-test failed: {len(broken_checks)} check(s) broken — {', '.join(broken_checks[:3])}",
                link=os.getenv("ACTIVITY_SHORT_URL")
                     or "https://nexa-web-production-6a6b.up.railway.app/activity",
            )
        except Exception as e:
            print(f"[qa.self_test] Slack ping failed: {e}")

    return {
        "total":         len(results),
        "passed":        sum(1 for r in results if r["test_passed"]),
        "broken_checks": broken_checks,
        "results":       results,
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, ".")
    from dotenv import load_dotenv; load_dotenv()
    r = run_self_test(post_to_bq=False)
    print(f"\nSelf-test: {r['passed']}/{r['total']} fixtures passed")
    if r["broken_checks"]:
        print(f"BROKEN CHECKS: {r['broken_checks']}")
        for fixture in r["results"]:
            if not fixture["test_passed"]:
                print(f"  ✗ {fixture['test_name']}: expected={fixture['expected_pass']}, "
                      f"got={fixture['actual_pass']}, detail={fixture['detail']}")
    else:
        print("All gate checks behaving correctly.")
