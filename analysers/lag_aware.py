"""Lag-aware CPQL helpers.

Problem: when leads from the last few days haven't been worked by SDRs yet,
they sit in `leads_open` instead of being qualified or disqualified. Computing
CPQL on those days gives nonsense numbers (May 15 2026 reported $2,801 CPQL —
147 of 158 leads were still open).

This module provides a single canonical rule: a day is "lag-affected" when
`open_leads / leads_total > LAG_OPEN_PCT_THRESHOLD` (default 30%).

Callers should:
  - Use `lag_clean_filter_sql()` inside their WHERE clause when computing CPQL
    over a window — it excludes lag-affected days from the math.
  - Use `lag_excluded_days_sql()` to surface how many days were dropped, so
    the UI can show "(N day(s) excluded for lag)".
  - For Python-side filtering (campaign_health.py, analysers), use
    `is_lag_affected(open_leads, leads_total)`.
"""
from __future__ import annotations
from config import LAG_OPEN_PCT_THRESHOLD


def is_lag_affected(open_leads, leads_total, threshold: float | None = None) -> bool:
    """Returns True if this row's open-leads share exceeds the lag threshold."""
    if leads_total in (None, 0):
        return False
    o = open_leads or 0
    t = leads_total or 0
    if t == 0:
        return False
    return (o / t) > (threshold if threshold is not None else LAG_OPEN_PCT_THRESHOLD)


def lag_clean_filter_sql(
    open_col: str = "open_leads",
    leads_col: str = "leads_total",
    threshold: float | None = None,
) -> str:
    """A SQL boolean expression returning TRUE when the row is NOT lag-affected.

    Inject into a CTE's WHERE clause:
        WHERE COALESCE({leads_col}, 0) = 0 OR {filter} ...

    But that's awkward — better usage is to wrap CPQL math:
        SAFE_DIVIDE(
          SUM(IF({lag_clean_filter_sql()}, spend, 0)),
          NULLIF(SUM(IF({lag_clean_filter_sql()}, qualified, 0)), 0)
        ) AS cpql
    which keeps CPQL clean while leaving volume metrics (spend/leads) untouched.
    """
    t = threshold if threshold is not None else LAG_OPEN_PCT_THRESHOLD
    return (
        f"(SAFE_DIVIDE(COALESCE({open_col}, 0), NULLIF({leads_col}, 0)) IS NULL "
        f"OR SAFE_DIVIDE(COALESCE({open_col}, 0), NULLIF({leads_col}, 0)) <= {t})"
    )


def lag_excluded_days_sql(
    open_col: str = "open_leads",
    leads_col: str = "leads_total",
    threshold: float | None = None,
) -> str:
    """A SQL expression that counts lag-affected days. Use inside aggregation:
        SELECT
          {lag_excluded_days_sql()} AS lag_excluded_days,
          ...
        FROM base
    """
    t = threshold if threshold is not None else LAG_OPEN_PCT_THRESHOLD
    return (
        f"COUNTIF(SAFE_DIVIDE(COALESCE({open_col}, 0), NULLIF({leads_col}, 0)) > {t})"
    )


def format_cpql_with_lag(cpql, lag_excluded_days: int) -> str:
    """Human-readable CPQL with lag annotation. Used by Slack/CLI summaries."""
    if cpql is None or cpql == 0:
        if lag_excluded_days and lag_excluded_days > 0:
            return f"pending ({lag_excluded_days}d open)"
        return "—"
    base = f"${int(cpql):,}"
    if lag_excluded_days and lag_excluded_days > 0:
        return f"{base} (lag-adj, {lag_excluded_days}d excl)"
    return base
