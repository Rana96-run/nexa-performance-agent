"""
reports/app.py
==============
Flask server that:
  GET  /health                 -> 200 OK (Railway health check)
  GET  /                       -> 301 → Hex performance dashboard
  GET  /activity               -> HTML agent activity dashboard (BQ-backed)
  GET  /paid-performance/*     -> 301 → Hex performance dashboard
  GET  /reports/*              -> 301 → Hex performance dashboard
  POST /api/refresh            -> kick off BQ data refresh in background
  GET  /api/refresh/status     -> poll refresh progress
  POST /slack/events           -> Slack Events API (reaction_added → approve/reject)
  POST /hubspot/webhook        -> HubSpot lead webhooks (via hubspot_bp blueprint)

Performance dashboard lives in Hex (read from BQ):
  Performance → qoyod-marketing-performance  (paid media KPIs)
Activity dashboard is served as HTML from this server at /activity.

Deploy on Railway (single dyno). Railway runs the agent — Flask serves /activity.
"""
from __future__ import annotations

import os
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, Response
from collectors.hubspot_webhook import hubspot_bp

app = Flask(__name__, template_folder="templates")
app.register_blueprint(hubspot_bp)


# ─── Static report pages ──────────────────────────────────────────────────────

_START_TIME = datetime.utcnow()

@app.route("/health")
def health():
    uptime_s = int((datetime.utcnow() - _START_TIME).total_seconds())
    return jsonify({
        "status": "ok",
        "uptime_seconds": uptime_s,
        "utc_now": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }), 200


_WORKFLOWS = {
    "campaigns_created": {
        "title": "Campaign Creation",
        "subtitle": "How new Google Ads campaigns are built from the best performer",
        "steps": [
            ("Trigger", "Manual prompt to agent or python scripts/create_campaign_from_best.py"),
            ("Template lookup", "BQ query on campaigns_daily — find lowest CPQL campaign last 30d"),
            ("Naming validation", "executors/naming.py: Channel_Type_Language_Product_Audience format enforced"),
            ("Budget created", "Google Ads API — CampaignBudgetService.mutate_campaign_budgets"),
            ("Campaign created (PAUSED)", "CampaignService.mutate_campaigns — status=PAUSED until reviewed"),
            ("Ad groups cloned", "Source campaign ad groups renamed to new campaign name"),
            ("Keywords filtered", "Keep only QS ≥ 5 OR (conv ≥ 3 AND CPA ≤ $90)"),
            ("UTM params auto-set", "Final URLs tagged via naming convention"),
            ("Logged to BQ", "agent_activity_log: action=campaign_created"),
        ],
    },
    "campaigns_paused": {
        "title": "Campaign Pause via Approval",
        "subtitle": "How underperforming campaigns get paused through the approval gate",
        "steps": [
            ("Daily audit at 08:00 Riyadh", "operational_scheduler.py triggers campaign_health.py"),
            ("BQ query", "campaigns_daily + hubspot_leads_module_daily — last 14 days"),
            ("CPQL threshold check", "CPQL > 3× channel warning threshold → flagged for pause"),
            ("Junk leads check", "disqualified/total ≥ 60% over 10+ days → also flagged"),
            ("Asana task created", "Pause recommendation with full campaign card and reason"),
            ("Nightly #approvals digest", "Single Slack message covering all scale + pause items"),
            ("Team reacts ✅ or ❌", "Slack Events API: reaction_added webhook fires in reports/app.py"),
            ("execute_approved_action()", "Channel-specific pause API called (Google/Meta/Snap/TikTok/LinkedIn)"),
            ("Logged to BQ", "agent_activity_log: action=campaign_paused"),
        ],
    },
    "campaigns_scaled": {
        "title": "Campaign Scale via Approval",
        "subtitle": "How high-performing campaigns get budget increases",
        "steps": [
            ("Daily audit at 08:00 Riyadh", "campaign_health.py checks CPQL + spend trend"),
            ("Scale flag set", "CPQL < warning threshold AND spend capacity available"),
            ("New budget calculated", "Current daily budget × 1.25 (always +25%)"),
            ("Asana task created", "Scale recommendation with projected budget and CPQL"),
            ("Nightly #approvals digest", "Bundled with pauses in one Slack message"),
            ("Team reacts ✅", "Reaction triggers execute_approved_action() → scale path"),
            ("Budget mutated", "set_campaign_budget() via channel-specific executor"),
            ("Logged to BQ", "agent_activity_log: action=campaign_scaled"),
        ],
    },
    "campaign_audits": {
        "title": "Campaign Health Audit",
        "subtitle": "Daily audit that generates all optimization recommendations",
        "steps": [
            ("Scheduled at 08:00 Riyadh", "operational_scheduler.py daily cadence"),
            ("Multi-channel BQ query", "All campaigns: spend, leads, CPQL, CPL last 14 days"),
            ("Classification", "Scale / Pause / Drilldown / Optimize / Awareness buckets"),
            ("Asana tasks batch-created", "One task per finding, routed to correct project + section"),
            ("Nightly digest posted", "Single #approvals Slack message; separate #notify Slack summary"),
            ("Logged to BQ", "action=create_audit_tasks, rows_affected = task count"),
        ],
    },
    "keywords_added": {
        "title": "Keyword Expansion",
        "subtitle": "How new keyword candidates are found and added",
        "steps": [
            ("Weekly trigger (Sunday Riyadh)", "google_ads_audit.py searches search_term_view last 14 days"),
            ("Policy filter", "keyword_policy.py removes ALWAYS_NEGATIVE, brand-only, competitor terms"),
            ("QS + IS-lost check", "Skip if QS < 5 AND > 80% impression share lost"),
            ("Age guard", "Keyword must have impressions ≥ 10 days old"),
            ("30-keyword cap", "Per ad group: only (30 − existing) candidates kept"),
            ("Asana task created", "Keyword list posted to Asana for human review"),
            ("Human executes", "python scripts/bulk_keywords.py add after Asana review"),
            ("Logged to BQ", "action=keyword_candidates_queued_for_weekly_review, rows_affected=count"),
        ],
    },
    "keywords_paused": {
        "title": "Keyword Auto-Pause",
        "subtitle": "How non-converting keywords get paused automatically",
        "steps": [
            ("Daily audit", "audit_and_pause_nonconverting_keywords(days=7) in google_ads_audit.py"),
            ("Threshold check", "spend > $4 over 7 days AND 0 HubSpot-qualified leads"),
            ("Age guard", "Keyword must be ≥ 10 days old (first impression date from keyword_view)"),
            ("Sole-keyword guard", "Skip if this is the last enabled keyword in its ad group"),
            ("QS exception", "If QS < 5 but conv > 4 AND $10 ≤ CPA ≤ $70 → leave ENABLED"),
            ("Google Ads API call", "AdGroupCriterionService.mutate: status = PAUSED"),
            ("Asana task created", "Confirmation task: EXECUTED prefix + full keyword list"),
            ("Logged to BQ", "action=keywords_paused, rows_affected = keywords paused"),
        ],
    },
    "negatives_added": {
        "title": "Negative Keyword Execution",
        "subtitle": "How wasted search terms get blocked automatically",
        "steps": [
            ("Search term report scanned", "google_ads_audit.py: search_term_view last 14 days"),
            ("ALWAYS_NEGATIVE policy", "login/free/course/download/loan/job patterns → auto-exclude"),
            ("Wasted spend check", "$25+ per term with 0 conversions → negative candidate"),
            ("Competitor guard", "Competitor terms NEVER negated — routed to pause-watch instead"),
            ("Add as EXACT negative", "Campaign-level via add_negative_keywords() in executors/google_ads.py"),
            ("Logged to BQ", "action=negative_keywords_added, details.terms = list of blocked terms"),
        ],
    },
    "optimizations": {
        "title": "Optimization Recommendation",
        "subtitle": "How the agent surfaces actionable improvements in Asana",
        "steps": [
            ("Health audit classifies campaign", "CPQL vs warning threshold; CPL vs $50; spend vs 14d window"),
            ("Drilldown flag", "Borderline CPQL (1–3× warning) → investigate creative/audience mix"),
            ("Optimize flag", "Stable CPL but declining trends or low IS → structural review"),
            ("Scale flag", "CPQL < warning AND capacity → budget increase recommendation"),
            ("Asana task created", "Full campaign card with metric context and suggested action"),
            ("Logged to BQ", "action=optimize/drilldown/scale_task_created, campaign_name stored"),
        ],
    },
    "asana_tasks": {
        "title": "Asana Task Creation",
        "subtitle": "How every agent recommendation becomes a trackable Asana task",
        "steps": [
            ("Analysis completes", "campaign_health, google_ads_audit, display_audit, microsoft_ads_audit"),
            ("Deduplication check", "cache/cache_manager.py: skip if identical task already created today"),
            ("Project routed", "daily_activity / optimization / campaigns_hub / seasonal"),
            ("Section routed", "Per-channel × per-asset-level section within project"),
            ("Task created via Asana API", "TasksApi.create_task with assignee, due_on, notes + footer"),
            ("Logged to BQ", "action=asana_task_created, details.title + project_key + asset_level"),
        ],
    },
    "creative_reviews": {
        "title": "Creative Review Task",
        "subtitle": "How ad-level creative performance triggers a review task",
        "steps": [
            ("Ad drilldown audit", "creative_performance.py or ad_drilldown.py pulls ads_daily"),
            ("Qual rate check", "disqualified/total ≥ 60% AND spend > threshold → junk flag"),
            ("CPL check per ad", "spend / hs_leads > $50 over 10+ days → high CPL flag"),
            ("Asana task created", "asset_level=ad, action=optimize — includes creative name + CPQL"),
            ("Creative name in details", "asana_task_created.details.title contains creative identifier"),
            ("Logged to BQ", "action=asana_task_created, asana_asset_level=ad"),
        ],
    },
    "slack_messages": {
        "title": "Daily Slack Summary",
        "subtitle": "How the agent sends its nightly performance digest",
        "steps": [
            ("Scheduled at 08:00 Riyadh", "operational_scheduler.py daily cadence post-audit"),
            ("BQ query", "paid_channel_daily: yesterday spend + HubSpot leads + CPQL per channel"),
            ("Top + worst identified", "Lowest and highest CPQL channels selected"),
            ("Main message formatted", "Dashboard URL (plain text) + peak numbers per channel"),
            ("Follow-up message", "Recommendations referencing Asana task GIDs + #approvals link"),
            ("Logged to BQ", "action=posted_slack_digest or slack_summary_posted"),
        ],
    },
    "slack_approvals": {
        "title": "Nightly Approvals Digest",
        "subtitle": "How scale + pause candidates reach the team for approval",
        "steps": [
            ("Audit findings compiled", "Scale + pause + review findings collected after full audit"),
            ("Single digest built", "campaign_health_tasks._send_nightly_digest()"),
            ("Slack block formatted", "Scale section (execute on ✅), Pause section, Review summary"),
            ("Posted to #approvals", "Pending approval stored in cache/pending_approvals.json"),
            ("Team reacts ✅ or ❌", "Slack Events API fires reaction_added within 24h"),
            ("Execute or skip", "✅ → execute_approved_action(); ❌ → log rejection, no change"),
            ("Logged to BQ", "action=posted_approvals_digest, details.scale/pause/review counts"),
        ],
    },
    "llm_runs": {
        "title": "LLM Analysis Run",
        "subtitle": "How Claude performs deep strategic analysis on a cadence",
        "steps": [
            ("Cadence check", "main.py checks weekly/monthly/quarterly cadence vs last-run date"),
            ("BQ data loaded", "Paid channel daily, HubSpot leads, deal pipeline — last 30/90d"),
            ("Claude prompt built", "Role-specific system prompt + structured channel data"),
            ("Claude API called", "claude-sonnet-4-6, max 8k tokens, tracked via cost_tracking.py"),
            ("Recommendations extracted", "Asana tasks created from LLM output"),
            ("Logged to BQ", "action=llm_role_ran, tokens_in/out/cost_usd recorded"),
        ],
    },
    "spike_detections": {
        "title": "Anomaly / Spike Detection",
        "subtitle": "How the agent spots sudden performance changes and alerts the team",
        "steps": [
            ("Runs daily post-refresh", "spike_detector.detect_spikes() in operational_scheduler"),
            ("BQ query", "paid_channel_daily: yesterday vs 7-day rolling baseline per channel"),
            ("Threshold check", "Spend/leads/CPQL deviation > configured threshold (e.g. 30%)"),
            ("Disqualification rate check", "Sudden disqual spike > 15 pp above baseline flagged"),
            ("Slack alert posted", "formatted block to #notify with direction arrows and % change"),
            ("Logged to BQ", "action=detect_spikes, rows_affected = spike count"),
        ],
    },
    "slack_bot_replies": {
        "title": "Slack Bot Reply (@Nexa)",
        "subtitle": "How the agent responds to direct mentions in Slack",
        "steps": [
            ("@Nexa mention received", "Slack Events API sends event to /slack/events endpoint"),
            ("Event type check", "app_mention event type → handle_mention() in slack_listener.py"),
            ("BQ context loaded", "Latest spend, leads, CPQL data pulled for grounding"),
            ("Claude API called", "claude-sonnet-4-6, 1.5k tokens, MSA Arabic or English detected"),
            ("Reply posted", "slack_client.chat_postMessage() in the same thread"),
            ("Logged to BQ", "action=slack_listener_reply, tokens_in/out/cost_usd recorded"),
        ],
    },
    "bq_collections": {
        "title": "BQ Data Collection",
        "subtitle": "How ad platform data flows into BigQuery every 6 hours",
        "steps": [
            ("Scheduled every 6h", "reporting_scheduler.py loop — run_refresh()"),
            ("Platform API called", "Channel-specific collector: google_ads_bq, meta_bq, snap_bq, etc."),
            ("Currency normalized", "Micros → USD; SAR → USD at 3.75 peg where needed"),
            ("MERGE into BQ", "bq_writer.py: MERGE ON date + campaign_id — idempotent, no duplicates"),
            ("Views refreshed", "collectors/views.py: paid_channel_daily, v_adset_performance, etc."),
            ("Logged to BQ", "action=collect_{channel}, rows_affected = rows written"),
        ],
    },
    "data_quality": {
        "title": "Data Quality Autoheal",
        "subtitle": "How the agent detects and fixes data gaps automatically",
        "steps": [
            ("Runs daily", "analysers/data_quality.py checks all BQ source tables"),
            ("Gap detection", "Missing dates, zero-spend days, stale collection timestamps"),
            ("Autoheal triggered", "Re-runs the relevant collector for the missing window"),
            ("Verification", "Confirms data present after heal attempt"),
            ("Logged to BQ", "action=data_quality_autoheal, details.issue_type"),
        ],
    },
}


@app.route("/activity")
def activity_dashboard():
    """HTML agent activity dashboard — GitHub-style heatmap + expandable cards + workflow modals."""
    from datetime import date, timedelta, timezone

    days = min(max(int(request.args.get("days", 90)), 7), 365)

    try:
        from collectors.bq_writer import get_client
        bq = get_client()
        P  = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
        D  = os.getenv("BQ_DATASET", "qoyod_marketing")
        T  = f"`{P}.{D}`"
    except Exception as e:
        return f"<pre>BQ unavailable: {e}</pre>", 503

    riyadh    = timezone(timedelta(hours=3))
    today     = datetime.now(riyadh).date()
    now_str   = datetime.now(riyadh).strftime("%Y-%m-%d %H:%M")
    start_day = today - timedelta(days=days - 1)
    date_label = f"{start_day.strftime('%b %d')} – {today.strftime('%b %d, %Y')}"

    # ── _CAT_MAP used for sidebar + recent activity ────────────────────────────
    _CAT_MAP = {
        "campaign_created":                            "Campaigns Created",
        "campaign_paused":                             "Campaigns Paused",
        "campaign_scaled":                             "Campaigns Scaled",
        "launch":                                      "Keywords Added",
        "keyword_candidates_queued_for_weekly_review": "Keywords Added",
        "keywords_paused":                             "Keywords Paused",
        "negative_keywords_added":                     "Negatives Added",
        "asana_task_created":                          "Asana Tasks",
        "posted_slack_digest":                         "Slack Messages",
        "slack_summary_posted":                        "Slack Messages",
        "post_weekly_summary":                         "Slack Messages",
        "nightly_audit_complete":                      "Slack Messages",
        "posted_approvals_digest":                     "Approvals",
        "approval_requested":                          "Approvals",
        "user_completed_task":                         "User Actions",
        "user_created_task":                           "User Actions",
        "user_executed_scale":                         "User Actions",
        "user_executed_pause":                         "User Actions",
        "user_added_negative":                         "User Actions",
        "user_reviewed_recommendation":                "User Actions",
        "user_paused_campaign":                        "User Actions",
        "user_enabled_campaign":                       "User Actions",
        "user_changed_budget":                         "User Actions",
        "user_changed_status":                         "User Actions",
        "user_paused_ad":                              "User Actions",
        "user_enabled_ad":                             "User Actions",
        "create_audit_tasks":                          "Campaign Audits",
        "optimize_task_created":                       "Optimizations",
        "drilldown_task_created":                      "Optimizations",
        "scale_task_created":                          "Optimizations",
        "pause_task_created":                          "Optimizations",
        "junk_leads_task_created":                     "Optimizations",
        "pause_task_created":                          "Ads Paused",
        "junk_leads_task_created":                     "Ads Paused",
        "ads_paused":                                  "Ads Paused",
    }

    # ── 1. Heatmap data (from view, parameterised by days) ─────────────────────
    heatmap_sql = f"""
        SELECT day, category, SUM(count) AS count
        FROM {T}.v_agent_activity_dashboard
        WHERE day >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {days + 1} DAY)
        GROUP BY day, category
    """
    heatmap_raw: dict[str, dict[str, int]] = {}
    try:
        for row in bq.query(heatmap_sql).result():
            heatmap_raw.setdefault(str(row.category), {})[str(row.day)] = int(row.count)
    except Exception as e:
        if "Not found" in str(e) and "v_agent_activity_dashboard" in str(e):
            # View hasn't been created yet — trigger it silently and continue
            try:
                from collectors.views import refresh_all_views
                refresh_all_views()
                for row in bq.query(heatmap_sql).result():
                    heatmap_raw.setdefault(str(row.category), {})[str(row.day)] = int(row.count)
            except Exception:
                pass  # heatmap will be empty; all other sections still render
        else:
            raise

    CATEGORIES = [
        "Campaigns Created", "Campaigns Paused", "Campaigns Scaled",
        "Keywords Added", "Keywords Paused", "Negatives Added",
        "Ads Paused", "Asana Tasks", "Slack Messages", "Approvals",
        "User Actions",
    ]
    all_dates = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    def _level(n):
        if n == 0: return 0
        if n <= 2:  return 1
        if n <= 5:  return 2
        if n <= 10: return 3
        return 4

    # Pad so the grid's first column starts on the correct weekday (Mon=0)
    first_weekday = start_day.weekday()
    pad_cells = [{"date": "", "count": 0, "level": -1}] * first_weekday

    heatmap_rows = []
    for cat in CATEGORIES:
        data  = heatmap_raw.get(cat, {})
        cells = pad_cells + [
            {"date": str(d), "count": data.get(str(d), 0),
             "level": _level(data.get(str(d), 0))}
            for d in all_dates
        ]
        total = sum(data.get(str(d), 0) for d in all_dates)
        heatmap_rows.append((cat, cells, total))

    # ── 2. All detail rows (90d, relevant actions only) ───────────────────────
    detail_sql = f"""
        SELECT
          DATE(ts, 'Asia/Riyadh')                          AS day,
          action, role, channel, campaign_name, status,
          COALESCE(rows_affected, 1)                        AS cnt,
          JSON_VALUE(details, '$.title')                    AS asana_title,
          JSON_VALUE(details, '$.task_action')              AS asana_task_action,
          JSON_VALUE(details, '$.asset_level')              AS asana_asset_level,
          JSON_VALUE(details, '$.project_key')              AS asana_project_key,
          JSON_VALUE(details, '$.new_budget_usd')           AS new_budget,
          JSON_VALUE(details, '$.budget_usd')               AS create_budget,
          JSON_VALUE(details, '$.candidate_count')          AS candidate_count,
          JSON_EXTRACT_STRING_ARRAY(details, '$.keywords')  AS kw_list,
          JSON_EXTRACT_STRING_ARRAY(details, '$.terms')     AS terms_list,
          JSON_VALUE(details, '$.scale')                    AS dig_scale,
          JSON_VALUE(details, '$.pause')                    AS dig_pause,
          JSON_VALUE(details, '$.review')                   AS dig_review
        FROM {T}.agent_activity_log
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
          AND status NOT IN ('failed', 'skipped')
          AND action IN (
            'campaign_created','campaign_paused','campaign_scaled',
            'launch','keyword_candidates_queued_for_weekly_review',
            'keywords_paused','negative_keywords_added',
            'asana_task_created',
            'posted_slack_digest','slack_summary_posted','post_weekly_summary',
            'nightly_audit_complete',
            'posted_approvals_digest','approval_requested',
            'create_audit_tasks',
            'optimize_task_created','drilldown_task_created',
            'scale_task_created','pause_task_created','junk_leads_task_created'
          )
        ORDER BY ts DESC
        LIMIT 600
    """
    detail_rows = list(bq.query(detail_sql).result())

    # ── 3. BQ collections & refreshes ─────────────────────────────────────────
    infra_sql = f"""
        SELECT
          DATE(ts, 'Asia/Riyadh') AS day,
          action,
          COALESCE(rows_affected, 1) AS cnt
        FROM {T}.agent_activity_log
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
          AND status NOT IN ('failed','skipped')
          AND (action LIKE 'collect_%' OR action IN (
               'refresh_hex_notebooks','refresh_complete','refresh_views'))
        ORDER BY ts DESC
        LIMIT 300
    """
    infra_rows = list(bq.query(infra_sql).result())

    # ── 4. Linked channels ─────────────────────────────────────────────────────
    chan_sql = f"""
        SELECT
          channel,
          MAX(date)                                                   AS latest_date,
          DATE_DIFF(CURRENT_DATE('Asia/Riyadh'), MAX(date), DAY) <= 3 AS active
        FROM {T}.campaigns_daily
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 60 DAY)
          AND channel IS NOT NULL
        GROUP BY channel
        ORDER BY latest_date DESC
    """
    channel_rows = []
    try:
        channel_rows = list(bq.query(chan_sql).result())
    except Exception:
        pass

    # ── Helper: count rows by action set, filtered to window ──────────────────
    cutoff_30 = today - timedelta(days=30)
    cutoff_7  = today - timedelta(days=7)

    def _counts(rows, actions):
        c30 = sum(r.cnt for r in rows if r.action in actions and r.day >= cutoff_30)
        c7  = sum(r.cnt for r in rows if r.action in actions and r.day >= cutoff_7)
        return c30, c7

    def _filter(rows, actions, *, extra=None):
        out = [r for r in rows if r.action in actions]
        if extra:
            out = [r for r in out if extra(r)]
        return out

    # ── Build each metric ──────────────────────────────────────────────────────

    # Campaigns created
    c_created_rows = _filter(detail_rows, {"campaign_created"})
    c30, c7 = _counts(detail_rows, {"campaign_created"})
    m_campaigns_created = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "campaign_name": r.campaign_name,
                  "channel": r.channel, "budget": r.create_budget}
                 for r in c_created_rows[:50]],
    }

    # Campaigns paused (via approval execution)
    c30, c7 = _counts(detail_rows, {"campaign_paused"})
    m_campaigns_paused = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "campaign_name": r.campaign_name, "channel": r.channel}
                 for r in _filter(detail_rows, {"campaign_paused"})[:50]],
    }

    # Campaigns scaled
    c30, c7 = _counts(detail_rows, {"campaign_scaled"})
    m_campaigns_scaled = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "campaign_name": r.campaign_name,
                  "channel": r.channel, "budget": r.new_budget}
                 for r in _filter(detail_rows, {"campaign_scaled"})[:50]],
    }

    # Campaign audits
    audit_actions = {"create_audit_tasks"}
    c30, c7 = _counts(detail_rows, audit_actions)
    m_campaign_audits = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "channel": r.channel, "cnt": r.cnt}
                 for r in _filter(detail_rows, audit_actions)[:60]],
    }

    # Keywords added
    kw_add_actions = {"launch", "keyword_candidates_queued_for_weekly_review"}
    c30, c7 = _counts(detail_rows, kw_add_actions)
    m_keywords_added = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "channel": r.channel or "google_ads", "cnt": r.cnt}
                 for r in _filter(detail_rows, kw_add_actions)[:60]],
    }

    # Keywords paused — expand kw_list from JSON array
    kw_paused_flat = []
    for r in _filter(detail_rows, {"keywords_paused"}):
        kws = r.kw_list or []
        for kw in kws:
            kw_paused_flat.append({"day": r.day, "keyword": kw, "channel": r.channel})
    kp_c30 = sum(r.cnt for r in detail_rows if r.action == "keywords_paused" and r.day >= cutoff_30)
    kp_c7  = sum(r.cnt for r in detail_rows if r.action == "keywords_paused" and r.day >= cutoff_7)
    m_keywords_paused = {
        "count_30d": kp_c30, "count_7d": kp_c7,
        "kw_rows": kw_paused_flat[:120],
    }

    # Negatives added — expand terms_list
    neg_flat = []
    for r in _filter(detail_rows, {"negative_keywords_added"}):
        for term in (r.terms_list or []):
            neg_flat.append({"day": r.day, "term": term})
    neg_c30 = sum(r.cnt for r in detail_rows if r.action == "negative_keywords_added" and r.day >= cutoff_30)
    neg_c7  = sum(r.cnt for r in detail_rows if r.action == "negative_keywords_added" and r.day >= cutoff_7)
    m_negatives_added = {
        "count_30d": neg_c30, "count_7d": neg_c7,
        "term_rows": neg_flat[:120],
    }

    # Optimization recommendations
    opt_actions = {"optimize_task_created", "drilldown_task_created",
                   "scale_task_created", "pause_task_created", "junk_leads_task_created"}
    c30, c7 = _counts(detail_rows, opt_actions)
    m_optimizations = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "campaign_name": r.campaign_name,
                  "channel": r.channel, "action": r.action}
                 for r in _filter(detail_rows, opt_actions)[:100]],
    }

    # Asana tasks (all, excluding creative reviews)
    asana_rows = _filter(detail_rows, {"asana_task_created"})
    asana_c30 = sum(1 for r in asana_rows if r.day >= cutoff_30)
    asana_c7  = sum(1 for r in asana_rows if r.day >= cutoff_7)
    m_asana_tasks = {
        "count_30d": asana_c30, "count_7d": asana_c7,
        "rows": [{"day": r.day, "title": r.asana_title or "—",
                  "project_key": r.asana_project_key or "—",
                  "task_action": r.asana_task_action or "—"}
                 for r in asana_rows[:100]],
    }

    # Creative reviews — Asana tasks where asset_level = 'ad'
    creative_rows = [r for r in asana_rows if r.asana_asset_level in ("ad", "creative")]
    cr_c30 = sum(1 for r in creative_rows if r.day >= cutoff_30)
    cr_c7  = sum(1 for r in creative_rows if r.day >= cutoff_7)
    m_creative_reviews = {
        "count_30d": cr_c30, "count_7d": cr_c7,
        "rows": [{"day": r.day, "title": r.asana_title or "—",
                  "campaign_name": r.campaign_name or "—", "channel": r.channel or "—"}
                 for r in creative_rows[:100]],
    }

    # Slack messages
    slack_actions = {"posted_slack_digest", "slack_summary_posted",
                     "post_weekly_summary", "nightly_audit_complete"}
    c30, c7 = _counts(detail_rows, slack_actions)
    m_slack_messages = {
        "count_30d": c30, "count_7d": c7,
        "rows": [{"day": r.day, "action": r.action}
                 for r in _filter(detail_rows, slack_actions)[:60]],
    }

    # Slack approvals — show scale/pause/review breakdown from details
    approval_rows = _filter(detail_rows, {"posted_approvals_digest", "approval_requested"})
    apr_c30 = sum(1 for r in approval_rows if r.day >= cutoff_30)
    apr_c7  = sum(1 for r in approval_rows if r.day >= cutoff_7)
    m_slack_approvals = {
        "count_30d": apr_c30, "count_7d": apr_c7,
        "rows": [{"day": r.day,
                  "scale":  r.dig_scale  or 0,
                  "pause":  r.dig_pause  or 0,
                  "review": r.dig_review or 0}
                 for r in approval_rows[:60]],
    }

    # BQ collections
    bq_col_rows = [r for r in infra_rows if r.action.startswith("collect_")]
    bc_c30 = sum(r.cnt for r in bq_col_rows if r.day >= cutoff_30)
    bc_c7  = sum(r.cnt for r in bq_col_rows if r.day >= cutoff_7)
    m_bq_collections = {
        "count_30d": bc_c30, "count_7d": bc_c7,
        "rows": [{"day": r.day, "action": r.action, "cnt": r.cnt}
                 for r in bq_col_rows[:100]],
    }

    # Reports refreshed
    rep_rows = [r for r in infra_rows if r.action in
                ("refresh_hex_notebooks", "refresh_complete", "refresh_views")]
    rr_c30 = len([r for r in rep_rows if r.day >= cutoff_30])
    rr_c7  = len([r for r in rep_rows if r.day >= cutoff_7])
    m_reports_refreshed = {
        "count_30d": rr_c30, "count_7d": rr_c7,
        "rows": [{"day": r.day, "action": r.action} for r in rep_rows[:60]],
    }

    # Linked channels
    linked_ch = [{"channel": r.channel, "latest_date": str(r.latest_date),
                  "active": bool(r.active)} for r in channel_rows]
    m_linked_channels = {
        "count": len(linked_ch),
        "rows": linked_ch,
    }

    # ── Top-level totals ───────────────────────────────────────────────────────
    _all_30d_actions = [r for r in detail_rows if r.day >= cutoff_30]
    active_days = len({r.day for r in _all_30d_actions})
    totals = {
        "total_actions": sum(r.cnt for r in _all_30d_actions),
        "active_days":   active_days,
        "asana_tasks":   asana_c30,
        "linked_channels": len(linked_ch),
        "active_apis":   sum(1 for r in channel_rows if r.active),
    }

    # ── User actions ──────────────────────────────────────────────────────────
    _USER_ACTIONS = {
        "user_completed_task", "user_created_task", "user_executed_scale",
        "user_executed_pause", "user_added_negative", "user_reviewed_recommendation",
        "user_paused_campaign", "user_enabled_campaign", "user_changed_budget",
        "user_changed_status", "user_paused_ad", "user_enabled_ad",
    }
    user_sql = f"""
        SELECT
          DATE(ts, 'Asia/Riyadh')             AS day,
          action,
          role,
          JSON_VALUE(details, '$.title')      AS task_title,
          JSON_VALUE(details, '$.project_key') AS project_key,
          JSON_VALUE(details, '$.gid')         AS gid,
          JSON_VALUE(details, '$.completed_at') AS completed_at,
          campaign_name,
          channel,
          COALESCE(rows_affected, 1)           AS cnt
        FROM {T}.agent_activity_log
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
          AND (action IN UNNEST([
            'user_completed_task','user_created_task','user_executed_scale',
            'user_executed_pause','user_added_negative','user_reviewed_recommendation'
          ]) OR role = 'user')
          AND status NOT IN ('failed','skipped')
        ORDER BY ts DESC
        LIMIT 200
    """
    user_rows = []
    try:
        user_rows = list(bq.query(user_sql).result())
    except Exception as e:
        print(f"[activity] user_actions query failed (non-fatal): {e}")

    ua_c30 = sum(r.cnt for r in user_rows if r.day >= cutoff_30)
    ua_c7  = sum(r.cnt for r in user_rows if r.day >= cutoff_7)

    _ACTION_LABELS = {
        "user_completed_task":          "Completed task",
        "user_created_task":            "Created task",
        "user_executed_scale":          "Executed scale",
        "user_executed_pause":          "Executed pause",
        "user_added_negative":          "Added negative keyword",
        "user_reviewed_recommendation": "Reviewed recommendation",
        "user_paused_campaign":         "Paused campaign (direct)",
        "user_enabled_campaign":        "Enabled campaign (direct)",
        "user_changed_budget":          "Changed budget (direct)",
        "user_changed_status":          "Changed status (direct)",
        "user_paused_ad":               "Paused ad (direct)",
        "user_enabled_ad":              "Enabled ad (direct)",
    }
    m_user_actions = {
        "count_30d": ua_c30, "count_7d": ua_c7,
        "rows": [
            {
                "day":        str(r.day),
                "action":     _ACTION_LABELS.get(r.action, r.action.replace("_", " ").title()),
                "task_title": r.task_title or "—",
                "project_key": r.project_key or "—",
                "channel":    r.channel or "—",
                "campaign":   r.campaign_name or "—",
            }
            for r in user_rows[:100]
        ],
    }

    # ── Intelligence / ops actions (LLM, spikes, bot replies, data quality) ──
    intel_sql = f"""
        SELECT
          DATE(ts, 'Asia/Riyadh')              AS day,
          action,
          role,
          channel,
          campaign_name,
          COALESCE(rows_affected, 1)            AS cnt,
          JSON_VALUE(details, '$.model')        AS model,
          JSON_VALUE(details, '$.issue_type')   AS issue_type,
          CAST(JSON_VALUE(details, '$.cost_usd') AS FLOAT64) AS cost_usd,
          CAST(JSON_VALUE(details, '$.tokens_in') AS INT64)  AS tokens_in,
          CAST(JSON_VALUE(details, '$.tokens_out') AS INT64) AS tokens_out
        FROM {T}.agent_activity_log
        WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
          AND status NOT IN ('failed','skipped')
          AND action IN (
            'llm_role_ran','detect_spikes','slack_listener_reply',
            'data_quality_autoheal','weekly_autofix'
          )
        ORDER BY ts DESC
        LIMIT 300
    """
    intel_rows = []
    try:
        intel_rows = list(bq.query(intel_sql).result())
    except Exception as e:
        print(f"[activity] intel query failed (non-fatal): {e}")

    def _icounts(action):
        c30 = sum(r.cnt for r in intel_rows if r.action == action and r.day >= cutoff_30)
        c7  = sum(r.cnt for r in intel_rows if r.action == action and r.day >= cutoff_7)
        return c30, c7

    llm_c30, llm_c7 = _icounts("llm_role_ran")
    m_llm_runs = {
        "count_30d": llm_c30, "count_7d": llm_c7,
        "total_cost": round(sum((r.cost_usd or 0) for r in intel_rows if r.action == "llm_role_ran"), 4),
        "total_tokens": sum((r.tokens_in or 0) + (r.tokens_out or 0) for r in intel_rows if r.action == "llm_role_ran"),
        "rows": [{"day": str(r.day), "model": r.model or "claude-sonnet-4-6",
                  "tokens_in": r.tokens_in or 0, "tokens_out": r.tokens_out or 0,
                  "cost_usd": round(r.cost_usd or 0, 4)}
                 for r in intel_rows if r.action == "llm_role_ran"][:60],
    }

    sp_c30, sp_c7 = _icounts("detect_spikes")
    m_spike_detections = {
        "count_30d": sp_c30, "count_7d": sp_c7,
        "rows": [{"day": str(r.day), "channel": r.channel or "—",
                  "campaign": r.campaign_name or "—", "cnt": r.cnt}
                 for r in intel_rows if r.action == "detect_spikes"][:60],
    }

    sb_c30, sb_c7 = _icounts("slack_listener_reply")
    m_slack_bot = {
        "count_30d": sb_c30, "count_7d": sb_c7,
        "rows": [{"day": str(r.day), "tokens_in": r.tokens_in or 0,
                  "tokens_out": r.tokens_out or 0}
                 for r in intel_rows if r.action == "slack_listener_reply"][:60],
    }

    dq_c30, dq_c7 = _icounts("data_quality_autoheal")
    m_data_quality = {
        "count_30d": dq_c30, "count_7d": dq_c7,
        "rows": [{"day": str(r.day), "issue_type": r.issue_type or "—",
                  "channel": r.channel or "—", "cnt": r.cnt}
                 for r in intel_rows if r.action == "data_quality_autoheal"][:60],
    }

    # ── Sidebar categories (totals over selected window) ──────────────────────
    sidebar_raw: dict[str, int] = {}
    for r in detail_rows:
        cat = _CAT_MAP.get(r.action)
        if cat:
            sidebar_raw[cat] = sidebar_raw.get(cat, 0) + int(r.cnt)
    for r in infra_rows:
        if r.action.startswith("collect_"):
            sidebar_raw["Data Collections"] = sidebar_raw.get("Data Collections", 0) + int(r.cnt)
        elif r.action in ("refresh_hex_notebooks", "refresh_complete", "refresh_views"):
            sidebar_raw["Reports Refreshed"] = sidebar_raw.get("Reports Refreshed", 0) + int(r.cnt)
    total_sidebar = max(sum(sidebar_raw.values()), 1)
    sidebar_cats = [
        {"name": k, "count": v, "pct": round(v / total_sidebar * 100)}
        for k, v in sorted(sidebar_raw.items(), key=lambda x: -x[1])
    ]

    # ── Recent activity feed ───────────────────────────────────────────────────
    recent_activity = [
        {
            "ts":       str(r.day),
            "category": _CAT_MAP.get(r.action, r.action.replace("_", " ").title()),
            "channel":  r.channel or "—",
            "campaign": r.campaign_name or "—",
            "count":    r.cnt,
        }
        for r in detail_rows[:80]
    ]

    metrics = {
        "campaigns_created":  m_campaigns_created,
        "campaigns_paused":   m_campaigns_paused,
        "campaigns_scaled":   m_campaigns_scaled,
        "campaign_audits":    m_campaign_audits,
        "keywords_added":     m_keywords_added,
        "keywords_paused":    m_keywords_paused,
        "negatives_added":    m_negatives_added,
        "optimizations":      m_optimizations,
        "asana_tasks":        m_asana_tasks,
        "creative_reviews":   m_creative_reviews,
        "slack_messages":     m_slack_messages,
        "slack_approvals":    m_slack_approvals,
        "bq_collections":     m_bq_collections,
        "reports_refreshed":  m_reports_refreshed,
        "linked_channels":    m_linked_channels,
        "user_actions":       m_user_actions,
        "llm_runs":           m_llm_runs,
        "spike_detections":   m_spike_detections,
        "slack_bot":          m_slack_bot,
        "data_quality":       m_data_quality,
    }

    # ── 5. Asana task completion status ───────────────────────────────────────
    task_status_rows = []
    try:
        ts_sql = f"""
            SELECT
              a.gid,
              COALESCE(s.title, a.title, JSON_VALUE(al.details, '$.title')) AS title,
              COALESCE(s.project_key, a.project_key)                         AS project_key,
              COALESCE(s.completed, FALSE)                                    AS completed,
              s.completed_at,
              s.assignee_name,
              s.due_on,
              DATE(al.ts, 'Asia/Riyadh')                                      AS created_day
            FROM (
              SELECT DISTINCT
                JSON_VALUE(details, '$.gid')        AS gid,
                JSON_VALUE(details, '$.title')      AS title,
                JSON_VALUE(details, '$.project_key') AS project_key,
                ts
              FROM `{T}.agent_activity_log`
              WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
                AND action = 'asana_task_created'
                AND JSON_VALUE(details, '$.gid') IS NOT NULL
            ) a
            LEFT JOIN `{T}.agent_activity_log` al
              ON JSON_VALUE(al.details, '$.gid') = a.gid
              AND al.action = 'asana_task_created'
            LEFT JOIN (
              SELECT gid, title, project_key, completed, completed_at,
                     assignee_name, due_on,
                     ROW_NUMBER() OVER (PARTITION BY gid ORDER BY synced_at DESC) AS rn
              FROM `{T}.asana_task_status`
            ) s ON s.gid = a.gid AND s.rn = 1
            ORDER BY a.ts DESC
            LIMIT 150
        """
        task_status_rows = list(bq.query(ts_sql).result())
    except Exception as e:
        print(f"[activity] asana_task_status query failed (non-fatal): {e}")

    completed_tasks  = [r for r in task_status_rows if r.completed]
    pending_tasks    = [r for r in task_status_rows if not r.completed]
    asana_completion = {
        "total":     len(task_status_rows),
        "completed": len(completed_tasks),
        "pending":   len(pending_tasks),
        "pct_done":  round(len(completed_tasks) / max(len(task_status_rows), 1) * 100),
        "completed_rows": [
            {"gid": r.gid, "title": r.title or "—", "project_key": r.project_key or "—",
             "created_day": str(r.created_day or ""), "completed_at": str(r.completed_at or ""),
             "assignee": r.assignee_name or "—"}
            for r in completed_tasks[:60]
        ],
        "pending_rows": [
            {"gid": r.gid, "title": r.title or "—", "project_key": r.project_key or "—",
             "created_day": str(r.created_day or ""), "due_on": str(r.due_on or ""),
             "assignee": r.assignee_name or "—"}
            for r in pending_tasks[:60]
        ],
    }

    # ── 6. Channel follow-up: outcome of agent actions ─────────────────────────
    followup_rows = []
    try:
        fu_sql = f"""
            WITH actions AS (
              SELECT
                DATE(ts, 'Asia/Riyadh')                         AS action_date,
                action,
                channel,
                campaign_name,
                CAST(JSON_VALUE(details, '$.new_budget_usd') AS FLOAT64) AS target_budget
              FROM `{T}.agent_activity_log`
              WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
                AND action IN ('campaign_paused','campaign_scaled','campaign_created','ads_paused')
                AND campaign_name IS NOT NULL
            ),
            perf AS (
              SELECT
                a.action,
                a.action_date,
                a.channel,
                a.campaign_name,
                a.target_budget,
                ROUND(AVG(CASE WHEN c.date > a.action_date THEN c.spend END), 2)  AS avg_spend_after,
                ROUND(AVG(CASE WHEN c.date BETWEEN DATE_SUB(a.action_date, INTERVAL 7 DAY)
                                           AND a.action_date THEN c.spend END), 2) AS avg_spend_before,
                MAX(CASE WHEN c.date > a.action_date THEN c.status END)            AS latest_status,
                COUNT(CASE WHEN c.date > a.action_date AND c.spend > 0 THEN 1 END) AS active_days_after
              FROM actions a
              LEFT JOIN `{T}.campaigns_daily` c USING (campaign_name)
              GROUP BY 1,2,3,4,5
            )
            SELECT *,
              CASE
                WHEN action = 'campaign_paused' AND active_days_after > 0 THEN 'Re-enabled'
                WHEN action = 'campaign_paused' AND active_days_after = 0 THEN 'Confirmed paused'
                WHEN action = 'campaign_scaled' AND avg_spend_after > avg_spend_before THEN 'Spend increased'
                WHEN action = 'campaign_scaled' AND avg_spend_after IS NULL THEN 'No data yet'
                WHEN action = 'campaign_scaled' THEN 'Spend unchanged'
                WHEN action = 'campaign_created' THEN
                  CASE WHEN active_days_after > 0 THEN 'Running' ELSE 'Not spending' END
                ELSE 'Paused'
              END AS outcome
            FROM perf
            ORDER BY action_date DESC
            LIMIT 80
        """
        followup_rows = list(bq.query(fu_sql).result())
    except Exception as e:
        print(f"[activity] follow-up query failed (non-fatal): {e}")

    # New ads in platform (first seen recently — not from agent campaign creation)
    new_ads_rows = []
    try:
        new_ads_sql = f"""
            SELECT
              MIN(date)        AS first_seen,
              channel,
              campaign_name,
              ad_name,
              ROUND(SUM(spend), 2) AS total_spend,
              SUM(impressions)     AS impressions
            FROM `{T}.ads_daily`
            WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
            GROUP BY channel, campaign_name, ad_name
            HAVING MIN(date) >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
               AND SUM(spend) > 0
            ORDER BY first_seen DESC
            LIMIT 60
        """
        new_ads_rows = [
            {"first_seen": str(r.first_seen), "channel": r.channel or "—",
             "campaign_name": r.campaign_name or "—", "ad_name": r.ad_name or "—",
             "total_spend": r.total_spend or 0, "impressions": r.impressions or 0}
            for r in bq.query(new_ads_sql).result()
        ]
    except Exception as e:
        print(f"[activity] new_ads query failed (non-fatal): {e}")

    followup = {
        "campaign_actions": [
            {"action_date": str(r.action_date), "action": r.action,
             "channel": r.channel or "—", "campaign_name": r.campaign_name or "—",
             "target_budget": r.target_budget, "avg_spend_after": r.avg_spend_after,
             "avg_spend_before": r.avg_spend_before, "latest_status": r.latest_status or "—",
             "active_days_after": r.active_days_after, "outcome": r.outcome}
            for r in followup_rows
        ],
        "new_ads": new_ads_rows,
    }

    return render_template(
        "activity.html",
        last_updated=now_str,
        date_label=date_label,
        days=days,
        heatmap_rows=heatmap_rows,
        metrics=metrics,
        totals=totals,
        recent_activity=recent_activity,
        sidebar_cats=sidebar_cats,
        workflows=_WORKFLOWS,
        asana_completion=asana_completion,
        followup=followup,
    )


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



# DASHBOARD_URL / ACTIVITY_DASHBOARD_URL = short Railway URLs shown in Slack/email/Asana
# DASHBOARD_DEST_URL / ACTIVITY_DEST_URL = full Hex URLs that /dashboard and /activity redirect to

@app.route("/dashboard")
def dashboard_short():
    """Short link → Hex performance dashboard."""
    dest = os.getenv("DASHBOARD_DEST_URL") or "https://app.hex.tech"
    return redirect(dest, code=302)


@app.route("/activity")
def activity_short():
    """Short link → Hex agent activity dashboard."""
    dest = os.getenv("ACTIVITY_DEST_URL") or "https://app.hex.tech"
    return redirect(dest, code=302)


@app.route("/")
@app.route("/paid-performance/latest")
@app.route("/paid-performance/<report_date>")
@app.route("/reports/latest")
@app.route("/reports/<report_date>")
def dashboard_redirect(**kwargs):
    """Legacy HTML report URLs → Hex performance dashboard."""
    return redirect(_HEX_DASHBOARD, code=301)



# ─── Removed: /api/report (HTML report custom date-range API) ────────────────
# Hex dashboard replaces the HTML report. Route removed 2026-05-04.


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
            try:
                from logs.activity_logger import log_activity_async
                log_activity_async(role="slack_approval",
                                   action="action_approved_via_slack",
                                   status="approved", channel=meta.get("channel", ""),
                                   campaign_name=camp,
                                   details={"user": user, "requested_action": action,
                                            "result": exec_result[:200]})
            except Exception:
                pass
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
            try:
                from logs.activity_logger import log_activity_async
                log_activity_async(role="slack_approval",
                                   action="action_rejected_via_slack",
                                   status="rejected", channel=meta.get("channel", ""),
                                   campaign_name=camp,
                                   details={"user": user, "requested_action": action})
            except Exception:
                pass

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
            elif channel == "linkedin":
                from executors.linkedin import set_campaign_budget
                set_campaign_budget(campaign_id, new_budget)
            else:
                return f"Channel `{channel}` not supported for auto-scale. Set budget to ${new_budget:.0f}/day manually."
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="execution", action="campaign_scaled",
                channel=channel, campaign_name=campaign,
                details={"new_budget_usd": new_budget, "campaign_id": campaign_id},
            )
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
            elif channel == "linkedin":
                from executors.linkedin import pause_campaign
                pause_campaign(campaign_id)
            else:
                return f"Channel `{channel}` not supported for auto-pause. Pause `{campaign}` manually."
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="execution", action="campaign_paused",
                channel=channel, campaign_name=campaign,
                details={"campaign_id": campaign_id},
            )
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


# ─── Startup: warn if pending approvals were lost on redeploy ─────────────────

def _check_pending_on_startup():
    """Log any surviving pending approvals so we know the state on boot."""
    try:
        from notifications.slack import _load_pending
        pending = _load_pending()
        if pending:
            print(f"[startup] {len(pending)} pending approval(s) survived redeploy: "
                  f"{list(pending.keys())}")
        else:
            print("[startup] No pending approvals on disk.")
    except Exception as e:
        print(f"[startup] Could not read pending approvals: {e}")

_check_pending_on_startup()


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
