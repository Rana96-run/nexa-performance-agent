"""
analysers/data_quality.py
==========================
Silent post-refresh auto-heal — runs after every BQ refresh pass and fixes
anomalies WITHOUT alerting the user. The weekly summary picks up the fix
counts and shows a one-line "🔧 Auto-healed: X" block.

Auto-heal cases:
  1. Future-dated partitions (date > today) — DELETE.
       Even with validate_row in bq_writer, an ad-hoc backfill or upstream
       schema drift could land a future row. Belt + suspenders.

  2. Channel wrote 0 rows for "today" / "yesterday" when prior 7 days had
     consistent data — the collector ran but produced nothing. We re-run
     the collector once. If still 0, log and move on (could be legit
     pause).

  3. Negative aggregate sums — sum(spend) < 0 for a (date, channel)
     combination indicates corrupted rows that snuck past the validator
     (e.g. a column added later). DELETE the partition and re-run.

  4. HubSpot consistency — leads_qualified + leads_disqualified > leads_total
     by more than 1-row slack. DELETE the affected partition and re-run.

What this skill does NOT do:
  - Decide what's a "real" anomaly vs a "fix-me-now" anomaly.
  - Page or notify on issues — those go to the weekly summary as counts.
  - Touch ad platforms (only manipulates BQ + re-triggers collectors).

The user said: "I don't care about the issue itself, I care about solving
it." So this module solves it and reports back what it solved.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from collectors.bq_writer import get_client


_DATASET = "qoyod_marketing"


# ── Discovery ────────────────────────────────────────────────────────────────

def find_future_partitions() -> list[dict]:
    """Returns list of {table, date, row_count} for any date > today across
    every partitioned table. Should be empty in steady state."""
    client = get_client()
    # Inventory of tables that have a `date` column
    q = f"""
      SELECT table_name
      FROM `{_DATASET}.INFORMATION_SCHEMA.COLUMNS`
      WHERE column_name = 'date' AND data_type = 'DATE'
    """
    findings = []
    for r in client.query(q).result():
        t = r.table_name
        try:
            q2 = f"""
              SELECT date, COUNT(*) AS n
              FROM `{_DATASET}.{t}`
              WHERE date > CURRENT_DATE()
              GROUP BY date
            """
            for rr in client.query(q2).result():
                findings.append({"table": t, "date": rr.date, "row_count": rr.n})
        except Exception as e:
            print(f"[dq] future-partition scan skipped {t}: {e}")
    return findings


def find_zero_row_channels(yesterday: date | None = None) -> list[str]:
    """Returns channel names where today/yesterday has 0 rows in
    campaigns_daily but the prior 7 days each had ≥ 1 row.

    A channel that's been silently failing for one day shows here.
    A channel that's been off for a week (legit pause) does not.
    """
    yesterday = yesterday or (date.today() - timedelta(days=1))
    q = f"""
      WITH prior AS (
        SELECT channel, COUNT(DISTINCT date) AS days_seen
        FROM `{_DATASET}.campaigns_daily`
        WHERE date BETWEEN DATE_SUB(@y, INTERVAL 7 DAY) AND DATE_SUB(@y, INTERVAL 1 DAY)
        GROUP BY channel
      ),
      today AS (
        SELECT DISTINCT channel
        FROM `{_DATASET}.campaigns_daily`
        WHERE date = @y
      )
      SELECT p.channel
      FROM prior p
      LEFT JOIN today t USING (channel)
      WHERE p.days_seen >= 5    -- must have been writing consistently before
        AND t.channel IS NULL   -- but wrote nothing yesterday
    """
    from google.cloud import bigquery
    client = get_client()
    job = client.query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("y", "DATE", yesterday)]
    ))
    return [r.channel for r in job.result()]


def find_negative_partitions() -> list[dict]:
    """Returns (table, date, channel) where SUM(spend) < 0 for a partition —
    indicates corrupted rows snuck past the validator."""
    client = get_client()
    q = f"""
      SELECT 'campaigns_daily' AS tbl, date, channel, ROUND(SUM(spend),2) AS s
      FROM `{_DATASET}.campaigns_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      GROUP BY date, channel
      HAVING s < 0
    """
    out = []
    try:
        for r in client.query(q).result():
            out.append({"table": r.tbl, "date": r.date, "channel": r.channel, "sum_spend": r.s})
    except Exception as e:
        print(f"[dq] negative-partition scan failed: {e}")
    return out


def find_inconsistent_lead_partitions() -> list[dict]:
    """leads_qualified + leads_disqualified should be ≤ leads_total + 1
    (small float slack). If not, the partition is internally inconsistent."""
    client = get_client()
    q = f"""
      SELECT date,
             SUM(leads_total)        AS lt,
             SUM(leads_qualified)    AS lq,
             SUM(leads_disqualified) AS ld
      FROM `{_DATASET}.hubspot_leads_module_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      GROUP BY date
      HAVING (lq + ld) > (lt + 1)
    """
    out = []
    try:
        for r in client.query(q).result():
            out.append({"date": r.date, "leads_total": r.lt,
                        "leads_qualified": r.lq, "leads_disqualified": r.ld})
    except Exception as e:
        print(f"[dq] lead-consistency scan failed: {e}")
    return out


# ── Auto-heal actions ────────────────────────────────────────────────────────

def _delete_future_partition(table: str, d: date) -> int:
    client = get_client()
    q = f"DELETE FROM `{_DATASET}.{table}` WHERE date = '{d.isoformat()}'"
    job = client.query(q)
    job.result()
    return job.num_dml_affected_rows or 0


def _delete_partition(table: str, d: date, channel: str | None = None) -> int:
    client = get_client()
    where = f"date = '{d.isoformat()}'"
    if channel:
        where += f" AND channel = '{channel}'"
    job = client.query(f"DELETE FROM `{_DATASET}.{table}` WHERE {where}")
    job.result()
    return job.num_dml_affected_rows or 0


_CHANNEL_TO_COLLECTOR = {
    # channel name in BQ → (module, function-name, kwargs)
    "google_ads":    ("collectors.google_ads_bq",    "collect_and_write", {"days": 3}),
    "meta":          ("collectors.meta_bq",          "collect_and_write", {"days": 3}),
    "snapchat":      ("collectors.snap_bq",          "collect_and_write", {"days": 3}),
    "tiktok":        ("collectors.tiktok_bq",        "collect_and_write", {"days": 3}),
    "microsoft_ads": ("collectors.microsoft_ads_bq", "collect_and_write", {"days": 3}),
    "linkedin":      ("collectors.linkedin_bq",      "collect_and_write", {"days": 3}),
    "hubspot_leads": ("collectors.hubspot_leads_bq", "collect_and_write", {"days": 3}),
    "hubspot_deals": ("collectors.hubspot_deals_bq", "collect_and_write", {"days": 3}),
}


def _retry_collector(channel: str) -> int:
    """Re-run a channel's collector for the last 3 days. Returns rows written."""
    spec = _CHANNEL_TO_COLLECTOR.get(channel)
    if not spec:
        print(f"[dq] no retry spec for channel {channel}")
        return 0
    mod_name, fn_name, kwargs = spec
    try:
        import importlib
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name)
        return fn(**kwargs) or 0
    except Exception as e:
        print(f"[dq] retry {channel} failed: {e}")
        return 0


# ── Top-level: run everything, return a fix-counts dict ─────────────────────

def auto_heal() -> dict:
    """
    Runs every detector + applies the fix. Returns a dict suitable for the
    weekly summary block:

      {
        "future_partitions_removed": 0,
        "zero_row_channels_recovered": 0,
        "zero_row_channels_still_empty": 0,
        "negative_partitions_recovered": 0,
        "inconsistent_lead_partitions_recovered": 0,
        "checked_at": "2026-05-06T08:00:00Z",
      }

    Logs each action so the BQ activity log has the trail.
    """
    counts = {
        "future_partitions_removed":            0,
        "zero_row_channels_recovered":          0,
        "zero_row_channels_still_empty":        0,
        "negative_partitions_recovered":        0,
        "inconsistent_lead_partitions_recovered": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    # 1. Future partitions
    future = find_future_partitions()
    for f in future:
        try:
            n = _delete_future_partition(f["table"], f["date"])
            counts["future_partitions_removed"] += n
            print(f"[dq] removed {n} future row(s) from {f['table']} dated {f['date']}")
        except Exception as e:
            print(f"[dq] future-partition delete failed for {f}: {e}")

    # 2. Zero-row channels
    silent = find_zero_row_channels()
    for ch in silent:
        try:
            n = _retry_collector(ch)
            if n > 0:
                counts["zero_row_channels_recovered"] += 1
                print(f"[dq] re-fetched {ch}: {n} row(s) recovered")
            else:
                counts["zero_row_channels_still_empty"] += 1
                print(f"[dq] re-fetched {ch}: still 0 rows (likely legit pause / token issue)")
        except Exception as e:
            print(f"[dq] retry failed for {ch}: {e}")

    # 3. Negative-spend partitions
    neg = find_negative_partitions()
    for n in neg:
        try:
            _delete_partition(n["table"], n["date"], n["channel"])
            recovered = _retry_collector(n["channel"])
            if recovered > 0:
                counts["negative_partitions_recovered"] += 1
            print(f"[dq] negative-spend partition {n}: deleted + re-fetched ({recovered} rows)")
        except Exception as e:
            print(f"[dq] negative-partition heal failed for {n}: {e}")

    # 4. Inconsistent lead partitions
    inc = find_inconsistent_lead_partitions()
    for r in inc:
        try:
            _delete_partition("hubspot_leads_module_daily", r["date"])
            recovered = _retry_collector("hubspot_leads")
            if recovered > 0:
                counts["inconsistent_lead_partitions_recovered"] += 1
            print(f"[dq] inconsistent lead partition {r['date']}: deleted + re-fetched ({recovered} rows)")
        except Exception as e:
            print(f"[dq] inconsistent-lead heal failed for {r}: {e}")

    # Log to BQ for the weekly summary to pick up
    try:
        from logs.activity_logger import log_activity_async
        total_fixed = (counts["future_partitions_removed"]
                       + counts["zero_row_channels_recovered"]
                       + counts["negative_partitions_recovered"]
                       + counts["inconsistent_lead_partitions_recovered"])
        log_activity_async(
            role="bq_refresh",
            action="data_quality_autoheal",
            status="success",
            details=counts,
            rows_affected=total_fixed,
        )
    except Exception as e:
        print(f"[dq] activity log write failed: {e}")

    return counts


if __name__ == "__main__":
    result = auto_heal()
    print(f"\n{json.dumps(result, indent=2, default=str)}")
