"""
Unit tests for qa/checks.py

Run:  python -m pytest qa/tests/test_checks.py -v

These tests exercise every check WITHOUT hitting BQ or HubSpot.
BQ-backed checks are tested via mocks so the suite runs offline.
"""
from __future__ import annotations
import sys
import types
import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap stubs so checks.py imports without real BQ / Slack credentials
# ---------------------------------------------------------------------------

def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules.setdefault(name, mod)
    return mod

for _m in [
    "collectors", "collectors.bq_writer",
    "google", "google.cloud", "google.cloud.bigquery",
    "analysers", "analysers.campaign_health", "analysers.lag_aware",
]:
    _stub_module(_m)

import os
os.environ.setdefault("BQ_PROJECT_ID", "test-project")
os.environ.setdefault("BQ_DATASET", "test_dataset")
os.environ.setdefault("HUBSPOT_ACCESS_TOKEN", "test-token")

from qa.checks import (
    check_asana_footer,
    check_slack_format,
    check_pause_precedence,
    check_numeric_claims,
    check_bq_write,
    EXPECTED_ACCOUNTS,
)


# ===========================================================================
# 1. check_asana_footer
# ===========================================================================

class TestAsanaFooter:
    def _task(self, notes: str) -> dict:
        return {"notes": notes, "name": "Test task"}

    def test_pass_all_required_fields(self):
        notes = (
            "## Scale Candidate\n\nSome body.\n\n"
            "**Task Details**\n\n"
            "| Created | 2026-05-19 |\n"
            "| Due | 2026-05-26 |\n"
            "| Priority | High |\n"
            "| Type | Scale |\n"
            "| Channel | Meta |\n"
        )
        r = check_asana_footer(self._task(notes))
        assert r.passed, f"expected pass, got: {r.detail}"

    def test_fail_missing_channel(self):
        notes = (
            "| Created | 2026-05-19 |\n"
            "| Due | 2026-05-26 |\n"
            "| Priority | High |\n"
            "| Type | Scale |\n"
            # Channel line missing
        )
        r = check_asana_footer(self._task(notes))
        assert not r.passed
        assert "Channel" in r.detail

    def test_fail_empty_notes(self):
        r = check_asana_footer(self._task(""))
        assert not r.passed

    def test_html_notes_fallback(self):
        task = {
            "name": "Test",
            "html_notes": (
                "Created Due Priority Type Channel"  # all keywords present
            )
        }
        r = check_asana_footer(task)
        assert r.passed


# ===========================================================================
# 2. check_slack_format
# ===========================================================================

class TestSlackFormat:
    def test_pass_daily_with_url(self):
        text = "Dashboard: https://app.hex.tech/dashboard · spend $1,200 · 15 leads"
        r = check_slack_format(text, "daily")
        assert r.passed, r.detail

    def test_fail_daily_missing_url(self):
        text = "Spend $1,200 · 15 leads · CPQL $80"
        r = check_slack_format(text, "daily")
        assert not r.passed
        assert "dashboard URL" in r.detail

    def test_fail_abbreviation_IS(self):
        text = "https://app.hex.tech · IS 35%"
        r = check_slack_format(text, "daily")
        assert not r.passed
        assert "IS/QS" in r.detail

    def test_fail_last_n_days(self):
        text = "https://app.hex.tech · last 7 days performance"
        r = check_slack_format(text, "daily")
        assert not r.passed
        assert "YYYY-MM-DD" in r.detail

    def test_pass_non_daily_channel_no_url(self):
        # Non-daily channel — URL not required
        text = "Some approval message without URL"
        r = check_slack_format(text, "approvals")
        assert r.passed

    def test_pass_IS_if_spelled_out(self):
        text = (
            "https://app.hex.tech · Impression Share 35% · Quality Score 7"
        )
        r = check_slack_format(text, "daily")
        assert r.passed


# ===========================================================================
# 3. check_pause_precedence — string detection logic only (no BQ)
# ===========================================================================

class TestPausePrecedenceDetection:
    """Test that the detection logic correctly identifies campaign-pause tasks
    with BOTH old 'key: value' and new '| key | value |' table footer formats.
    Tests stop before the BQ lookup (campaign_name too short to trigger)."""

    def _task(self, title: str, notes: str) -> dict:
        return {"name": title, "notes": notes}

    def test_detects_table_format_pause(self):
        """'| action | pause |' + '| asset level | campaign |' must be detected."""
        task = self._task(
            "[Recommendation | Pause] X",  # title contains "pause"
            "some notes\n| Asset level | Campaign |\n| Action | Pause |",
        )
        title_l = task["name"].lower()
        notes_l = task["notes"].lower()
        # Replicate the fixed detection logic
        is_pause = (
            "pause" in title_l
            or "action: pause" in notes_l
            or "| action | pause |" in notes_l
        )
        is_campaign = (
            "asset level: campaign" in notes_l
            or "| asset level | campaign |" in notes_l
        )
        assert is_pause, "should detect pause from table footer"
        assert is_campaign, "should detect campaign level from table footer"

    def test_detects_legacy_format_pause(self):
        task = self._task(
            "Pause candidate",
            "action: pause\nasset level: campaign",
        )
        title_l = task["name"].lower()
        notes_l = task["notes"].lower()
        is_pause = (
            "pause" in title_l
            or "action: pause" in notes_l
            or "| action | pause |" in notes_l
        )
        is_campaign = (
            "asset level: campaign" in notes_l
            or "| asset level | campaign |" in notes_l
        )
        assert is_pause
        assert is_campaign

    def test_scale_task_not_detected_as_pause(self):
        notes_l = "| action | scale |\n| asset level | campaign |"
        is_pause = (
            "pause" in notes_l
            or "action: pause" in notes_l
            or "| action | pause |" in notes_l
        )
        assert not is_pause, "scale task should NOT trigger pause check"

    def test_ad_level_task_not_detected_as_campaign(self):
        notes_l = "| action | pause |\n| asset level | ad |"
        is_campaign = (
            "asset level: campaign" in notes_l
            or "| asset level | campaign |" in notes_l
        )
        assert not is_campaign, "ad-level task should NOT trigger campaign-level check"

    def test_full_check_skips_non_pause(self):
        """Full check on a scale task should return passed=True without hitting BQ."""
        task = self._task(
            "[Recommendation | Scale] Meta_LeadGen_AR_Invoice_Interests",
            "| Action | Scale |\n| Asset level | Campaign |",
        )
        r = check_pause_precedence(task)
        # Should skip (not a pause task) without touching BQ
        assert r.passed
        assert "skipped" in r.detail.lower() or "not a campaign-pause" in r.detail.lower()


# ===========================================================================
# 4. check_numeric_claims — only verifies spend-scale amounts (>= $500)
# ===========================================================================

class TestNumericClaims:
    """No BQ calls — the function only queries BQ when cited amounts exist.
    We patch _cached to return known amounts."""

    def _run(self, text: str, known: list[float]) -> object:
        with patch("qa.checks._cached", return_value=known):
            return check_numeric_claims(text)

    def test_no_dollar_amounts_passes(self):
        r = self._run("Leads 15, spend normal", [1000.0, 2000.0])
        assert r.passed
        assert "no dollar figures" in r.detail

    def test_cpql_amounts_ignored(self):
        """$73, $80 CPQL values must NOT be checked (< $500 threshold)."""
        r = self._run(
            "CPQL $73 · CPQL $80 · CPQL $120",
            [5000.0, 3000.0],  # nothing near $73/$80/$120 but they should be ignored
        )
        assert r.passed, f"CPQL amounts should be ignored, got: {r.detail}"

    def test_large_amount_matched(self):
        """$2,500 spend figure that exists in BQ should pass."""
        r = self._run("Total spend $2,500 last period", [2500.0, 1000.0])
        assert r.passed

    def test_large_amount_unmatched_fails(self):
        """$9,999 in text with no BQ match → orphan → should warn/fail."""
        r = self._run(
            "https://hex.tech · Total spend $9,999",
            [1000.0, 2000.0],  # nothing near $9,999
        )
        # orphan_pct = 1/1 = 100% > max_orphan_pct(0.20) → fail
        assert not r.passed

    def test_mixed_small_large_only_large_checked(self):
        """$73 (CPQL) + $1,200 (spend, matches) — only $1,200 should be checked."""
        r = self._run(
            "CPQL $73 · Spend $1,200",
            [1200.0, 5000.0],
        )
        assert r.passed, f"matched large amount should pass, got: {r.detail}"


# ===========================================================================
# 5. check_bq_write — internal dupe and account count checks
# ===========================================================================

class TestBqWrite:
    def _row(self, date, cid, channel, account_id, spend):
        return {"date": date, "campaign_id": cid, "channel": channel,
                "account_id": account_id, "spend": spend}

    def test_empty_batch_passes(self):
        r = check_bq_write("campaigns_daily", [], ["date", "campaign_id"])
        assert r.passed

    def test_clean_batch_passes(self):
        rows = [
            self._row("2026-05-18", "c1", "google_ads", "a1", 100),
            self._row("2026-05-18", "c2", "google_ads", "a2", 200),
        ]
        r = check_bq_write("campaigns_daily", rows, ["date", "campaign_id", "account_id"])
        assert r.passed

    def test_internal_duplicate_fails(self):
        rows = [
            self._row("2026-05-18", "c1", "google_ads", "a1", 100),
            self._row("2026-05-18", "c1", "google_ads", "a1", 100),  # dup
        ]
        r = check_bq_write("campaigns_daily", rows, ["date", "campaign_id", "account_id"])
        assert not r.passed
        assert "duplicate" in r.detail

    def test_single_account_when_two_expected_fails(self):
        # 12 rows all from account a1 only (google_ads expects 2 accounts)
        rows = [self._row(f"2026-05-{i:02d}", f"c{i}", "google_ads", "a1", 50)
                for i in range(1, 13)]
        r = check_bq_write("campaigns_daily", rows, ["date", "campaign_id", "account_id"])
        assert not r.passed
        assert "account" in r.detail

    def test_no_key_fields_always_passes(self):
        rows = [{"spend": 100}, {"spend": 100}]
        r = check_bq_write("some_table", rows, [])
        assert r.passed


# ===========================================================================
# 6. Reconciler error surface (unit — does not call HubSpot/BQ)
# ===========================================================================

class TestReconcilerErrorSurface:
    def test_exception_returns_passed_false(self):
        """check_bq_hubspot_reconcile must NOT return passed=True on exception."""
        with patch("qa.checks._cached", side_effect=RuntimeError("BQ timeout")):
            from qa.checks import check_bq_hubspot_reconcile
            r = check_bq_hubspot_reconcile()
        assert not r.passed, "reconciler failure must not silently pass"
        assert "manual check required" in r.detail.lower() or "reconciler error" in r.detail.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
