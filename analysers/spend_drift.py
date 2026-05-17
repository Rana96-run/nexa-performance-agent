"""Spend-drift detector — three nightly anomaly rules.

These rules are tied 1:1 to specific May 2026 failures the team would have
caught earlier if these checks had been running:

    Rule 1 — Scaling an underperformer:
      Campaign's 14-day CPQL > $140 AND week-over-week spend up > 20%.
      → would have flagged PMax_AR_Generic_Retargeting ($124→$175 CPQL with
        3.6x spend bump).

    Rule 2 — Silent campaign death:
      Campaign spent > $500 in prior 30 days but < 5% of that in last 7d.
      → would have flagged PMax_AR_E-Invoice ($3,000 → $3).

    Rule 3 — Launch wave:
      ≥ 3 new-spend campaigns on the same channel within a 7-day window.
      → would have flagged the May 4-10 Bing/Google launch wave (8 campaigns).

Findings are returned as dicts; downstream consumers create Asana tasks or
post to #approvals. This module performs zero writes.

Run with:
    railway run python -m analysers.spend_drift          # all rules
    railway run python -m analysers.spend_drift --rule scaling
    railway run python -m analysers.spend_drift --rule silent
    railway run python -m analysers.spend_drift --rule wave
"""
from __future__ import annotations
import sys
from datetime import date, timedelta
from typing import Iterable

from collectors.bq_writer import get_client, PROJECT_ID, DATASET

# ── Thresholds (kept local — see analysers/lag_aware for the design pattern) ──
CPQL_SCALING_BLOCK_USD  = 140.00   # Rule 1: 14d CPQL above this is "broken"
WOW_SPEND_BUMP_PCT      = 0.20     # Rule 1: +20% WoW spend = "scaling"
SILENT_DEATH_PRIOR_USD  = 500.00   # Rule 2: must have spent at least this in prior_30d
SILENT_DEATH_DROP_PCT   = 0.05     # Rule 2: last_7d < 5% of prior_30d = "death"
LAUNCH_WAVE_COUNT       = 3        # Rule 3: 3+ new campaigns
LAUNCH_WAVE_WINDOW_DAYS = 7        # Rule 3: ... within a 7-day window
LAUNCH_WAVE_LOOKBACK    = 14       # Rule 3: only look at last 14 days for new launches

# Channels we skip on Rule 3 — Snap has 185 short-lived ad-objects that get
# created and burnt out daily; "wave" detection would fire constantly without
# adding signal. Re-enable per-channel if/when their ops pattern changes.
LAUNCH_WAVE_CHANNEL_BLOCKLIST = {"snapchat"}


# ─── Rule 1 ─────────────────────────────────────────────────────────────────

def detect_scaling_underperformers(cpql_threshold: float = CPQL_SCALING_BLOCK_USD,
                                   wow_bump_pct: float = WOW_SPEND_BUMP_PCT) -> list[dict]:
    """Find campaigns whose 14-day CPQL > threshold AND WoW spend > +20%."""
    client = get_client()
    sql = f"""
        WITH hs AS (
          SELECT date, lead_utm_campaign,
                 SUM(leads_total)     AS leads,
                 SUM(leads_qualified) AS sqls,
                 -- Day-level lag flag (same logic as campaign_health.py)
                 SAFE_DIVIDE(SUM(COALESCE(leads_open,0)),
                             NULLIF(SUM(leads_total), 0)) <= 0.30
                   OR SUM(leads_total) = 0       AS day_lag_ok
          FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
          GROUP BY date, lead_utm_campaign
        ),
        joined AS (
          SELECT c.date, c.channel, c.campaign_id, c.campaign_name,
                 c.spend, hs.sqls, hs.day_lag_ok
          FROM `{PROJECT_ID}.{DATASET}.campaigns_daily` c
          LEFT JOIN hs
            ON c.date = hs.date
           AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
          WHERE c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
            AND c.date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
        ),
        rolled AS (
          SELECT channel, campaign_id, ANY_VALUE(campaign_name) AS campaign_name,
            SUM(spend) AS spend_14d,
            SUM(IF(date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL  7 DAY), spend, 0))     AS spend_last_7d,
            SUM(IF(date <  DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL  7 DAY), spend, 0))     AS spend_prev_7d,
            -- lag-aware CPQL
            SAFE_DIVIDE(
              SUM(IF(day_lag_ok, spend, 0)),
              NULLIF(SUM(IF(day_lag_ok, sqls, 0)), 0)
            ) AS cpql_14d
          FROM joined
          GROUP BY channel, campaign_id
        )
        SELECT *,
               SAFE_DIVIDE(spend_last_7d - spend_prev_7d, NULLIF(spend_prev_7d, 0)) AS wow_pct
        FROM rolled
        WHERE cpql_14d > {cpql_threshold}
          AND spend_last_7d > spend_prev_7d * (1 + {wow_bump_pct})
          AND spend_last_7d > 50          -- ignore micro-spend campaigns
        ORDER BY (spend_last_7d - spend_prev_7d) DESC
    """
    findings = []
    for r in client.query(sql).result():
        findings.append({
            "rule":          "scaling_underperformer",
            "channel":       r.channel,
            "campaign_id":   r.campaign_id,
            "campaign_name": r.campaign_name,
            "cpql_14d":      round(float(r.cpql_14d), 1) if r.cpql_14d else None,
            "spend_last_7d": round(float(r.spend_last_7d or 0), 0),
            "spend_prev_7d": round(float(r.spend_prev_7d or 0), 0),
            "wow_pct":       round(float(r.wow_pct or 0) * 100, 1),
        })
    return findings


# ─── Rule 2 ─────────────────────────────────────────────────────────────────

def detect_silent_deaths(prior_min_usd: float = SILENT_DEATH_PRIOR_USD,
                         drop_pct: float = SILENT_DEATH_DROP_PCT) -> list[dict]:
    """Find campaigns that spent > $X in prior 30d but went silent (last 7d)."""
    client = get_client()
    sql = f"""
        WITH rolled AS (
          SELECT channel, campaign_id, ANY_VALUE(campaign_name) AS campaign_name,
            SUM(IF(date BETWEEN DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 37 DAY)
                              AND DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL  8 DAY),
                   spend, 0)) AS prior_30d,
            SUM(IF(date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                   AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY),
                   spend, 0)) AS last_7d,
            MAX(IF(date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                   AND spend > 0, status, NULL)) AS recent_status
          FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
          WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 37 DAY)
          GROUP BY channel, campaign_id
        )
        SELECT *,
               SAFE_DIVIDE(last_7d, NULLIF(prior_30d, 0)) AS pct_of_prior
        FROM rolled
        WHERE prior_30d > {prior_min_usd}
          AND last_7d < prior_30d * {drop_pct}
        ORDER BY prior_30d DESC
    """
    findings = []
    for r in client.query(sql).result():
        findings.append({
            "rule":          "silent_death",
            "channel":       r.channel,
            "campaign_id":   r.campaign_id,
            "campaign_name": r.campaign_name,
            "prior_30d":     round(float(r.prior_30d or 0), 0),
            "last_7d":       round(float(r.last_7d or 0), 0),
            "pct_of_prior":  round(float(r.pct_of_prior or 0) * 100, 1),
            "recent_status": r.recent_status,
        })
    return findings


# ─── Rule 3 ─────────────────────────────────────────────────────────────────

def detect_launch_waves(min_count: int = LAUNCH_WAVE_COUNT,
                        window_days: int = LAUNCH_WAVE_WINDOW_DAYS,
                        lookback_days: int = LAUNCH_WAVE_LOOKBACK,
                        blocklist: set[str] = LAUNCH_WAVE_CHANNEL_BLOCKLIST) -> list[dict]:
    """Find channels with N+ new-spend campaigns clustered in a 7-day window."""
    client = get_client()
    sql = f"""
        WITH first_spend AS (
          SELECT channel, campaign_id,
                 ANY_VALUE(campaign_name) AS campaign_name,
                 MIN(IF(spend > 10, date, NULL)) AS first_day
          FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
          GROUP BY channel, campaign_id
        )
        SELECT channel,
               first_day,
               COUNT(DISTINCT campaign_id) AS wave_size,
               ARRAY_AGG(campaign_name ORDER BY campaign_name LIMIT 50) AS campaigns
        FROM first_spend
        WHERE first_day >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {lookback_days} DAY)
        GROUP BY channel, first_day
    """
    # We count campaigns whose first_day falls within a sliding 7-day window —
    # do that in Python rather than a 200-line BQ window function.
    rows = list(client.query(sql).result())
    by_channel: dict[str, list[dict]] = {}
    for r in rows:
        by_channel.setdefault(r.channel, []).append({
            "first_day": r.first_day,
            "size":      int(r.wave_size),
            "campaigns": list(r.campaigns or []),
        })

    findings = []
    for channel, days in by_channel.items():
        if channel in blocklist:
            continue
        days.sort(key=lambda d: d["first_day"])
        # Slide a 7-day window over the sorted first-spend days.
        n = len(days)
        for i in range(n):
            window_end = days[i]["first_day"] + timedelta(days=window_days)
            cluster_campaigns = []
            for j in range(i, n):
                if days[j]["first_day"] >= window_end:
                    break
                cluster_campaigns.extend(days[j]["campaigns"])
            if len(cluster_campaigns) >= min_count:
                findings.append({
                    "rule":           "launch_wave",
                    "channel":        channel,
                    "window_start":   days[i]["first_day"].isoformat(),
                    "window_end":     (window_end - timedelta(days=1)).isoformat(),
                    "wave_size":      len(cluster_campaigns),
                    "campaigns":      cluster_campaigns,
                })
                break  # one finding per channel; don't duplicate windows
    return findings


# ─── Runner ─────────────────────────────────────────────────────────────────

def run_all() -> dict[str, list[dict]]:
    """Run all three rules and return findings grouped by rule."""
    return {
        "scaling_underperformer": detect_scaling_underperformers(),
        "silent_death":           detect_silent_deaths(),
        "launch_wave":            detect_launch_waves(),
    }


def _print_findings(findings: dict[str, list[dict]]) -> None:
    for rule, items in findings.items():
        print(f"\n── {rule} ({len(items)} finding{'s' if len(items) != 1 else ''}) ──")
        for f in items:
            print(f"  {f}")


if __name__ == "__main__":
    rule = None
    for i, a in enumerate(sys.argv):
        if a == "--rule" and i + 1 < len(sys.argv):
            rule = sys.argv[i + 1]

    if rule == "scaling":
        _print_findings({"scaling_underperformer": detect_scaling_underperformers()})
    elif rule == "silent":
        _print_findings({"silent_death": detect_silent_deaths()})
    elif rule == "wave":
        _print_findings({"launch_wave": detect_launch_waves()})
    else:
        _print_findings(run_all())
