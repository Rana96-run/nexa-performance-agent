"""
Smoke tests for the Nexa Performance Agent.

Two modes:

  python -m tests.test_smoke              # fast: imports + math + config (no API calls)
  python -m tests.test_smoke --live       # also hits each BQ collector with days=1

The fast mode is dependency-free and safe to run every commit / on Replit
boot. It catches:
  - broken imports (syntax errors, missing deps, renamed modules)
  - drift in config thresholds
  - currency math regressions
  - missing critical env vars

The --live mode also catches "the API broke" for each channel by pulling a
single day's data. Slower (~1–2 min) and consumes API quota, so it's opt-in.

Pytest-compatible: each `test_*` function uses bare asserts and takes no
fixtures. If you later `pip install pytest`, `pytest tests/` will just work.
"""
from __future__ import annotations

import importlib
import os
import sys
import traceback
from typing import Callable


# ---------------------------------------------------------------------------
# Fast tests — no network, no BQ, no auth. Safe everywhere.
# ---------------------------------------------------------------------------

def test_config_has_usd_thresholds():
    """All KPI thresholds and the SAR peg must live in config.py as numbers."""
    import config
    assert isinstance(config.USD_SAR_PEG, (int, float)) and config.USD_SAR_PEG > 0
    # SAR peg must be the official 3.75 (Saudi Central Bank). If this ever
    # legitimately changes, update config.py and this test together.
    assert config.USD_SAR_PEG == 3.75, f"USD_SAR_PEG drifted: {config.USD_SAR_PEG}"

    # CPL bands must be ordered: scale < acceptable < warning
    assert config.CPL_SCALE < config.CPL_ACCEPTABLE < config.CPL_WARNING
    assert config.CPQL_SCALE < config.CPQL_ACCEPTABLE < config.CPQL_WARNING

    # Targets are sane
    assert 0 < config.QUAL_RATE_TARGET < 1
    assert config.ROAS_TARGET > 0


def test_currency_math():
    """to_usd() must use the centralised peg and round-trip correctly."""
    from collectors.currency import to_usd, normalize_currency, PEG_RATES_TO_USD
    import config

    # SAR -> USD is the only one we hard-pin (peg is policy, not market).
    assert to_usd(3.75, "SAR") == 1.0, "1 USD must equal 3.75 SAR exactly"
    assert to_usd(375, "SAR") == 100.0
    assert to_usd(100, "USD") == 100.0
    assert to_usd(0, "SAR") == 0.0
    assert to_usd(None, "SAR") == 0.0

    # currency.py must read the peg from config.py — not hardcode it.
    assert PEG_RATES_TO_USD["SAR"] == 1 / config.USD_SAR_PEG, \
        "currency.py SAR rate is not derived from config.USD_SAR_PEG"

    # Case-insensitive + default behaviour
    assert normalize_currency(None) == "SAR"
    assert normalize_currency("usd") == "USD"


def test_all_collectors_import():
    """Every collector module must import cleanly. Catches syntax/import drift."""
    modules = [
        "collectors.bq_writer",
        "collectors.currency",
        "collectors.from_bq",        # BQ reader — single source of truth for campaign data
        # BQ writers (populate the data layer 4×/day)
        "collectors.google_ads_bq",
        "collectors.meta_bq",
        "collectors.snap_bq",
        "collectors.tiktok_bq",
        "collectors.linkedin_bq",
        "collectors.microsoft_ads_bq",
        "collectors.hubspot_leads_bq",
        "collectors.hubspot_deals_bq",
        "collectors.meta_organic_bq",
        "collectors.youtube_bq",
        # Live API modules (only kept for grain BQ doesn't have, plus executors/OAuth)
        "collectors.google_ads",     # keyword grain + pause executors
        "collectors.meta",           # ad grain + pause executors
        "collectors.microsoft_ads",  # OAuth bootstrap only
        "collectors.hubspot",
        "collectors.views",
        # Notification + logging spine
        "notifications.notify",
        "notifications.slack",
        "logs.logger",
    ]
    failures = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except Exception as e:
            failures.append((mod, str(e)))
    assert not failures, "Failed imports:\n" + "\n".join(
        f"  - {m}: {e}" for m, e in failures
    )


def test_entry_points_import():
    """Schedulers + main must import without side effects breaking."""
    for mod in ("main", "reporting_scheduler", "operational_scheduler", "slack_listener"):
        importlib.import_module(mod)


def test_logger_setup_idempotent():
    """setup_global_logging() must be safe to call multiple times."""
    from logs.logger import setup_global_logging
    log1 = setup_global_logging("smoke-test")
    log2 = setup_global_logging("smoke-test")
    assert log1 is log2


def test_critical_env_vars_present():
    """Soft check: warn (don't fail) if optional creds are missing."""
    from dotenv import load_dotenv
    load_dotenv(override=True)
    must_have = ["BQ_PROJECT_ID", "ANTHROPIC_API_KEY"]
    missing = [v for v in must_have if not os.getenv(v)]
    assert not missing, f"Critical env vars missing: {missing}"


def test_bq_view_sql_uses_config_thresholds():
    """The campaign_performance view SQL must inject thresholds from config."""
    from collectors import bq_writer
    import config
    sql = bq_writer.CAMPAIGN_PERFORMANCE_VIEW_SQL
    # Threshold values from config must appear literally in the rendered SQL
    for v in (config.CPL_SCALE, config.CPL_ACCEPTABLE, config.CPL_WARNING,
              config.CPQL_SCALE, config.CPQL_ACCEPTABLE, config.CPQL_WARNING):
        assert str(v) in sql, f"View SQL missing threshold {v}"


# ---------------------------------------------------------------------------
# Live tests — opt-in via --live. Each runs the BQ collector with days=1
# and only asserts that the call returns without raising. No row-count
# assertions, since some channels may legitimately have 0 rows for a given
# day (e.g. paused account).
# ---------------------------------------------------------------------------

def _live(name: str, fn: Callable):
    print(f"  [live] {name} ... ", end="", flush=True)
    try:
        n = fn(days=1)
        print(f"OK ({n} rows)")
        return True, n
    except Exception as e:
        print(f"FAIL: {e}")
        traceback.print_exc()
        return False, str(e)


def test_live_collectors():
    """Hit each BQ collector with days=1. Skipped unless --live is passed."""
    if "--live" not in sys.argv:
        print("  (skipped — pass --live to enable)")
        return
    from collectors import (
        google_ads_bq, meta_bq, snap_bq, tiktok_bq,
        linkedin_bq, microsoft_ads_bq,
        hubspot_leads_bq, hubspot_deals_bq,
    )
    targets = [
        ("google_ads",     google_ads_bq.collect_and_write),
        ("meta",           meta_bq.collect_and_write),
        ("snapchat",       snap_bq.collect_and_write),
        ("tiktok",         tiktok_bq.collect_and_write),
        ("linkedin",       linkedin_bq.collect_and_write),
        ("microsoft_ads",  microsoft_ads_bq.collect_and_write),
        ("hubspot_leads",  hubspot_leads_bq.collect_and_write),
        ("hubspot_deals",  hubspot_deals_bq.collect_and_write),
    ]
    failed = [name for name, fn in targets if not _live(name, fn)[0]]
    assert not failed, f"Live collectors failed: {failed}"


# ---------------------------------------------------------------------------
# Standalone runner — prints results table.
# ---------------------------------------------------------------------------

def _all_tests() -> list[tuple[str, Callable]]:
    g = globals()
    return sorted(
        [(name, fn) for name, fn in g.items()
         if name.startswith("test_") and callable(fn)],
        key=lambda x: x[0],
    )


def main():
    tests = _all_tests()
    print(f"\n{'='*60}\nNexa smoke tests — {len(tests)} cases")
    if "--live" in sys.argv:
        print("LIVE MODE — collectors will hit real APIs")
    print("=" * 60)

    passed, failed = [], []
    for name, fn in tests:
        print(f"\n  {name}")
        try:
            fn()
            passed.append(name)
            print(f"  -> PASS")
        except AssertionError as e:
            failed.append((name, str(e)))
            print(f"  -> FAIL: {e}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  -> ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"  {len(passed)}/{len(tests)} passed")
    if failed:
        print(f"\n  Failures:")
        for name, err in failed:
            print(f"    - {name}: {err}")
    print("=" * 60)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
