"""Period-over-period auto-comparator — codifies the Apr-vs-May-style audit
that's currently done manually. Runs in the weekly + monthly cadences.

For every comparison it produces:
- Headline diff (spend, leads, SQLs, CPQL, ROAS, qual rate)
- Per-channel shifts
- Top winners + top losers at campaign level
- New campaigns launched in period B (and how they performed)
- Silent deaths (active in A, ~zero in B)
- Quality shifts (disqualification reasons)
- Narrative bullet points ready for Slack / Asana / LLM summarisation

Read-only — produces a structured dict + a markdown narrative.
Downstream: notifications/, executors/asana.py for Asana tasks.

Run from CLI:
    railway run python -m analysers.period_compare --weekly
    railway run python -m analysers.period_compare --monthly
    railway run python -m analysers.period_compare --custom 2026-04-01:2026-04-16 2026-05-01:2026-05-16
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Optional

from collectors.bq_writer import get_client, PROJECT_ID, DATASET

DS = f"`{PROJECT_ID}.{DATASET}`"


# ── Output schema ───────────────────────────────────────────────────────────

@dataclass
class MetricDelta:
    name:      str
    period_a:  float | None
    period_b:  float | None
    delta_abs: float | None
    delta_pct: float | None

    def fmt(self, unit: str = "$") -> str:
        if self.period_a is None and self.period_b is None: return "—"
        a = f"{unit}{int(self.period_a):,}" if self.period_a is not None and unit == "$" else f"{self.period_a}"
        b = f"{unit}{int(self.period_b):,}" if self.period_b is not None and unit == "$" else f"{self.period_b}"
        return f"{a} → {b} ({self.delta_pct:+.0f}%)" if self.delta_pct is not None else f"{a} → {b}"


@dataclass
class PeriodCompare:
    period_a:           tuple[str, str]
    period_b:           tuple[str, str]
    days_a:             int
    days_b:             int
    label:              str
    headline:           dict        = field(default_factory=dict)
    by_channel:         list[dict]  = field(default_factory=list)
    top_losers:         list[dict]  = field(default_factory=list)
    top_winners:        list[dict]  = field(default_factory=list)
    new_launches:       list[dict]  = field(default_factory=list)
    silent_deaths:      list[dict]  = field(default_factory=list)
    quality_shifts:     dict        = field(default_factory=dict)
    narrative:          list[str]   = field(default_factory=list)
    flags:              list[str]   = field(default_factory=list)  # "CPQL_REGRESSED", "QUAL_DROP", etc.


# ── Helpers ─────────────────────────────────────────────────────────────────

def _delta(a: float | None, b: float | None) -> tuple[float | None, float | None]:
    """Returns (delta_abs, delta_pct)."""
    if a is None and b is None: return None, None
    a = a or 0
    b = b or 0
    abs_ = b - a
    pct  = (abs_ / a * 100) if a else None
    return abs_, pct


def _bq_rows(sql: str) -> list[dict]:
    return [dict(r) for r in get_client().query(sql).result()]


# ── Core comparison ─────────────────────────────────────────────────────────

def compare(period_a: tuple[str, str],
            period_b: tuple[str, str],
            label: str = "ad-hoc") -> PeriodCompare:
    """The headline function. Returns a fully populated PeriodCompare."""
    a_start, a_end = period_a
    b_start, b_end = period_b
    days_a = (date.fromisoformat(a_end) - date.fromisoformat(a_start)).days + 1
    days_b = (date.fromisoformat(b_end) - date.fromisoformat(b_start)).days + 1

    out = PeriodCompare(period_a=period_a, period_b=period_b,
                        days_a=days_a, days_b=days_b, label=label)

    # 1. Headline — lag-aware CPQL
    sql = f"""
        WITH base AS (
          SELECT
            CASE
              WHEN date BETWEEN '{a_start}' AND '{a_end}' THEN 'A'
              WHEN date BETWEEN '{b_start}' AND '{b_end}' THEN 'B'
            END AS p,
            date, channel, spend, leads_total, leads_qualified AS qualified,
            leads_disqualified AS disqualified,
            leads_open, all_deals_won AS deals_won, all_revenue_won AS revenue_won
          FROM {DS}.wide_ads
          WHERE date BETWEEN '{a_start}' AND '{b_end}'
        )
        SELECT p,
          ROUND(SUM(spend), 0)         AS spend,
          SUM(leads_total)             AS leads,
          SUM(qualified)               AS sqls,
          SUM(disqualified)            AS disq,
          SUM(deals_won)               AS deals_won,
          ROUND(SUM(revenue_won), 0)   AS rev_won,
          ROUND(SAFE_DIVIDE(SUM(spend), SUM(leads_total)), 2)    AS cpl,
          ROUND(SAFE_DIVIDE(
            SUM(IF(SAFE_DIVIDE(COALESCE(leads_open,0), NULLIF(leads_total,0)) <= 0.30
                    OR leads_total = 0, spend, 0)),
            NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(leads_open,0), NULLIF(leads_total,0)) <= 0.30
                           OR leads_total = 0, qualified, 0)), 0)
          ), 2) AS cpql_lag_aware,
          ROUND(SAFE_DIVIDE(SUM(qualified), SUM(leads_total))*100, 1) AS qual_pct,
          ROUND(SAFE_DIVIDE(SUM(revenue_won), SUM(spend)), 2)    AS roas
        FROM base WHERE p IS NOT NULL
        GROUP BY p
    """
    rows = {r["p"]: r for r in _bq_rows(sql)}
    a = rows.get("A", {})
    b = rows.get("B", {})
    for k, unit in [("spend","$"), ("leads",""), ("sqls",""), ("disq",""),
                    ("deals_won",""), ("rev_won","$"), ("cpl","$"),
                    ("cpql_lag_aware","$"), ("qual_pct","%"), ("roas","x")]:
        av = a.get(k)
        bv = b.get(k)
        abs_, pct_ = _delta(
            float(av) if av is not None else None,
            float(bv) if bv is not None else None
        )
        out.headline[k] = asdict(MetricDelta(
            name=k, period_a=av, period_b=bv, delta_abs=abs_, delta_pct=pct_
        ))

    # 2. Per-channel shifts
    sql = f"""
        WITH base AS (
          SELECT
            CASE
              WHEN date BETWEEN '{a_start}' AND '{a_end}' THEN 'A'
              WHEN date BETWEEN '{b_start}' AND '{b_end}' THEN 'B'
            END AS p,
            channel, date, spend, leads_total,
            leads_qualified AS qualified,
            all_deals_won AS deals_won,
            all_revenue_won AS revenue_won,
            leads_open
          FROM {DS}.wide_ads
          WHERE date BETWEEN '{a_start}' AND '{b_end}'
        )
        SELECT channel, p,
          ROUND(SUM(spend), 0)         AS spend,
          SUM(leads_total)             AS leads,
          SUM(qualified)               AS sqls,
          ROUND(SAFE_DIVIDE(
            SUM(IF(SAFE_DIVIDE(COALESCE(leads_open,0), NULLIF(leads_total,0)) <= 0.30
                    OR leads_total = 0, spend, 0)),
            NULLIF(SUM(IF(SAFE_DIVIDE(COALESCE(leads_open,0), NULLIF(leads_total,0)) <= 0.30
                           OR leads_total = 0, qualified, 0)), 0)
          ), 1) AS cpql,
          ROUND(SAFE_DIVIDE(SUM(revenue_won), SUM(spend)), 2) AS roas
        FROM base WHERE p IS NOT NULL
        GROUP BY channel, p
        ORDER BY channel, p
    """
    by_ch_rows = _bq_rows(sql)
    channels = {r["channel"] for r in by_ch_rows}
    for ch in sorted(channels):
        a_r = next((r for r in by_ch_rows if r["channel"] == ch and r["p"] == "A"), None)
        b_r = next((r for r in by_ch_rows if r["channel"] == ch and r["p"] == "B"), None)
        entry = {"channel": ch, "a": a_r, "b": b_r,
                 "spend_delta_pct": None, "cpql_delta_pct": None}
        if a_r and b_r:
            _, sp_pct  = _delta(a_r.get("spend"), b_r.get("spend"))
            _, cq_pct  = _delta(a_r.get("cpql"),  b_r.get("cpql"))
            entry["spend_delta_pct"] = sp_pct
            entry["cpql_delta_pct"]  = cq_pct
        out.by_channel.append(entry)

    # 3. Top losers + winners at campaign level (min spend $500 in A)
    sql = f"""
        WITH a AS (
          SELECT channel, campaign_id, ANY_VALUE(campaign_name) AS campaign_name,
                 SUM(spend) AS spend, SUM(leads_qualified) AS sqls
          FROM {DS}.wide_ads
          WHERE date BETWEEN '{a_start}' AND '{a_end}'
          GROUP BY channel, campaign_id
        ),
        b AS (
          SELECT channel, campaign_id,
                 SUM(spend) AS spend, SUM(leads_qualified) AS sqls
          FROM {DS}.wide_ads
          WHERE date BETWEEN '{b_start}' AND '{b_end}'
          GROUP BY channel, campaign_id
        )
        SELECT a.channel, a.campaign_name,
               ROUND(a.spend, 0) AS spend_a, a.sqls AS sqls_a,
               ROUND(SAFE_DIVIDE(a.spend, NULLIF(a.sqls,0)), 1) AS cpql_a,
               ROUND(COALESCE(b.spend, 0), 0) AS spend_b, COALESCE(b.sqls, 0) AS sqls_b,
               ROUND(SAFE_DIVIDE(b.spend, NULLIF(b.sqls,0)), 1) AS cpql_b
        FROM a LEFT JOIN b USING (channel, campaign_id)
        WHERE a.spend > 500 AND a.sqls >= 2
    """
    rows = _bq_rows(sql)
    def _cpql_delta_abs(r):
        a_, b_ = r.get("cpql_a"), r.get("cpql_b")
        if a_ is None: return None
        if b_ is None: return 9999  # campaign died; treat as big regression
        return b_ - a_
    rows_sorted = sorted(rows, key=lambda r: (_cpql_delta_abs(r) or 0), reverse=True)
    out.top_losers  = [r for r in rows_sorted[:10] if (_cpql_delta_abs(r) or 0) > 10]
    out.top_winners = [r for r in rows_sorted[-10:] if (_cpql_delta_abs(r) or 0) < -10]

    # 4. New launches in B that weren't in A
    sql = f"""
        WITH a AS (
          SELECT DISTINCT channel, campaign_id FROM {DS}.campaigns_daily
          WHERE date BETWEEN '{a_start}' AND '{a_end}' AND spend > 0
        ),
        b AS (
          SELECT channel, campaign_id, ANY_VALUE(campaign_name) AS campaign_name,
                 SUM(spend) AS spend, MIN(date) AS first_day
          FROM {DS}.campaigns_daily
          WHERE date BETWEEN '{b_start}' AND '{b_end}' AND spend > 10
          GROUP BY channel, campaign_id
        )
        SELECT b.channel, b.campaign_name, b.first_day,
               ROUND(b.spend, 0) AS spend
        FROM b LEFT JOIN a USING (channel, campaign_id)
        WHERE a.campaign_id IS NULL
        ORDER BY spend DESC
        LIMIT 15
    """
    out.new_launches = _bq_rows(sql)

    # 5. Silent deaths (had spend in A, ~zero in B)
    sql = f"""
        WITH a AS (
          SELECT channel, campaign_id, ANY_VALUE(campaign_name) AS campaign_name,
                 SUM(spend) AS spend_a
          FROM {DS}.campaigns_daily
          WHERE date BETWEEN '{a_start}' AND '{a_end}'
          GROUP BY channel, campaign_id
          HAVING spend_a > 200
        ),
        b AS (
          SELECT channel, campaign_id, SUM(spend) AS spend_b
          FROM {DS}.campaigns_daily
          WHERE date BETWEEN '{b_start}' AND '{b_end}'
          GROUP BY channel, campaign_id
        )
        SELECT a.channel, a.campaign_name,
               ROUND(a.spend_a, 0) AS spend_a,
               ROUND(COALESCE(b.spend_b, 0), 0) AS spend_b
        FROM a LEFT JOIN b USING (channel, campaign_id)
        WHERE COALESCE(b.spend_b, 0) < a.spend_a * 0.05
        ORDER BY spend_a DESC
        LIMIT 10
    """
    out.silent_deaths = _bq_rows(sql)

    # 6. Quality shifts — disqualification reasons
    sql = f"""
        WITH x AS (
          SELECT
            CASE
              WHEN date BETWEEN '{a_start}' AND '{a_end}' THEN 'A'
              WHEN date BETWEEN '{b_start}' AND '{b_end}' THEN 'B'
            END AS p,
            COALESCE(top_disq_reason, '(none)') AS reason,
            SUM(leads_disqualified) AS disq
          FROM {DS}.hubspot_leads_module_daily
          WHERE date BETWEEN '{a_start}' AND '{b_end}'
          GROUP BY p, reason
        )
        SELECT reason,
          SUM(IF(p='A', disq, 0)) AS disq_a,
          SUM(IF(p='B', disq, 0)) AS disq_b
        FROM x WHERE p IS NOT NULL
        GROUP BY reason
        HAVING (disq_a + disq_b) > 10
        ORDER BY disq_b DESC
        LIMIT 12
    """
    out.quality_shifts["top_reasons"] = _bq_rows(sql)

    # 7. Build narrative + flags
    _build_narrative(out)

    return out


def _build_narrative(p: PeriodCompare) -> None:
    """Convert structured data into human-readable bullets + flags."""
    bullets, flags = p.narrative, p.flags
    h = p.headline

    def md(k): return h.get(k, {}).get("delta_pct")
    def va(k): return h.get(k, {}).get("period_a")
    def vb(k): return h.get(k, {}).get("period_b")

    # Headline
    if md("spend") is not None and md("cpql_lag_aware") is not None:
        bullets.append(
            f"Spend {md('spend'):+.0f}% (${int(va('spend') or 0):,} → ${int(vb('spend') or 0):,}) · "
            f"Leads {md('leads'):+.0f}% · "
            f"SQLs {md('sqls'):+.0f}% · "
            f"**CPQL {md('cpql_lag_aware'):+.0f}%** (${va('cpql_lag_aware')} → ${vb('cpql_lag_aware')}) · "
            f"ROAS {va('roas')}x → {vb('roas')}x"
        )

    # Flags — auto-detect regressions
    if md("cpql_lag_aware") is not None and md("cpql_lag_aware") > 15:
        flags.append("CPQL_REGRESSED")
        bullets.append(f"⚠ CPQL regressed by {md('cpql_lag_aware'):+.0f}% — investigate which campaigns drove it.")
    if md("roas") is not None and md("roas") < -25:
        flags.append("ROAS_REGRESSED")
    if md("qual_pct") is not None and md("qual_pct") < -10:
        flags.append("QUAL_DROPPED")
        bullets.append(
            f"⚠ Qualification rate dropped {md('qual_pct'):+.1f}pp "
            f"({va('qual_pct')}% → {vb('qual_pct')}%) — lead quality declining."
        )

    # Per-channel
    for ch in p.by_channel:
        if ch.get("cpql_delta_pct") is None: continue
        if abs(ch["cpql_delta_pct"]) < 15: continue
        a, b = ch["a"], ch["b"]
        bullets.append(
            f"{ch['channel']}: spend ${int(a['spend']):,}→${int(b['spend']):,} "
            f"({ch['spend_delta_pct']:+.0f}%), CPQL ${a['cpql']}→${b['cpql']} "
            f"({ch['cpql_delta_pct']:+.0f}%)"
        )

    # Top losers
    if p.top_losers:
        bullets.append(f"Top {len(p.top_losers)} CPQL regressions:")
        for r in p.top_losers[:5]:
            bullets.append(
                f"  • {r['campaign_name']} ({r['channel']}): "
                f"${r.get('cpql_a','?')}→${r.get('cpql_b','?')}, "
                f"spend ${int(r.get('spend_a', 0)):,}→${int(r.get('spend_b', 0)):,}"
            )

    # Silent deaths
    if p.silent_deaths:
        bullets.append(f"Silent deaths ({len(p.silent_deaths)}):")
        for r in p.silent_deaths[:5]:
            bullets.append(
                f"  • {r['campaign_name']} ({r['channel']}): "
                f"${int(r['spend_a']):,} → ${int(r['spend_b']):,}"
            )

    # New launches with their cost
    if p.new_launches:
        bullets.append(f"New launches in period B ({len(p.new_launches)}):")
        for r in p.new_launches[:5]:
            bullets.append(
                f"  • {r['campaign_name']} ({r['channel']}, first {r['first_day']}): "
                f"${int(r['spend']):,}"
            )
        if len(p.new_launches) >= 3:
            flags.append("LAUNCH_WAVE")

    # Quality shifts
    reasons = p.quality_shifts.get("top_reasons", [])
    surged = [r for r in reasons if r.get("disq_b", 0) > (r.get("disq_a", 0) or 0) * 2
              and r.get("disq_b", 0) > 20]
    if surged:
        bullets.append("Disqualification reasons that surged 2×+:")
        for r in surged[:5]:
            bullets.append(
                f"  • '{r['reason']}': {r['disq_a']} → {r['disq_b']}"
            )


# ── Standard cadence wrappers ───────────────────────────────────────────────

def compare_weekly() -> PeriodCompare:
    """Last 7 days vs prior 7 days."""
    today = date.today()
    b_end = today - timedelta(days=1)
    b_start = b_end - timedelta(days=6)
    a_end = b_start - timedelta(days=1)
    a_start = a_end - timedelta(days=6)
    return compare((a_start.isoformat(), a_end.isoformat()),
                   (b_start.isoformat(), b_end.isoformat()),
                   label="weekly (last 7d vs prior 7d)")


def compare_monthly() -> PeriodCompare:
    """Current month-to-date vs same number of days from previous month."""
    today    = date.today()
    b_start  = today.replace(day=1)
    b_end    = today - timedelta(days=1)
    days_in_b = (b_end - b_start).days + 1
    prev_month_last_day = b_start - timedelta(days=1)
    a_start  = prev_month_last_day.replace(day=1)
    a_end    = a_start + timedelta(days=days_in_b - 1)
    return compare((a_start.isoformat(), a_end.isoformat()),
                   (b_start.isoformat(), b_end.isoformat()),
                   label="monthly (current MTD vs same days prev month)")


# ── Output formats ──────────────────────────────────────────────────────────

def to_markdown(p: PeriodCompare) -> str:
    """Slack/Asana-ready markdown."""
    lines = [
        f"# Period comparison — {p.label}",
        f"**Period A**: {p.period_a[0]} → {p.period_a[1]} ({p.days_a}d)",
        f"**Period B**: {p.period_b[0]} → {p.period_b[1]} ({p.days_b}d)",
        "",
    ]
    if p.flags:
        lines.append(f"**Flags**: {', '.join(p.flags)}")
        lines.append("")
    lines.extend(p.narrative)
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    arg = sys.argv[1] if len(sys.argv) > 1 else "--weekly"
    if arg == "--weekly":
        p = compare_weekly()
    elif arg == "--monthly":
        p = compare_monthly()
    elif arg == "--custom" and len(sys.argv) >= 4:
        a = tuple(sys.argv[2].split(":"))
        b = tuple(sys.argv[3].split(":"))
        p = compare(a, b, label="custom")
    else:
        print("Usage: period_compare [--weekly|--monthly|--custom A_start:A_end B_start:B_end]")
        sys.exit(1)
    print(to_markdown(p))
    print()
    print("--- JSON (machine-readable) ---")
    print(json.dumps(asdict(p), indent=2, default=str))
