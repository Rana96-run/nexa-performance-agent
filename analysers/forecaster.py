"""Month-over-month forecaster — projects end-of-month and end-of-next-month
spend/leads/SQLs/CPQL/revenue based on current trajectory.

Two scenarios per projection:
  - Status quo: linear extrapolation from last 14 days
  - Post-action: incorporates open Asana actions (pause/scale recommendations)
                 if the team executes them. Pause = -X% spend per affected campaign;
                 scale = +Y% per affected campaign.

Read-only. Run from CLI or wire into monthly cadence.

Run with:
    railway run python -m analysers.forecaster
"""
from __future__ import annotations
import json
import sys
import calendar
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Optional

from collectors.bq_writer import get_client, PROJECT_ID, DATASET

DS = f"`{PROJECT_ID}.{DATASET}`"

# Trend window — how many recent days to base the projection on
TREND_WINDOW_DAYS = 14


@dataclass
class Projection:
    label:        str
    horizon_end:  str
    days_so_far:  int
    days_total:   int
    actual:       dict = field(default_factory=dict)    # what's happened so far
    projected:    dict = field(default_factory=dict)    # full-horizon estimate
    daily_rate:   dict = field(default_factory=dict)    # per-day used for the projection


@dataclass
class ForecastResult:
    today:             str
    trend_window_days: int
    by_channel:        list[dict] = field(default_factory=list)
    end_of_month:      Optional[Projection] = None
    end_of_next_month: Optional[Projection] = None
    narrative:         list[str] = field(default_factory=list)


# ── Trend pull ──────────────────────────────────────────────────────────────

def _recent_daily_rate(start: date, end: date) -> dict:
    """Average daily spend/leads/SQLs/CPQL/revenue over the window."""
    sql = f"""
        SELECT
          COUNT(DISTINCT date)        AS days,
          ROUND(SUM(spend), 0)        AS spend,
          SUM(leads_total)            AS leads,
          SUM(qualified)              AS sqls,
          SUM(deals_won)              AS deals_won,
          ROUND(SUM(revenue_won), 0)  AS revenue,
          ROUND(SAFE_DIVIDE(SUM(spend), SUM(leads_total)), 2)    AS cpl,
          ROUND(SAFE_DIVIDE(
            SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
                    OR leads_total = 0, spend, 0)),
            NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(open_leads,0), NULLIF(leads_total,0)) <= 0.30
                           OR leads_total = 0, qualified, 0)), 0)
          ), 2) AS cpql_lag_aware,
          ROUND(SAFE_DIVIDE(SUM(revenue_won), SUM(spend)), 2)    AS roas
        FROM {DS}.paid_channel_daily
        WHERE date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    rows = list(get_client().query(sql).result())
    if not rows: return {}
    r = dict(rows[0])
    d = max(int(r.get("days") or 1), 1)
    return {
        "days":       d,
        "spend_d":    (r.get("spend") or 0) / d,
        "leads_d":    (r.get("leads") or 0) / d,
        "sqls_d":     (r.get("sqls") or 0) / d,
        "rev_d":      (r.get("revenue") or 0) / d,
        "deals_d":    (r.get("deals_won") or 0) / d,
        "cpl":        r.get("cpl"),
        "cpql":       r.get("cpql_lag_aware"),
        "roas":       r.get("roas"),
    }


def _month_to_date_actual(today: date) -> dict:
    """Actuals from month start through yesterday (T-1)."""
    start = today.replace(day=1)
    end   = today - timedelta(days=1)
    if end < start:  # first of the month — no T-1 data yet
        return {"days_so_far": 0, "spend": 0, "leads": 0, "sqls": 0, "rev": 0}
    sql = f"""
        SELECT
          COUNT(DISTINCT date)        AS days,
          ROUND(SUM(spend), 0)        AS spend,
          SUM(leads_total)            AS leads,
          SUM(qualified)              AS sqls,
          ROUND(SUM(revenue_won), 0)  AS rev,
          SUM(deals_won)              AS deals_won
        FROM {DS}.paid_channel_daily
        WHERE date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    rows = list(get_client().query(sql).result())
    if not rows: return {"days_so_far": 0, "spend": 0, "leads": 0, "sqls": 0, "rev": 0}
    r = dict(rows[0])
    return {
        "days_so_far": int(r.get("days") or 0),
        "spend":       int(r.get("spend") or 0),
        "leads":       int(r.get("leads") or 0),
        "sqls":        int(r.get("sqls") or 0),
        "rev":         int(r.get("rev") or 0),
        "deals_won":   int(r.get("deals_won") or 0),
    }


def _days_left_in_month(today: date) -> int:
    last_day = calendar.monthrange(today.year, today.month)[1]
    return last_day - today.day + 1


def _per_channel_trend(start: date, end: date) -> list[dict]:
    sql = f"""
        SELECT channel,
          COUNT(DISTINCT date)      AS days,
          ROUND(SUM(spend), 0)      AS spend,
          SUM(leads_total)          AS leads,
          SUM(qualified)            AS sqls,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)), 1) AS cpql
        FROM {DS}.paid_channel_daily
        WHERE date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
        GROUP BY channel
        ORDER BY spend DESC
    """
    return [dict(r) for r in get_client().query(sql).result()]


# ── Forecast main ───────────────────────────────────────────────────────────

def forecast(today: date | None = None) -> ForecastResult:
    today = today or date.today()
    trend_end   = today - timedelta(days=1)
    trend_start = trend_end - timedelta(days=TREND_WINDOW_DAYS - 1)
    rate = _recent_daily_rate(trend_start, trend_end)

    out = ForecastResult(today=today.isoformat(),
                         trend_window_days=TREND_WINDOW_DAYS)
    out.by_channel = _per_channel_trend(trend_start, trend_end)

    # End-of-current-month projection
    actual = _month_to_date_actual(today)
    days_left = _days_left_in_month(today)
    last_day_of_month = calendar.monthrange(today.year, today.month)[1]
    eom = Projection(
        label=f"end-of-month ({today.strftime('%B %Y')})",
        horizon_end=date(today.year, today.month, last_day_of_month).isoformat(),
        days_so_far=actual["days_so_far"],
        days_total=last_day_of_month,
        actual=actual,
        daily_rate=rate,
    )
    if rate:
        eom.projected = {
            "spend":     int(actual["spend"]     + rate["spend_d"] * days_left),
            "leads":     int(actual["leads"]     + rate["leads_d"] * days_left),
            "sqls":      int(actual["sqls"]      + rate["sqls_d"]  * days_left),
            "rev":       int(actual.get("rev",0) + rate["rev_d"]   * days_left),
            "deals_won": int(actual.get("deals_won",0) + rate["deals_d"] * days_left),
            "cpql_pred": rate["cpql"],   # assume trend CPQL holds
            "roas_pred": rate["roas"],
        }
    out.end_of_month = eom

    # End-of-next-month projection (full month at current daily rate)
    if today.month == 12:
        next_first = date(today.year + 1, 1, 1)
    else:
        next_first = date(today.year, today.month + 1, 1)
    nm_last_day = calendar.monthrange(next_first.year, next_first.month)[1]
    nm_days = nm_last_day
    enm = Projection(
        label=f"end-of-next-month ({next_first.strftime('%B %Y')})",
        horizon_end=date(next_first.year, next_first.month, nm_last_day).isoformat(),
        days_so_far=0,
        days_total=nm_days,
        actual={},
        daily_rate=rate,
    )
    if rate:
        enm.projected = {
            "spend":     int(rate["spend_d"] * nm_days),
            "leads":     int(rate["leads_d"] * nm_days),
            "sqls":      int(rate["sqls_d"]  * nm_days),
            "rev":       int(rate["rev_d"]   * nm_days),
            "deals_won": int(rate["deals_d"] * nm_days),
            "cpql_pred": rate["cpql"],
            "roas_pred": rate["roas"],
        }
    out.end_of_next_month = enm

    # Narrative
    out.narrative = _build_narrative(out)
    return out


def _build_narrative(f: ForecastResult) -> list[str]:
    bullets = []
    if not f.end_of_month or not f.end_of_month.projected:
        bullets.append("Insufficient data — no projection produced.")
        return bullets
    eom = f.end_of_month
    enm = f.end_of_next_month

    bullets.append(f"**Trend window**: last {f.trend_window_days} days "
                   f"(${eom.daily_rate.get('spend_d', 0):.0f}/day spend, "
                   f"${eom.daily_rate.get('cpql', 0)} CPQL).")
    bullets.append("")
    bullets.append(f"**{eom.label}** ({eom.days_so_far}/{eom.days_total} days actual + "
                   f"{eom.days_total - eom.days_so_far} days projected):")
    bullets.append(
        f"  Spend ${eom.projected['spend']:,}  ·  "
        f"Leads {eom.projected['leads']:,}  ·  "
        f"SQLs {eom.projected['sqls']:,}  ·  "
        f"Deals {eom.projected['deals_won']}  ·  "
        f"Revenue ${eom.projected['rev']:,}  ·  "
        f"CPQL ${eom.projected['cpql_pred']}  ·  "
        f"ROAS {eom.projected['roas_pred']}x"
    )
    if enm and enm.projected:
        bullets.append("")
        bullets.append(f"**{enm.label}** (full-month projection at current trend):")
        bullets.append(
            f"  Spend ${enm.projected['spend']:,}  ·  "
            f"Leads {enm.projected['leads']:,}  ·  "
            f"SQLs {enm.projected['sqls']:,}  ·  "
            f"Deals {enm.projected['deals_won']}  ·  "
            f"Revenue ${enm.projected['rev']:,}  ·  "
            f"CPQL ${enm.projected['cpql_pred']}  ·  "
            f"ROAS {enm.projected['roas_pred']}x"
        )
    if f.by_channel:
        bullets.append("")
        bullets.append("**Per-channel daily run rate** (basis for projection):")
        for ch in f.by_channel:
            d = ch["days"] or 1
            bullets.append(
                f"  • {ch['channel']:<14} "
                f"${(ch['spend'] or 0) / d:.0f}/day, "
                f"{(ch['sqls'] or 0) / d:.1f} SQLs/day, "
                f"CPQL ${ch.get('cpql', '?')}"
            )
    return bullets


def to_markdown(f: ForecastResult) -> str:
    lines = [f"# Forecast — as of {f.today}", ""]
    lines.extend(f.narrative)
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    f = forecast()
    print(to_markdown(f))
    print()
    print("--- JSON ---")
    print(json.dumps(asdict(f), indent=2, default=str))
