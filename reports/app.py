"""
reports/app.py
==============
Tiny Flask server that:
  GET  /                       → redirect to /reports/latest
  GET  /reports/latest         → serve the most-recent pre-rendered HTML
  GET  /reports/<date>         → serve a specific dated HTML  (e.g. /reports/2026-04-25)
  GET  /api/report             → custom date range: ?start=YYYY-MM-DD&end=YYYY-MM-DD
                                 runs assemble_report_data live against BQ, returns JSON
                                 (front-end JS patches window.NEXA_DATA.windows['custom'])

Deploy on Railway alongside the agent (single dyno, one process via Procfile).

Usage (local):
    python -m reports.app
"""
from __future__ import annotations

import json
import os
from datetime import datetime, date
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, abort
from collectors.hubspot_webhook import hubspot_bp
from collectors.zapier_webhook import zapier_bp

REPORTS_DIR = Path(__file__).parent
app = Flask(__name__)
app.register_blueprint(hubspot_bp)
app.register_blueprint(zapier_bp)


# ─── Static report pages ──────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


_REFRESH_STATUS: dict = {"running": False, "started_at": None,
                          "finished_at": None, "result": None, "error": None}


def _do_refresh(days: int | None, backfill: bool):
    """Run refresh + regen, recording status to _REFRESH_STATUS for polling."""
    import threading
    from datetime import datetime as _dt
    from reporting_scheduler import run_refresh
    from claude.reporter import assemble_report_data
    from reports.render import save_report

    _REFRESH_STATUS.update({
        "running": True, "started_at": _dt.utcnow().isoformat() + "Z",
        "finished_at": None, "result": None, "error": None,
    })
    try:
        if days:
            results = run_refresh(days=days)
        else:
            results = run_refresh(incremental=not backfill)
        report = assemble_report_data(
            cadence="on_demand", role_results=[], tasks_created=[],
            approvals_pending=[], permalink="/reports/latest",
        )
        save_report(report)
        _REFRESH_STATUS["result"] = {
            "collectors": {k: ("ok" if v[0] else "fail") for k, v in results.items()},
            "channels": [c.get("channel") for c in report.get("channels", [])],
            "trends_rows": len(report.get("trends_30d", [])),
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        _REFRESH_STATUS["error"] = str(e)
    finally:
        from datetime import datetime as _dt
        _REFRESH_STATUS["finished_at"] = _dt.utcnow().isoformat() + "Z"
        _REFRESH_STATUS["running"] = False


@app.route("/api/refresh", methods=["POST", "GET"])
def refresh_bq():
    """
    Kick off a BigQuery refresh + view rebuild + report regen.
    Runs in the background so the HTTP response returns immediately.
    Poll /api/refresh/status to check progress.

    Query params:
      ?days=N       Backfill last N days for every collector (e.g. 14, 30).
      ?backfill=1   Full historical backfill (very slow).
      Without args  Incremental refresh — last 2 days only.
    """
    import threading
    expected = os.getenv("REGEN_TOKEN")
    if expected and request.args.get("token") != expected:
        return jsonify({"error": "unauthorized"}), 401
    if _REFRESH_STATUS.get("running"):
        return jsonify({"queued": False, "reason": "another refresh is already running",
                        "status": _REFRESH_STATUS}), 409

    backfill = request.args.get("backfill") == "1"
    days_arg = request.args.get("days")
    days = int(days_arg) if days_arg and days_arg.isdigit() else None
    threading.Thread(target=_do_refresh, args=(days, backfill), daemon=True).start()
    return jsonify({
        "queued": True,
        "mode": "backfill" if backfill else (f"days={days}" if days else "incremental"),
        "poll": "/api/refresh/status",
    })


@app.route("/api/refresh/status")
def refresh_status():
    return jsonify(_REFRESH_STATUS)


@app.route("/api/regenerate", methods=["POST", "GET"])
def regenerate():
    """
    Regenerate the daily HTML report on demand using current BigQuery data.
    Light-weight (no Claude calls — just data fetch + render).
    Auth: pass ?token=<REGEN_TOKEN> matching the env var, OR if not set, allow.
    """
    expected = os.getenv("REGEN_TOKEN")
    if expected and request.args.get("token") != expected:
        return jsonify({"error": "unauthorized"}), 401

    try:
        from claude.reporter import assemble_report_data
        from reports.render import save_report

        report = assemble_report_data(
            cadence="on_demand",
            role_results=[],
            tasks_created=[],
            approvals_pending=[],
            permalink="/reports/latest",
        )
        path = save_report(report)
        return jsonify({
            "ok": True,
            "saved_to": str(path),
            "channels": [c.get("channel") for c in report.get("channels", [])],
            "windows": list((report.get("windows") or {}).keys()),
            "trends_rows": len(report.get("trends_30d", [])),
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/")
def root():
    return redirect("/reports/latest")


@app.route("/reports/latest")
def latest():
    f = REPORTS_DIR / "latest.html"
    if f.exists():
        return send_file(f, mimetype="text/html")
    # Fall back to Google Drive — persists across Railway restarts
    try:
        from collectors.drive_writer import load_report_from_drive
        html = load_report_from_drive()
        if html:
            from flask import Response
            return Response(html, mimetype="text/html")
    except Exception as e:
        print(f"[app] Drive fallback failed: {e}")
    abort(404, "No report available. Run: python main.py daily")


@app.route("/reports/<report_date>")
def dated(report_date: str):
    # Accept both "2026-04-25" and "2026-04-25.html"
    name = report_date if report_date.endswith(".html") else f"{report_date}.html"
    f = REPORTS_DIR / name
    if f.exists():
        return send_file(f, mimetype="text/html")
    # Fall back to Drive
    date_key = name.replace(".html", "")
    try:
        from collectors.drive_writer import load_report_from_drive
        html = load_report_from_drive(date_key)
        if html:
            from flask import Response
            return Response(html, mimetype="text/html")
    except Exception as e:
        print(f"[app] Drive fallback failed for {date_key}: {e}")
    abort(404, f"No report for {report_date}")


# ─── Custom date-range API ────────────────────────────────────────────────────

@app.route("/api/report")
def api_report():
    """
    Returns JSON with the same shape as the `channels` list inside
    window.NEXA_DATA so the front-end can populate window 'custom'.

    Query params:
        start  — YYYY-MM-DD  (required)
        end    — YYYY-MM-DD  (required)
    """
    start_str = request.args.get("start")
    end_str   = request.args.get("end")

    if not start_str or not end_str:
        return jsonify({"error": "start and end are required (YYYY-MM-DD)"}), 400

    try:
        start = date.fromisoformat(start_str)
        end   = date.fromisoformat(end_str)
    except ValueError:
        return jsonify({"error": "Dates must be YYYY-MM-DD"}), 400

    if start > end:
        return jsonify({"error": "start must be ≤ end"}), 400

    days = (end - start).days + 1
    if days > 120:
        return jsonify({"error": "Max range is 120 days"}), 400

    try:
        from claude.reporter import CHANNEL_DISPLAY, build_channel_section, build_hero_kpis
        from collectors.bq_writer import get_client

        # Channels that have any spend in the requested window (quick check)
        client, bq, project, dataset = _bq_conn()
        if not client:
            return jsonify({"error": "BQ unavailable"}), 503

        spending_q = f"""
            SELECT DISTINCT channel
            FROM `{project}.{dataset}.campaigns_daily`
            WHERE date BETWEEN @start AND @end AND spend > 0
        """
        rows = _run_query(client, bq, spending_q, [
            bq.ScalarQueryParameter("start", "DATE", start),
            bq.ScalarQueryParameter("end",   "DATE", end),
        ])
        spending_channels = {r["channel"] for r in rows}

        channels = []
        for key, label, color in CHANNEL_DISPLAY:
            if key not in spending_channels:
                continue
            section = _build_section_for_range(key, start, end, days, project, dataset, bq, client)
            section["label"] = label
            section["color"] = color
            channels.append(section)

        return jsonify({
            "start":    start_str,
            "end":      end_str,
            "days":     days,
            "channels": channels,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _bq_conn():
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        from google.cloud import bigquery
        return get_client(), bigquery, PROJECT_ID, DATASET
    except Exception as e:
        print(f"[api] BQ unavailable: {e}")
        return None, None, None, None


def _run_query(client, bq, sql, params):
    try:
        cfg = bq.QueryJobConfig(query_parameters=params)
        return [dict(r) for r in client.query(sql, job_config=cfg).result()]
    except Exception as e:
        print(f"[api] query failed: {e}")
        return []


def _build_section_for_range(channel_key, start, end, days, project, dataset, bq, client):
    """
    Like build_channel_section() but parameterised by explicit start/end
    rather than a rolling window.  Shares the same SQL shape.
    """
    from claude.reporter import _zone, _channel_to_qoyod_source, _utm_breakdown, _disq_reason_breakdown
    from config import CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING

    qoyod_src = _channel_to_qoyod_source(channel_key)
    p = [
        bq.ScalarQueryParameter("channel",   "STRING", channel_key),
        bq.ScalarQueryParameter("qoyod_src", "STRING", qoyod_src),
        bq.ScalarQueryParameter("start",     "DATE",   start),
        bq.ScalarQueryParameter("end",       "DATE",   end),
    ]

    def q(sql): return _run_query(client, bq, sql, p)

    rollup = q(f"""
        WITH cost AS (
          SELECT SUM(spend) AS spend
          FROM `{project}.{dataset}.campaigns_daily`
          WHERE channel = @channel AND date BETWEEN @start AND @end
        ),
        crm AS (
          SELECT SUM(leads_total) AS leads, SUM(leads_qualified) AS qualified,
                 SUM(leads_disqualified) AS disqualified
          FROM `{project}.{dataset}.hubspot_leads_module_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
        ),
        deals AS (
          SELECT SUM(deals_won) AS deals, SUM(amount_won) AS deal_amount
          FROM `{project}.{dataset}.hubspot_deals_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
        )
        SELECT cost.spend, crm.leads, crm.qualified, crm.disqualified,
               deals.deals, deals.deal_amount
        FROM cost, crm, deals
    """)
    r0 = rollup[0] if rollup else {}
    spend = round(float(r0.get("spend") or 0), 2)
    leads = int(r0.get("leads") or 0)
    qual  = int(r0.get("qualified") or 0)
    disq  = int(r0.get("disqualified") or 0)
    deals = int(r0.get("deals") or 0)
    da    = round(float(r0.get("deal_amount") or 0), 2)
    cpl   = round(spend / leads, 2) if leads else None
    cpql  = round(spend / qual, 2)  if qual  else None
    roas  = round(da / spend, 2)    if spend else None

    # Campaign table
    camp_rows = q(f"""
        WITH cost AS (
          SELECT campaign_name, SUM(spend) AS spend
          FROM `{project}.{dataset}.campaigns_daily`
          WHERE channel = @channel AND date BETWEEN @start AND @end
          GROUP BY campaign_name
        ),
        crm AS (
          SELECT lead_utm_campaign AS campaign_name,
                 SUM(leads_total) AS leads, SUM(leads_qualified) AS qualified,
                 SUM(leads_disqualified) AS disqualified
          FROM `{project}.{dataset}.hubspot_leads_module_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
          GROUP BY 1
        ),
        deals AS (
          SELECT deal_utm_campaign AS campaign_name,
                 SUM(deals_won) AS deals_won, SUM(amount_won) AS amount_won
          FROM `{project}.{dataset}.hubspot_deals_daily`
          WHERE qoyod_source = @qoyod_src AND date BETWEEN @start AND @end
          GROUP BY 1
        )
        SELECT cost.campaign_name,
               IFNULL(cost.spend,0) AS cost,
               IFNULL(crm.leads,0) AS leads,
               IFNULL(crm.qualified,0) AS qualified,
               IFNULL(crm.disqualified,0) AS disqualified,
               IFNULL(deals.deals_won,0) AS deals,
               IFNULL(deals.amount_won,0) AS deal_amount
        FROM cost
        LEFT JOIN crm   ON crm.campaign_name   = cost.campaign_name
        LEFT JOIN deals ON deals.campaign_name = cost.campaign_name
        WHERE cost.spend > 0
        ORDER BY cost.spend DESC
    """)
    campaigns = []
    for c in camp_rows:
        s  = round(float(c["cost"] or 0), 2)
        l  = int(c["leads"] or 0)
        q_ = int(c["qualified"] or 0)
        ds = int(c["deals"] or 0)
        da_ = round(float(c["deal_amount"] or 0), 2)
        c_cpl  = round(s / l, 2)  if l  else None
        c_cpql = round(s / q_, 2) if q_ else None
        c_roas = round(da_ / s, 2) if s else None
        campaigns.append({
            "campaign":     c["campaign_name"],
            "cost":         s, "leads": l, "qualified": q_,
            "disqualified": int(c["disqualified"] or 0),
            "cpl": c_cpl, "cpql": c_cpql,
            "deals": ds, "deal_amount": da_, "roas": c_roas,
            "cpl_zone":  _zone(c_cpl,  CPL_SCALE,  CPL_ACCEPTABLE,  CPL_WARNING),
            "cpql_zone": _zone(c_cpql, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING),
        })

    return {
        "channel":  channel_key,
        "window_days": days,
        "kpis": {
            "spend": spend, "leads": leads, "qualified": qual, "disqualified": disq,
            "deals": deals, "deal_amount": da,
            "cpl": cpl, "cpql": cpql, "roas": roas,
            "cpl_zone":  _zone(cpl,  CPL_SCALE,  CPL_ACCEPTABLE,  CPL_WARNING),
            "cpql_zone": _zone(cpql, CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING),
        },
        "campaigns":     campaigns,
        "utm_campaign":  _utm_breakdown(project, dataset, bq, qoyod_src, start, end, "lead_utm_campaign"),
        "utm_audience":  _utm_breakdown(project, dataset, bq, qoyod_src, start, end, "lead_utm_audience"),
        "utm_content":   _utm_breakdown(project, dataset, bq, qoyod_src, start, end, "lead_utm_content"),
        "disq_reasons":  _disq_reason_breakdown(project, dataset, bq, qoyod_src, start, end),
        "ad_groups": {"available": False, "note": "adgroups_daily collector pending"},
        "ads":       {"available": False, "note": "ads_daily collector pending"},
    }


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
