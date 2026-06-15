"""
scripts/reconcile_views.py — per-channel view reconciliation gate

Compares v_ad_performance and v_adset_performance leads against
hubspot_leads_module_daily (source of truth) for a given date window.

Bar: ratio ≤ 1.05 on EVERY paid channel.
Run after any change to v_ad_performance, v_adset_performance,
utm_paid_attribution_daily, or related CTEs.

Usage:
    railway run python scripts/reconcile_views.py
    railway run python scripts/reconcile_views.py --days 14
    railway run python scripts/reconcile_views.py --start 2026-06-01 --end 2026-06-07
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BQ_PROJECT = None  # resolved from env at runtime
BQ_DATASET = None

PAID_CHANNELS = {"google_ads", "meta", "snapchat", "tiktok", "microsoft_ads"}
RATIO_BAR = 1.05   # view leads / hs leads must be <= this


# ── BQ helpers ────────────────────────────────────────────────────────────────

def _client():
    import os
    from google.cloud import bigquery
    global BQ_PROJECT, BQ_DATASET
    BQ_PROJECT = os.getenv("BQ_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "angular-axle-492812-q4")
    BQ_DATASET = os.getenv("BQ_DATASET", "qoyod_marketing")
    return bigquery.Client(project=BQ_PROJECT)


def _run(client, sql: str) -> list[dict]:
    rows = client.query(sql).result()
    return [dict(r) for r in rows]


# ── Queries ───────────────────────────────────────────────────────────────────

def _hs_leads_by_channel(client, start: str, end: str) -> dict[str, int]:
    """Source of truth: hubspot_leads_module_daily per paid channel.
    v_channel_key_map inlined as a CASE expression (view dropped 2026-06-16)."""
    sql = f"""
    SELECT
      CASE hl.lead_qoyod_source
        WHEN 'Google Ads'     THEN 'google_ads'
        WHEN 'Meta Ads'       THEN 'meta'
        WHEN 'Snapchat Ads'   THEN 'snapchat'
        WHEN 'TikTok Ads'     THEN 'tiktok'
        WHEN 'Microsoft Ads'  THEN 'microsoft_ads'
        WHEN 'LinkedIn Ads'   THEN 'linkedin'
        WHEN 'Organic Search' THEN 'organic_search'
      END AS channel,
      SUM(hl.leads_total) AS hs_leads
    FROM `{BQ_PROJECT}.{BQ_DATASET}.hubspot_leads_module_daily` hl
    WHERE hl.date BETWEEN '{start}' AND '{end}'
      AND hl.lead_qoyod_source IN (
        'Google Ads', 'Meta Ads', 'Snapchat Ads',
        'TikTok Ads', 'Microsoft Ads', 'LinkedIn Ads'
      )
    GROUP BY 1
    """
    return {r["channel"]: r["hs_leads"] for r in _run(client, sql) if r["channel"]}


def _view_leads_by_channel(client, view: str, start: str, end: str) -> dict[str, int]:
    """Leads from a materialized view, collapsed to channel grain."""
    sql = f"""
    SELECT
      channel,
      SUM(leads_total) AS view_leads
    FROM `{BQ_PROJECT}.{BQ_DATASET}.{view}`
    WHERE date BETWEEN '{start}' AND '{end}'
      AND channel IN ({', '.join(repr(c) for c in PAID_CHANNELS)})
    GROUP BY 1
    """
    return {r["channel"]: r["view_leads"] for r in _run(client, sql)}


# ── Core check ────────────────────────────────────────────────────────────────

def reconcile(view: str, start: str, end: str, client) -> tuple[bool, list[str]]:
    """
    Returns (all_pass, list_of_result_lines).
    all_pass is True only if every channel ratio <= RATIO_BAR.
    """
    hs = _hs_leads_by_channel(client, start, end)
    view_leads = _view_leads_by_channel(client, view, start, end)

    all_channels = PAID_CHANNELS & (set(hs) | set(view_leads))
    lines = []
    all_pass = True

    for ch in sorted(all_channels):
        hs_n = hs.get(ch, 0)
        view_n = view_leads.get(ch, 0)
        if hs_n == 0:
            ratio = float("inf") if view_n > 0 else 1.0
            ratio_str = "∞" if view_n > 0 else "1.00"
        else:
            ratio = view_n / hs_n
            ratio_str = f"{ratio:.2f}"

        passed = ratio <= RATIO_BAR
        if not passed:
            all_pass = False
        icon = "✓" if passed else "✗ FAIL"
        lines.append(
            f"  {icon}  {ch:<20}  view={view_n:>5}  hs={hs_n:>5}  ratio={ratio_str}"
        )

    return all_pass, lines


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Per-channel view reconciliation gate")
    parser.add_argument("--days",  type=int, default=7,
                        help="Number of completed days to check (default: 7)")
    parser.add_argument("--start", help="Start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--end",   help="End date YYYY-MM-DD (overrides --days)")
    args = parser.parse_args()

    client = _client()

    # Resolve window — always end at last complete spend day
    if args.start and args.end:
        start, end = args.start, args.end
    else:
        # End = yesterday (collector typically lands before this script runs)
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=args.days - 1)
        start, end = str(start_date), str(end_date)

    print(f"\n=== View Reconciliation Gate  [{start} to {end}] ===")
    print(f"Bar: ratio <= {RATIO_BAR} on every paid channel\n")

    overall_pass = True
    for view in ("v_ad_performance", "v_adset_performance"):
        passed, lines = reconcile(view, start, end, client)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {view}")
        for line in lines:
            print(line)
        print()
        if not passed:
            overall_pass = False

    if overall_pass:
        print("ALL VIEWS PASS — safe to deploy.\n")
        sys.exit(0)
    else:
        print("ONE OR MORE VIEWS FAILED — do not declare this change done.")
        print("Trace the failing channel to the most-upstream view that over-reports.")
        print("See memory/08_pitfalls.md: 'v_ad_performance leads fan-out' for the fix pattern.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
