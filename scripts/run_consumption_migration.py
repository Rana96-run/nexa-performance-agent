"""
scripts/run_consumption_migration.py
====================================
One-shot runner to:
  1. ALTER agent_activity_log to add tokens_in / tokens_out / cost_usd /
     api_calls / bq_bytes_scanned columns (idempotent — IF NOT EXISTS).
  2. Create / replace the v_agent_consumption_daily view that the Hex
     dashboard reads to render consumption cards + heatmap.

Run once after deploying the cost_tracking changes:
    python scripts/run_consumption_migration.py

Safe to re-run — both statements are idempotent.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from collectors.bq_writer import get_client


PROJECT = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
DATASET = os.getenv("BQ_DATASET", "qoyod_marketing")


# ── 1. Schema migration ──────────────────────────────────────────────────────
MIGRATION_SQL = (REPO / "scripts" / "migrate_activity_log_consumption.sql").read_text(
    encoding="utf-8"
)


# ── 2. Consumption rollup view ───────────────────────────────────────────────
# One row per (date, role) summing tokens, cost, api calls, bytes scanned.
# Used by the Hex dashboard to render Single Value cards + per-role breakdown.
CONSUMPTION_VIEW_SQL = f"""
CREATE OR REPLACE VIEW `{PROJECT}.{DATASET}.v_agent_consumption_daily` AS
SELECT
  DATE(ts, 'Asia/Riyadh')                                AS day,
  role,
  COUNT(*)                                               AS actions,
  SUM(COALESCE(tokens_in,  0))                           AS tokens_in_total,
  SUM(COALESCE(tokens_out, 0))                           AS tokens_out_total,
  SUM(COALESCE(tokens_in,  0)) + SUM(COALESCE(tokens_out, 0)) AS tokens_total,
  ROUND(SUM(COALESCE(cost_usd, 0)),    4)                AS cost_usd_total,
  SUM(COALESCE(api_calls, 0))                            AS api_calls_total,
  SUM(COALESCE(bq_bytes_scanned, 0))                     AS bq_bytes_scanned_total,
  -- BQ cost re-derived from bytes (cheap to compute, lets the view stay
  -- correct if pricing changes without backfilling cost_usd).
  ROUND(
    SUM(COALESCE(bq_bytes_scanned, 0)) / POW(1024, 4) * 6.25,
    4
  )                                                      AS bq_cost_usd_estimate
FROM `{PROJECT}.{DATASET}.agent_activity_log`
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
GROUP BY day, role
ORDER BY day DESC, cost_usd_total DESC
"""


def main() -> None:
    client = get_client()

    print(f"Running schema migration on {PROJECT}.{DATASET}.agent_activity_log …")
    job = client.query(MIGRATION_SQL)
    job.result()
    print("  [OK] schema columns added (or already present)")

    print(f"Creating view {PROJECT}.{DATASET}.v_agent_consumption_daily …")
    job = client.query(CONSUMPTION_VIEW_SQL)
    job.result()
    print("  [OK] view created")

    # Sanity probe — show the most recent day
    probe = f"""
    SELECT day, role, actions, tokens_total, cost_usd_total,
           api_calls_total, bq_bytes_scanned_total
    FROM `{PROJECT}.{DATASET}.v_agent_consumption_daily`
    LIMIT 10
    """
    rows = list(client.query(probe).result())
    if not rows:
        print("\n[OK] migration complete — no rows yet (logger hasn't written "
              "consumption fields). They'll populate as the agent runs.")
        return
    print("\nRecent consumption (top 10 rows):")
    for r in rows:
        print(f"  {r.day}  {r.role:25s}  actions={r.actions:4d}  "
              f"tokens={r.tokens_total:>8}  cost=${float(r.cost_usd_total or 0):.4f}  "
              f"apis={r.api_calls_total:>4}  bq_bytes={r.bq_bytes_scanned_total:>10}")


if __name__ == "__main__":
    main()
