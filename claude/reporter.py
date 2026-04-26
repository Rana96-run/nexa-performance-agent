"""
Daily report — data orchestrator.

Splits the report into two layers:

  1. **Deterministic data** (this module) — every chart, table, and KPI tile
     comes from BigQuery via parameterised SQL. No Claude in the loop, so
     numbers are exact.

  2. **Narrative** — one Claude call generates the headline, the "what
     changed" section, and a short paragraph per channel. Claude writes
     the prose; it never invents numbers.

The renderer (`reports/render.py`) takes the dict this module returns and
produces a single self-contained HTML file with embedded Plotly charts.

Failure-mode policy: every BQ helper returns an empty dict/list on error
and logs the reason. A single broken query cannot poison the whole report.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timezone, timedelta
from typing import Any

import anthropic
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
    QUAL_RATE_TARGET,
)
from claude.roles import load_prompt

_RIYADH = timezone(timedelta(hours=3))

# Channel display config — order, label, hex accent for charts
CHANNEL_DISPLAY = [
    ("google_ads",     "Google Ads",     "#4285F4"),
    ("meta",           "Meta",           "#1877F2"),
    ("snapchat",       "Snapchat",       "#FFFC00"),
    ("tiktok",         "TikTok",         "#000000"),
    ("linkedin",       "LinkedIn",       "#0A66C2"),
    ("microsoft_ads",  "Microsoft Ads",  "#00A4EF"),
]


# ---------------------------------------------------------------------------
# Low-level BQ helpers
# ---------------------------------------------------------------------------

def _bq():
    """Return (bigquery_client, query_module). None on failure."""
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        from google.cloud import bigquery
        return get_client(), bigquery, PROJECT_ID, DATASET
    except Exception as e:
        print(f"[reporter] BQ client unavailable: {e}")
        return None, None, None, None


def _query(sql: str, params: list | None = None) -> list[dict]:
    client, bq, _, _ = _bq()
    if not client:
        return []
    try:
        cfg = bq.QueryJobConfig(query_parameters=params or [])
        return [dict(r) for r in client.query(sql, job_config=cfg).result()]
    except Exception as e:
        print(f"[reporter] query failed: {e}\n  sql: {sql[:200]}...")
        return []


def _zone(value: float | None, scale: float, ok: float, warn: float, lower_is_better=True) -> str:
    """Map a metric value to a 4-zone label using config thresholds."""
    if value is None:
        return "no_data"
    if lower_is_better:
        if value < scale: return "scale"
        if value <= ok:    return "acceptable"
        if value <= warn:  return "warning"
        return "pause_zone"
    if value >= warn:  return "scale"
    if value >= ok:    return "acceptable"
    if value >= scale: return "warning"
    return "pause_zone"


# ---------------------------------------------------------------------------
# Data builders — each returns a chunk consumed by the renderer
# ---------------------------------------------------------------------------

def build_hero_kpis() -> dict:
    """Yesterday's totals + week-over-week deltas across all channels."""
    _, bq, project, dataset = _bq()
    if not bq:
        return {}
    end = date.today() - timedelta(days=1)
    sql = f"""
        WITH win AS (
          SELECT
            CASE
              WHEN date = @yesterday THEN 'today'
              WHEN date BETWEEN @prev_start AND @prev_end THEN 'prev'
              ELSE 'recent'
            END AS bucket,
            spend, leads, conversions, campaign_name, channel, date
          FROM `{project}.{dataset}.campaigns_daily`
          WHERE date BETWEEN @prev_start AND @yesterday
        )
        SELECT
          bucket,
          SUM(spend) AS spend,
          SUM(leads) AS leads,
          SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)) AS cpl
        FROM win
        WHERE bucket IN ('today','prev')
        GROUP BY bucket
    """
    rows = _query(sql, [
        bq.ScalarQueryParameter("yesterday", "DATE", end),
        bq.ScalarQueryParameter("prev_end",  "DATE", end - timedelta(days=7)),
        bq.ScalarQueryParameter("prev_start","DATE", end - timedelta(days=13)),
    ])
    today = next((r for r in rows if r["bucket"] == "today"), {})
    prev  = next((r for r in rows if r["bucket"] == "prev"),  {})

    def _delta(now, before):
        if not before or before == 0: return None
        return round(((now - before) / before) * 100, 1)

    spend_now = float(today.get("spend") or 0)
    spend_prev = float(prev.get("spend") or 0)
    leads_now = int(today.get("leads") or 0)
    leads_prev = int(prev.get("leads") or 0)
    cpl_now = today.get("cpl")
    cpl_prev = prev.get("cpl")

    # SQL counts from HubSpot leads
    sql_q = f"""
        SELECT
          SUM(IF(date = @yesterday, leads_qualified, 0)) AS sql_today,
          SUM(IF(date BETWEEN @prev_start AND @prev_end, leads_qualified, 0)) AS sql_prev
        FROM `{project}.{dataset}.hubspot_leads_module_daily`
        WHERE date BETWEEN @prev_start AND @yesterday
    """
    sql_rows = _query(sql_q, [
        bq.ScalarQueryParameter("yesterday", "DATE", end),
        bq.ScalarQueryParameter("prev_end",  "DATE", end - timedelta(days=7)),
        bq.ScalarQueryParameter("prev_start","DATE", end - timedelta(days=13)),
    ])
    sql_today = int((sql_rows[0] if sql_rows else {}).get("sql_today") or 0)
    sql_prev  = int((sql_rows[0] if sql_rows else {}).get("sql_prev")  or 0)
    cpql_now  = round(spend_now / sql_today, 2) if sql_today else None
    cpql_prev = round(spend_prev / sql_prev, 2) if sql_prev else None

    qual_rate_now  = round(sql_today / leads_now, 3) if leads_now else None
    qual_rate_prev = round(sql_prev  / leads_prev, 3) if leads_prev else None

    return {
        "date": end.isoformat(),
        "spend":     {"value": round(spend_now, 2), "delta_pct": _delta(spend_now, spend_prev)},
        "leads":     {"value": leads_now,           "delta_pct": _delta(leads_now, leads_prev)},
        "sql":       {"value": sql_today,           "delta_pct": _delta(sql_today, sql_prev)},
        "cpl":       {"value": round(float(cpl_now), 2) if cpl_now is not None else None,
                      "delta_pct": _delta(float(cpl_now or 0), float(cpl_prev or 0)),
                      "zone": _zone(float(cpl_now) if cpl_now is not None else None,
                                    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING)},
        "cpql":      {"value": cpql_now,
                      "delta_pct": _delta(cpql_now or 0, cpql_prev or 0),
                      "zone": _zone(cpql_now, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING)},
        "qual_rate": {"value": qual_rate_now,
                      "delta_pct": _delta((qual_rate_now or 0) * 100,
                                          (qual_rate_prev or 0) * 100),
                      "target": QUAL_RATE_TARGET},
    }


def build_trends_30d() -> list[dict]:
    """Per-day per-channel spend / leads / cpl for last 30 days. For trend charts."""
    _, bq, project, dataset = _bq()
    if not bq:
        return []
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    sql = f"""
        SELECT
          date, channel,
          SUM(spend) AS spend,
          SUM(leads) AS leads,
          SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)) AS cpl
        FROM `{project}.{dataset}.campaigns_daily`
        WHERE date BETWEEN @start AND @end
        GROUP BY date, channel
        ORDER BY date, channel
    """
    rows = _query(sql, [
        bq.ScalarQueryParameter("start", "DATE", start),
        bq.ScalarQueryParameter("end",   "DATE", end),
    ])
    return [
        {
            "date":    str(r["date"]),
            "channel": r["channel"],
            "spend":   round(float(r["spend"] or 0), 2),
            "leads":   int(r["leads"] or 0),
            "cpl":     round(float(r["cpl"]), 2) if r["cpl"] is not None else None,
        }
        for r in rows
    ]


def _utm_breakdown(
    project: str, dataset: str, bq, qoyod_src: str,
    start: date, end: date, dim: str,
) -> list[dict]:
    """
    Build a UTM-grain table joined with deals for one dimension
    (`lead_utm_campaign` | `lead_utm_audience` | `lead_utm_content`).

    Cost is attributed via campaign_name <-> utm_campaign match. For
    utm_audience / utm_content, cost is the SUM of cost across the
    parent utm_campaigns those leads came from (best-effort proxy).

    Columns returned per row:
      label, leads, qualified, disqualified, qual_rate, deals, deal_amount,
      cost, cpl, cpql, roas
    """
    deal_dim = dim.replace("lead_", "deal_")

    sql = f"""
        WITH leads AS (
          SELECT
            IFNULL({dim}, '(none)') AS label,
            ANY_VALUE(lead_utm_campaign) AS utm_campaign,
            SUM(leads_total)        AS leads,
            SUM(leads_qualified)    AS qualified,
            SUM(leads_disqualified) AS disqualified
          FROM `{project}.{dataset}.hubspot_leads_module_daily`
          WHERE qoyod_source = @qoyod_src
            AND date BETWEEN @start AND @end
          GROUP BY label
        ),
        deals AS (
          SELECT
            IFNULL({deal_dim}, '(none)') AS label,
            SUM(deals_total)  AS deals_total,
            SUM(deals_won)    AS deals_won,
            SUM(amount_won)   AS amount_won
          FROM `{project}.{dataset}.hubspot_deals_daily`
          WHERE qoyod_source = @qoyod_src
            AND date BETWEEN @start AND @end
          GROUP BY label
        ),
        camp_cost AS (
          SELECT campaign_name, SUM(spend) AS spend
          FROM `{project}.{dataset}.campaigns_daily`
          WHERE channel = @channel
            AND date BETWEEN @start AND @end
          GROUP BY campaign_name
        )
        SELECT
          l.label,
          l.leads, l.qualified, l.disqualified,
          SAFE_DIVIDE(l.qualified, NULLIF(l.leads, 0)) AS qual_rate,
          IFNULL(d.deals_won, 0)    AS deals,
          IFNULL(d.amount_won, 0.0) AS deal_amount,
          IFNULL(c.spend, 0.0)      AS cost
        FROM leads l
        LEFT JOIN deals d USING(label)
        LEFT JOIN camp_cost c ON c.campaign_name = l.utm_campaign
        WHERE l.leads > 0 OR IFNULL(d.deals_total, 0) > 0
        ORDER BY l.leads DESC
    """
    rows = _query(sql, [
        bq.ScalarQueryParameter("qoyod_src", "STRING", qoyod_src),
        bq.ScalarQueryParameter("channel",   "STRING", _channel_from_qoyod_source(qoyod_src)),
        bq.ScalarQueryParameter("start",     "DATE",   start),
        bq.ScalarQueryParameter("end",       "DATE",   end),
    ])
    out = []
    for r in rows:
        leads = int(r["leads"] or 0)
        qual  = int(r["qualified"] or 0)
        disq  = int(r["disqualified"] or 0)
        cost  = round(float(r["cost"] or 0), 2)
        deal_amt = round(float(r["deal_amount"] or 0), 2)
        cpl   = round(cost / leads, 2) if leads else None
        cpql  = round(cost / qual, 2)  if qual  else None
        roas  = round(deal_amt / cost, 2) if cost else None
        out.append({
            "label":       r["label"],
            "leads":       leads,
            "qualified":   qual,
            "disqualified": disq,
            "qual_rate":   round(float(r["qual_rate"]), 3) if r.get("qual_rate") is not None else None,
            "deals":       int(r["deals"] or 0),
            "deal_amount": deal_amt,
            "cost":        cost,
            "cpl":         cpl,
            "cpql":        cpql,
            "roas":        roas,
            "cpl_zone":    _zone(cpl,  CPL_SCALE,  CPL_ACCEPTABLE,  CPL_WARNING),
            "cpql_zone":   _zone(cpql, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING),
        })
    return out


def _disq_reason_breakdown(
    project: str, dataset: str, bq, qoyod_src: str,
    start: date, end: date,
) -> list[dict]:
    """Top disqualification reasons for this channel's leads in the window."""
    sql = f"""
        SELECT
          IFNULL(top_disq_reason, 'Unknown') AS reason,
          SUM(leads_disqualified)            AS count,
          SUM(leads_total)                   AS leads_total
        FROM `{project}.{dataset}.hubspot_leads_module_daily`
        WHERE qoyod_source = @qoyod_src
          AND date BETWEEN @start AND @end
          AND leads_disqualified > 0
        GROUP BY reason
        HAVING count > 0
        ORDER BY count DESC
        LIMIT 10
    """
    rows = _query(sql, [
        bq.ScalarQueryParameter("qoyod_src", "STRING", qoyod_src),
        bq.ScalarQueryParameter("start",     "DATE",   start),
        bq.ScalarQueryParameter("end",       "DATE",   end),
    ])
    return [
        {
            "reason": r["reason"],
            "count":  int(r["count"] or 0),
            "share":  round(float(r["count"] or 0) / float(r["leads_total"] or 1), 3),
        }
        for r in rows
    ]


def build_channel_section(channel_key: str, days: int = 7) -> dict:
    """
    Single channel block:
      - rollup KPIs
      - campaign table (cost, leads, qual, disqual, CPL, CPQL, deals, deal_amount, ROAS)
      - utm_campaign / utm_audience / utm_content tables
      - disqualification reasons table
      - placeholders flagging missing ad_group / ad grain
    """
    _, bq, project, dataset = _bq()
    if not bq:
        return {}
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    qoyod_src = _channel_to_qoyod_source(channel_key)
    p = [
        bq.ScalarQueryParameter("channel",   "STRING", channel_key),
        bq.ScalarQueryParameter("qoyod_src", "STRING", qoyod_src),
        bq.ScalarQueryParameter("start",     "DATE",   start),
        bq.ScalarQueryParameter("end",       "DATE",   end),
    ]

    # ── Channel rollup KPIs ──────────────────────────────────────────────────
    rollup_sql = f"""
        WITH cost AS (
          SELECT SUM(spend) AS spend, SUM(leads) AS platform_leads
          FROM `{project}.{dataset}.campaigns_daily`
          WHERE channel = @channel AND date BETWEEN @start AND @end
        ),
        crm AS (
          SELECT SUM(leads_total)        AS leads,
                 SUM(leads_qualified)    AS qualified,
                 SUM(leads_disqualified) AS disqualified
          FROM `{project}.{dataset}.hubspot_leads_module_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
        ),
        deals AS (
          SELECT SUM(deals_won)  AS deals,
                 SUM(amount_won) AS deal_amount
          FROM `{project}.{dataset}.hubspot_deals_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
        )
        SELECT cost.spend, cost.platform_leads, crm.leads, crm.qualified,
               crm.disqualified, deals.deals, deals.deal_amount
        FROM cost, crm, deals
    """
    rollup = _query(rollup_sql, p)
    r0     = rollup[0] if rollup else {}
    spend  = round(float(r0.get("spend") or 0), 2)
    leads_crm = int(r0.get("leads") or 0)
    qualified = int(r0.get("qualified") or 0)
    disqual   = int(r0.get("disqualified") or 0)
    deals     = int(r0.get("deals") or 0)
    deal_amt  = round(float(r0.get("deal_amount") or 0), 2)
    cpl  = round(spend / leads_crm, 2) if leads_crm else None
    cpql = round(spend / qualified, 2) if qualified else None
    roas = round(deal_amt / spend, 2)  if spend else None

    # ── Campaign table (full columns) ────────────────────────────────────────
    camp_sql = f"""
        WITH cost AS (
          SELECT campaign_name, SUM(spend) AS spend, SUM(leads) AS platform_leads
          FROM `{project}.{dataset}.campaigns_daily`
          WHERE channel = @channel AND date BETWEEN @start AND @end
          GROUP BY campaign_name
        ),
        crm AS (
          SELECT lead_utm_campaign AS campaign_name,
                 SUM(leads_total) AS leads,
                 SUM(leads_qualified) AS qualified,
                 SUM(leads_disqualified) AS disqualified
          FROM `{project}.{dataset}.hubspot_leads_module_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
          GROUP BY campaign_name
        ),
        deals AS (
          SELECT deal_utm_campaign AS campaign_name,
                 SUM(deals_won) AS deals_won,
                 SUM(amount_won) AS amount_won
          FROM `{project}.{dataset}.hubspot_deals_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
          GROUP BY campaign_name
        )
        SELECT
          cost.campaign_name,
          IFNULL(cost.spend, 0)             AS spend,
          IFNULL(crm.leads, 0)              AS leads,
          IFNULL(crm.qualified, 0)          AS qualified,
          IFNULL(crm.disqualified, 0)       AS disqualified,
          IFNULL(deals.deals_won, 0)        AS deals,
          IFNULL(deals.amount_won, 0)       AS deal_amount
        FROM cost
        LEFT JOIN crm   ON crm.campaign_name   = cost.campaign_name
        LEFT JOIN deals ON deals.campaign_name = cost.campaign_name
        WHERE cost.spend > 0
        ORDER BY cost.spend DESC
    """
    camp_rows = _query(camp_sql, p)
    campaigns = []
    for c in camp_rows:
        s  = round(float(c["spend"] or 0), 2)
        l  = int(c["leads"] or 0)
        q  = int(c["qualified"] or 0)
        ds = int(c["deals"] or 0)
        da = round(float(c["deal_amount"] or 0), 2)
        c_cpl  = round(s / l, 2) if l else None
        c_cpql = round(s / q, 2) if q else None
        c_roas = round(da / s, 2) if s else None
        campaigns.append({
            "campaign":     c["campaign_name"],
            "cost":         s,
            "leads":        l,
            "qualified":    q,
            "disqualified": int(c["disqualified"] or 0),
            "cpl":          c_cpl,
            "cpql":         c_cpql,
            "deals":        ds,
            "deal_amount":  da,
            "roas":         c_roas,
            "cpl_zone":     _zone(c_cpl,  CPL_SCALE,  CPL_ACCEPTABLE,  CPL_WARNING),
            "cpql_zone":    _zone(c_cpql, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING),
        })
    top_campaigns    = campaigns[:8]
    bottom_campaigns = sorted(
        campaigns,
        key=lambda c: ((c["cpl"] if c["cpl"] is not None else 1e9), -c["cost"]),
        reverse=True,
    )[:5]

    # ── UTM-grain tables ────────────────────────────────────────────────────
    utm_campaign = _utm_breakdown(project, dataset, bq, qoyod_src, start, end, "lead_utm_campaign")
    utm_audience = _utm_breakdown(project, dataset, bq, qoyod_src, start, end, "lead_utm_audience")
    utm_content  = _utm_breakdown(project, dataset, bq, qoyod_src, start, end, "lead_utm_content")

    # ── Disqualification reasons ────────────────────────────────────────────
    disq_reasons = _disq_reason_breakdown(project, dataset, bq, qoyod_src, start, end)

    return {
        "channel":  channel_key,
        "window_days": days,
        "kpis": {
            "spend":        spend,
            "leads":        leads_crm,
            "qualified":    qualified,
            "disqualified": disqual,
            "deals":        deals,
            "deal_amount":  deal_amt,
            "cpl":          cpl,
            "cpql":         cpql,
            "roas":         roas,
            "cpl_zone":     _zone(cpl,  CPL_SCALE,  CPL_ACCEPTABLE,  CPL_WARNING),
            "cpql_zone":    _zone(cpql, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING),
        },
        "campaigns":         campaigns,
        "top_campaigns":     top_campaigns,
        "bottom_campaigns":  bottom_campaigns,
        "utm_campaign":      utm_campaign,
        "utm_audience":      utm_audience,
        "utm_content":       utm_content,
        "disq_reasons":      disq_reasons,
        # Grain we don't yet collect — surfaced in render with a "data pending" badge
        "ad_groups": {"available": False,
                      "note": "ad_group grain not yet in BQ — needs adgroups_daily collector"},
        "ads":       {"available": False,
                      "note": "ad grain not yet in BQ — needs ads_daily collector"},
    }


def _channel_from_qoyod_source(qoyod_src: str) -> str:
    """Inverse of _channel_to_qoyod_source for cross-table joins.
    Verified live HubSpot qoyod_source values:
      'Google Ads', 'Meta Ads', 'Snapchat Ads', 'Tiktok Ads',
      'LinkedIn Ads', 'Microsoft Ads', 'Direct Traffic', 'Email Marketing',
      'Offline', 'Other'
    """
    return {
        "Google Ads":    "google_ads",
        "Meta Ads":      "meta",
        "Snapchat Ads":  "snapchat",
        "Tiktok Ads":    "tiktok",
        "TikTok Ads":    "tiktok",
        "LinkedIn Ads":  "linkedin",
        "Microsoft Ads": "microsoft_ads",
    }.get(qoyod_src, qoyod_src)


def _channel_to_qoyod_source(channel_key: str) -> str:
    """Map our channel keys → HubSpot's actual qoyod_source label.
    HubSpot writes 'Google Ads', 'Meta Ads', etc. — NOT 'google' / 'facebook'.
    """
    return {
        "google_ads":    "Google Ads",
        "meta":          "Meta Ads",
        "snapchat":      "Snapchat Ads",
        "tiktok":        "Tiktok Ads",
        "linkedin":      "LinkedIn Ads",
        "microsoft_ads": "Microsoft Ads",
    }.get(channel_key, channel_key)


# ---------------------------------------------------------------------------
# Narrative — one Claude call covering overview + per-channel paragraphs
# ---------------------------------------------------------------------------

def build_narrative(
    cadence: str,
    role_results: list,
    hero: dict,
    channels: list[dict],
) -> dict:
    """Return {"headline": str, "what_changed": [str], "why": str, "channel_narratives": {channel: str}}."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = load_prompt("daily_report")

    trimmed_roles = []
    for r in role_results or []:
        trimmed_roles.append({
            "role":     r.get("role"),
            "decision": r.get("decision") or {},
            "summary":  (r.get("raw_response") or "")[:1200],
        })

    user_msg = (
        f"cadence: {cadence}\n"
        f"hero KPIs (yesterday + WoW deltas):\n{json.dumps(hero, indent=2, default=str)}\n\n"
        f"per-channel data (last 7 days):\n{json.dumps(channels, indent=2, default=str)}\n\n"
        f"role outputs from this morning's run:\n{json.dumps(trimmed_roles, indent=2, default=str)}\n\n"
        "Return a single JSON object with exactly these keys:\n"
        '  "headline": one-sentence summary, lead with the most important number\n'
        '  "what_changed": list of 3-6 short bullet strings\n'
        '  "why": 2-4 short paragraphs of narrative explaining the drivers\n'
        '  "channel_narratives": {channel_key: "1 short paragraph per channel"}\n'
        "Channel keys must match: google_ads, meta, snapchat, tiktok, linkedin, microsoft_ads. "
        "Only include channels that have spend > 0 in the data above. "
        "Do not invent numbers — every figure must come from the data provided."
    )

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = msg.content[0].text

    # Extract JSON. Prefer fenced block; fall back to first { ... }.
    import re
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(m.group(1) if m and m.lastindex else m.group(0)) if m else {}
    except Exception as e:
        print(f"[reporter] narrative JSON parse failed: {e}")
        return {"headline": "", "what_changed": [], "why": text[:800], "channel_narratives": {}}


# ---------------------------------------------------------------------------
# Top-level entry — assemble everything the renderer needs
# ---------------------------------------------------------------------------

def assemble_report_data(
    cadence: str,
    role_results: list,
    tasks_created: list,
    approvals_pending: list,
    permalink: str = "/reports/latest",
) -> dict:
    """
    Build the complete data bundle the renderer expects.

    Pre-computes three date windows so the UI can switch without a backend
    round-trip:
      - yesterday (1d)   — most recent day only
      - last_7d          — rolling 7-day default
      - last_30d         — rolling 30-day deep-dive

    The renderer embeds all three as JSON; JS swaps which window is visible.
    """
    hero   = build_hero_kpis()
    trends = build_trends_30d()  # 30 days — UI slices this client-side

    # Channels that have spend in any recent period (use 30d scan)
    spending_channels = {row["channel"] for row in trends if (row["spend"] or 0) > 0}

    # Build channel metadata (label + color) for all active channels
    active_channels_meta = {
        key: {"label": label, "color": color}
        for key, label, color in CHANNEL_DISPLAY
        if key in spending_channels
    }

    # Pre-compute 3 windows per channel
    windows = {}
    for days, window_key in [(1, "yesterday"), (7, "last_7d"), (30, "last_30d")]:
        window_channels = []
        for key in [k for k, _, _ in CHANNEL_DISPLAY if k in spending_channels]:
            section = build_channel_section(key, days=days)
            meta = active_channels_meta[key]
            section["label"] = meta["label"]
            section["color"] = meta["color"]
            window_channels.append(section)
        windows[window_key] = window_channels

    # Narrative uses the 7d window (default view)
    channels_7d = windows["last_7d"]
    narrative = build_narrative(cadence, role_results, hero, channels_7d)

    # Stitch narrative paragraph into all three windows
    ch_narratives = narrative.get("channel_narratives") or {}
    for wk in ("yesterday", "last_7d", "last_30d"):
        for ch in windows[wk]:
            ch["narrative"] = ch_narratives.get(ch["channel"], "")

    return {
        "generated_at":      datetime.now(_RIYADH).strftime("%Y-%m-%d %H:%M Riyadh"),
        "report_date":       hero.get("date") or (date.today() - timedelta(days=1)).isoformat(),
        "cadence":           cadence,
        "permalink":         permalink,
        "hero":              hero,
        "headline":          narrative.get("headline", ""),
        "what_changed":      narrative.get("what_changed", []),
        "why":               narrative.get("why", ""),
        "trends_30d":        trends,
        "windows":           windows,
        # Kept for backward-compat with any callers that expect "channels"
        "channels":          channels_7d,
        "decisions":         _decisions_taken(role_results),
        "approvals_pending": approvals_pending or [],
        "tasks_created":     tasks_created or [],
        "thresholds": {
            "cpl":  {"scale": CPL_SCALE,  "acceptable": CPL_ACCEPTABLE,  "warning": CPL_WARNING},
            "cpql": {"scale": CPQL_SCALE, "acceptable": CPQL_ACCEPTABLE, "warning": CPQL_WARNING},
            "qual_rate_target": QUAL_RATE_TARGET,
        },
    }


def _decisions_taken(role_results: list) -> list[dict]:
    """Pull autonomous actions from the media_buyer's decision."""
    out = []
    for r in role_results or []:
        if r.get("role") != "media_buyer":
            continue
        d = r.get("decision") or {}
        if d.get("action") and d.get("action").lower() != "recommend":
            out.append({
                "channel":  d.get("channel"),
                "action":   d.get("action"),
                "campaign": d.get("campaign"),
                "reason":   d.get("reason"),
            })
    return out
