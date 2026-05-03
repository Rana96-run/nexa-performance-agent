"""
reports/app.py
==============
Tiny Flask server that:
  GET  /                       -> redirect to /reports/latest
  GET  /reports/latest         -> serve the most-recent pre-rendered HTML
  GET  /reports/<date>         -> serve a specific dated HTML  (e.g. /reports/2026-04-25)
  GET  /api/report             -> custom date range: ?start=YYYY-MM-DD&end=YYYY-MM-DD
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

from flask import Flask, jsonify, redirect, request, send_file, abort, Response
from collectors.hubspot_webhook import hubspot_bp

REPORTS_DIR = Path(__file__).parent
app = Flask(__name__)
app.register_blueprint(hubspot_bp)


# ─── Static report pages ──────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


_REFRESH_STATUS: dict = {"running": False, "started_at": None,
                          "finished_at": None, "result": None, "error": None}


def _do_refresh(days: int | None, backfill: bool):
    """
    Run BQ refresh, recording status to _REFRESH_STATUS for polling.
    HTML report generation removed — Hex dashboard replaces it.
    """
    from datetime import datetime as _dt
    from reporting_scheduler import run_refresh

    _REFRESH_STATUS.update({
        "running": True, "started_at": _dt.utcnow().isoformat() + "Z",
        "finished_at": None, "result": None, "error": None,
    })
    try:
        if days:
            results = run_refresh(days=days)
        else:
            results = run_refresh(incremental=not backfill)
        _REFRESH_STATUS["result"] = {
            "collectors": {k: ("ok" if v[0] else "fail") for k, v in results.items()},
            "note": "HTML report deprecated — view dashboard at Hex DASHBOARD_URL",
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



_HEX_DASHBOARD = (
    os.getenv(
        "DASHBOARD_URL",
        "https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/"
        "Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest",
    )
)


@app.route("/")
@app.route("/paid-performance/latest")
@app.route("/paid-performance/<report_date>")
@app.route("/reports/latest")
@app.route("/reports/<report_date>")
def dashboard_redirect(**kwargs):
    """All old HTML report URLs → Hex dashboard (permanent redirect)."""
    return redirect(_HEX_DASHBOARD, code=301)


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


# ─── Slack Events API ─────────────────────────────────────────────────────────

def _verify_slack_signature(raw_body: bytes, headers) -> bool:
    """
    Verify Slack request signature using the raw body bytes.
    Must receive raw body BEFORE any json parsing — calling get_json() first
    consumes the stream and makes get_data() return empty, breaking the HMAC.
    """
    import hashlib, hmac as _hmac, time as _time
    secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not secret:
        return True  # no secret configured — skip (dev / first-run)
    ts  = headers.get("X-Slack-Request-Timestamp", "")
    sig = headers.get("X-Slack-Signature", "")
    if not ts or not sig:
        return False
    try:
        if abs(_time.time() - float(ts)) > 300:
            return False  # replay-attack window
    except ValueError:
        return False
    basestring = f"v0:{ts}:{raw_body.decode('utf-8')}".encode()
    expected   = "v0=" + _hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, sig)


def _handle_reaction(event: dict):
    """
    Called in a background thread when ✅ or ❌ is added to an approval message.
    Looks up the ts in pending_approvals.json, executes if approved, then replies in thread.
    """
    reaction = event.get("reaction", "")
    item     = event.get("item", {})
    msg_ts   = item.get("ts", "")

    if reaction not in ("white_check_mark", "x"):
        return

    try:
        from notifications.slack import get_pending_approval, remove_pending_approval
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
        wc   = WebClient(token=SLACK_BOT_TOKEN)
        meta = get_pending_approval(msg_ts)
        if not meta:
            return  # not one of our messages

        action = meta.get("action", "")
        # Build a human-readable label for the reaction reply
        if action == "batch_scale_pause":
            findings = meta.get("findings", [])
            camp = f"{len(findings)} campaign(s)"
        else:
            camp = meta.get("campaign", "") or ", ".join(meta.get("campaigns", [])[:3])
        user   = event.get("user", "")

        if reaction == "white_check_mark":
            exec_result = _execute_approved_action(meta)
            # Update Asana for each finding in a batch, or the single asana_gid
            gids = [f.get("asana_gid") for f in meta.get("findings", []) if f.get("asana_gid")]
            if not gids and meta.get("asana_gid"):
                gids = [meta["asana_gid"]]
            for gid in gids:
                try:
                    import asana as asana_sdk
                    cfg = asana_sdk.Configuration()
                    cfg.access_token = os.getenv("ASANA_ACCESS_TOKEN", "")
                    ac  = asana_sdk.ApiClient(cfg)
                    asana_sdk.StoriesApi(ac).create_story_for_task(
                        gid,
                        {"data": {"text": f"[Nexa] Approved by <@{user}>. Result: {exec_result[:200]}"}},
                    )
                except Exception as e:
                    print(f"[events] Asana comment failed for {gid}: {e}")
            reply = f"✅ *Approved* by <@{user}>\n{exec_result}"
        else:
            reply = f"❌ *Rejected* by <@{user}>\n`{camp}` — no changes made."

        wc.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            thread_ts=msg_ts,
            text=reply,
        )
        remove_pending_approval(msg_ts)
        print(f"[events] Reaction '{reaction}' by {user} for {camp[:50]!r}")
    except Exception as e:
        print(f"[events] reaction handler error: {e}")


def _execute_approved_action(meta: dict) -> str:
    """
    Execute a scale or pause that was approved via yes/no reply.
    Returns a human-readable result string.
    """
    action      = meta.get("action", "").lower()
    channel     = meta.get("channel", "")
    campaign    = meta.get("campaign", "")
    campaign_id = meta.get("campaign_id", "")
    account_id  = meta.get("account_id", "")
    new_budget  = meta.get("new_budget")

    if action == "scale":
        if not campaign_id or not new_budget:
            return f"Could not execute — missing campaign_id or budget. Scale `{campaign}` manually to ${new_budget:.0f}/day." if new_budget else f"Scale `{campaign}` manually (+25%)."
        try:
            if channel == "google_ads":
                from executors.google_ads import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget, customer_id=account_id)
            elif channel == "meta":
                from executors.meta import update_campaign_budget
                update_campaign_budget(campaign_id, new_budget)
            elif channel == "snapchat":
                from executors.snapchat import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget, account_id=account_id)
            elif channel == "tiktok":
                from executors.tiktok import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget, advertiser_id=account_id)
            else:
                return f"Channel `{channel}` not supported for auto-scale. Set budget to ${new_budget:.0f}/day manually."
            return f"Budget increased to ${new_budget:.0f}/day (+25%). Done."
        except Exception as e:
            return f"Scale execution failed: {e}. Set to ${new_budget:.0f}/day manually."

    elif action == "pause":
        if not campaign_id:
            return f"Could not execute — no campaign_id. Pause `{campaign}` manually."
        try:
            if channel == "google_ads":
                from executors.google_ads import pause_campaign
                pause_campaign(campaign_id, customer_id=account_id)
            elif channel == "meta":
                from executors.meta import pause_campaign
                pause_campaign(campaign_id)
            elif channel == "snapchat":
                from executors.snapchat import pause_campaign
                pause_campaign(campaign_id, account_id=account_id)
            elif channel == "tiktok":
                from executors.tiktok import pause_campaign
                pause_campaign(campaign_id, advertiser_id=account_id)
            else:
                return f"Channel `{channel}` not supported for auto-pause. Pause `{campaign}` manually."
            return f"Campaign paused. Done."
        except Exception as e:
            return f"Pause execution failed: {e}. Pause `{campaign}` manually."

    elif action == "batch_scale_pause":
        results = []
        for f in meta.get("findings", []):
            sub = _execute_approved_action(f)
            results.append(f"`{f.get('campaign', '?')}`: {sub}")
        return "\n".join(results) if results else "Nothing to execute."

    return "Acknowledged — Asana tasks updated."


def _handle_thread_reply(event: dict):
    """
    Called in a background thread when a message is posted in the approval channel.
    Looks for yes/no replies to pending approval messages and executes accordingly.
    """
    # Only process thread replies (has thread_ts and it differs from the message ts)
    thread_ts = event.get("thread_ts", "")
    msg_ts    = event.get("ts", "")
    if not thread_ts or thread_ts == msg_ts:
        return  # top-level message, not a reply

    text = (event.get("text") or "").strip().lower()
    if text not in ("yes", "no"):
        return  # not a yes/no reply

    try:
        from notifications.slack import get_pending_approval, remove_pending_approval
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
        wc   = WebClient(token=SLACK_BOT_TOKEN)
        meta = get_pending_approval(thread_ts)
        if not meta:
            return  # not one of our approval messages

        action = meta.get("action", "")
        camp   = meta.get("campaign", "") or ", ".join(meta.get("campaigns", [])[:3])
        user   = event.get("user", "")

        if text == "yes":
            exec_result = _execute_approved_action(meta)
            # Add Asana comment if gid is stored
            asana_gid = meta.get("asana_gid", "")
            if asana_gid:
                try:
                    import asana as asana_sdk
                    cfg = asana_sdk.Configuration()
                    cfg.access_token = os.getenv("ASANA_ACCESS_TOKEN", "")
                    ac  = asana_sdk.ApiClient(cfg)
                    asana_sdk.StoriesApi(ac).create_story_for_task(
                        asana_gid,
                        {"data": {"text": f"[Nexa] Approved by <@{user}>. Result: {exec_result}"}},
                    )
                except Exception as e:
                    print(f"[events] Asana comment failed: {e}")
            reply = f"✅ *Approved* by <@{user}>\n{exec_result}"
        else:
            reply = f"❌ *Skipped* by <@{user}>\n`{camp}` — no changes made."

        wc.chat_postMessage(
            channel=SLACK_CHANNEL_APPROVAL,
            thread_ts=thread_ts,
            text=reply,
        )
        remove_pending_approval(thread_ts)
        print(f"[events] Reply '{text}' by {user} for {camp[:50]!r}")
    except Exception as e:
        print(f"[events] thread reply handler error: {e}")


@app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Slack Events API endpoint.
    1. URL verification (one-time during Events setup)
    2. reaction_added on approval messages → approve/reject
    """
    import json as _json

    # Read raw body ONCE — must happen before any get_json() call
    raw_body = request.get_data()
    try:
        payload = _json.loads(raw_body) if raw_body else {}
    except Exception:
        payload = {}
    event_type = payload.get("type", "")

    # URL verification: respond immediately, no signature check needed
    if event_type == "url_verification":
        return jsonify({"challenge": payload.get("challenge", "")})

    # All other events: verify signature using the already-read raw body
    if not _verify_slack_signature(raw_body, request.headers):
        return jsonify({"error": "invalid signature"}), 403

    if event_type == "event_callback":
        event      = payload.get("event", {})
        event_kind = event.get("type", "")

        if event_kind == "reaction_added":
            import threading
            threading.Thread(target=_handle_reaction, args=(event,), daemon=True).start()

    # Always respond 200 immediately (Slack requires < 3s)
    return Response("", status=200)


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
