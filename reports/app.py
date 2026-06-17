"""
reports/app.py
==============
Thin Flask app for the Nexa Performance Agent activity dashboard.

Routes:
  GET  /health                      → {"status": "ok"}
  GET  /                            → redirect to /activity
  GET  /activity                    → self-contained HTML dashboard
  POST /api/ondemand/<task>         → proxy POST to n8n webhook URL

On-demand tasks proxy to n8n webhook URLs. Results arrive in Slack #approvals.
No secrets, no subprocesses, no background threads.
"""
from __future__ import annotations

import os
import requests
from flask import Flask, jsonify, redirect, request


# ─── n8n webhook map ──────────────────────────────────────────────────────────

N8N_BASE = "https://qoyod.app.n8n.cloud/webhook"

ONDEMAND_ROUTES: dict[str, str] = {
    # Performance Operations
    "keyword-audit":     f"{N8N_BASE}/od-keyword-audit",
    "ad-audit":          f"{N8N_BASE}/od-ad-audit",
    "campaign-health":   f"{N8N_BASE}/od-campaign-health",
    # Creative Strategist
    "creative-audit":    f"{N8N_BASE}/od-creative-audit",
    "creative-brief":    f"{N8N_BASE}/od-creative-brief",
    "creative-analysis": f"{N8N_BASE}/od-creative-analysis",
    # Performance Lead
    "campaign-brief":    f"{N8N_BASE}/od-campaign-brief",
    "monthly-plan":      f"{N8N_BASE}/od-monthly-plan",
    "quarterly-plan":    f"{N8N_BASE}/od-quarterly-plan",
    # Technical Health
    "connector-health":  f"{N8N_BASE}/od-connector-health",
    "gtm-audit":         f"{N8N_BASE}/od-gtm-audit",
    "lp-brief":          f"{N8N_BASE}/od-lp-brief",
}


# ─── App factory ─────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    # -- Health check ---------------------------------------------------------

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "nexa-activity-dashboard"})

    # -- Root redirect --------------------------------------------------------

    @app.get("/")
    def root():
        return redirect("/activity", code=302)

    # -- Activity dashboard ---------------------------------------------------

    @app.get("/activity")
    def activity():
        return _render_dashboard()

    # -- On-demand proxy ------------------------------------------------------

    @app.post("/api/ondemand/<task>")
    def ondemand(task: str):
        if task not in ONDEMAND_ROUTES:
            return jsonify({"error": f"Unknown task: {task}"}), 404

        webhook_url = ONDEMAND_ROUTES[task]
        payload = request.get_json(silent=True) or {}
        payload.setdefault("triggered_by", "dashboard")

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code == 404:
                return jsonify({
                    "status": "not_configured",
                    "task": task,
                    "message": f"Webhook not configured yet — create n8n workflow `od-{task}`",
                }), 200
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return jsonify({
                "status": "not_configured",
                "task": task,
                "message": f"Webhook not configured yet — create n8n workflow `od-{task}`",
            }), 200
        except requests.exceptions.Timeout:
            # n8n may take a moment — treat as triggered
            pass
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return jsonify({
                    "status": "not_configured",
                    "task": task,
                    "message": f"Webhook not configured yet — create n8n workflow `od-{task}`",
                }), 200
            return jsonify({"status": "error", "task": task, "message": str(exc)}), 502

        return jsonify({
            "status": "triggered",
            "task": task,
            "message": "Running… results will arrive in Slack #approvals",
        })

    return app


# ─── Dashboard HTML (self-contained, no Jinja templates) ─────────────────────

def _render_dashboard() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nexa Performance Agent</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0d0d0d;
    --card:     #1a1a1a;
    --border:   #2a2a2a;
    --accent:   #00ff88;
    --accent2:  #58a6ff;
    --warn:     #f0883e;
    --muted:    #888;
    --text:     #e6e6e6;
    --text-dim: #aaa;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 16px 24px;
    border-bottom: 1px solid var(--border);
    background: #111;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  header h1 {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0.3px;
  }
  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 6px var(--accent);
    flex-shrink: 0;
  }
  .header-tag {
    margin-left: auto;
    font-size: 11px;
    color: var(--muted);
    background: #222;
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--border);
  }

  /* ── Layout ── */
  main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 28px 20px 60px;
  }

  /* ── Section title ── */
  .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--muted);
    margin: 32px 0 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .section-title::after {
    content: "";
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  /* ── Card grid ── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
  }
  @media (max-width: 800px) {
    .card-grid { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 520px) {
    .card-grid { grid-template-columns: 1fr; }
  }

  /* ── Card ── */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: border-color 0.15s;
  }
  .card:hover { border-color: #3a3a3a; }

  .card-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
  }
  .card-desc {
    font-size: 12px;
    color: var(--text-dim);
    flex: 1;
  }
  .card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 4px;
    gap: 8px;
  }
  .card-slack-note {
    font-size: 11px;
    color: var(--muted);
  }

  /* ── Cadence card (read-only) ── */
  .cadence-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .cadence-name {
    font-size: 13px;
    font-weight: 600;
  }
  .cadence-schedule {
    font-size: 11px;
    color: var(--muted);
    background: #111;
    padding: 3px 8px;
    border-radius: 4px;
    font-family: monospace;
  }
  .cadence-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
  }
  @media (max-width: 600px) {
    .cadence-grid { grid-template-columns: 1fr; }
  }

  /* ── Role badge ── */
  .role-header {
    grid-column: 1 / -1;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--accent2);
    padding: 8px 0 2px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2px;
  }
  .role-header.creative { color: #d2a8ff; }
  .role-header.ops { color: var(--warn); }
  .role-header.tech { color: var(--muted); }

  /* ── Run button ── */
  .btn-run {
    font-size: 12px;
    font-weight: 600;
    padding: 6px 14px;
    border-radius: 5px;
    border: none;
    background: var(--accent);
    color: #0d0d0d;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s, background 0.15s;
  }
  .btn-run:hover { opacity: 0.85; }
  .btn-run:disabled {
    background: #333;
    color: var(--muted);
    cursor: not-allowed;
  }

  /* ── Status message ── */
  .card-status {
    font-size: 11px;
    min-height: 16px;
    transition: color 0.2s;
  }
  .card-status.ok   { color: var(--accent); }
  .card-status.err  { color: var(--warn); }
  .card-status.spin { color: var(--text-dim); }
</style>
</head>
<body>

<header>
  <div class="status-dot"></div>
  <h1>Nexa Performance Agent</h1>
  <span class="header-tag">Railway &bull; Live</span>
</header>

<main>

  <!-- ── Cadence Flows ── -->
  <div class="section-title">Cadence Flows</div>
  <div class="cadence-grid">

    <div class="cadence-card">
      <div>
        <div class="cadence-name">Daily Master</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px;">
          Full daily analysis — spend, leads, CPQL, anomaly detection, Slack summary
        </div>
      </div>
      <div class="cadence-schedule">05:00 UTC daily</div>
    </div>

    <div class="cadence-card">
      <div>
        <div class="cadence-name">Weekly Review</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px;">
          7-day vs prior-7 period comparison, keyword autofix, forecasting
        </div>
      </div>
      <div class="cadence-schedule">Sun 05:00 UTC</div>
    </div>

    <div class="cadence-card">
      <div>
        <div class="cadence-name">Monthly Review</div>
        <div style="font-size:11px;color:var(--muted);margin-top:3px;">
          MoM review, OKR tracking, budget reconciliation, next-month planning
        </div>
      </div>
      <div class="cadence-schedule">1st 05:00 UTC</div>
    </div>

  </div>

  <!-- ── On-Demand Tasks ── -->
  <div class="section-title">On-Demand Tasks</div>

  <div class="card-grid">

    <!-- Performance Lead -->
    <div class="role-header">Performance Lead</div>

    <div class="card">
      <div class="card-title">Campaign Brief</div>
      <div class="card-desc">Full brief for a new campaign including audience, creative direction, budget</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'campaign-brief')">Run</button>
      </div>
      <div class="card-status spin" id="status-campaign-brief"></div>
    </div>

    <div class="card">
      <div class="card-title">Monthly Plan</div>
      <div class="card-desc">Monthly performance plan with targets and channel allocation</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'monthly-plan')">Run</button>
      </div>
      <div class="card-status spin" id="status-monthly-plan"></div>
    </div>

    <div class="card">
      <div class="card-title">Quarterly Plan</div>
      <div class="card-desc">Quarterly strategy plan with OKRs and budget roadmap</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'quarterly-plan')">Run</button>
      </div>
      <div class="card-status spin" id="status-quarterly-plan"></div>
    </div>

    <!-- Creative Strategist -->
    <div class="role-header creative">Creative Strategist</div>

    <div class="card">
      <div class="card-title">Creative Analysis</div>
      <div class="card-desc">Analyse creatives by qualified leads, CTR, views (video-aware)</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'creative-analysis')">Run</button>
      </div>
      <div class="card-status spin" id="status-creative-analysis"></div>
    </div>

    <div class="card">
      <div class="card-title">Creative Audit</div>
      <div class="card-desc">Audit live creatives for policy, format, and quality issues</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'creative-audit')">Run</button>
      </div>
      <div class="card-status spin" id="status-creative-audit"></div>
    </div>

    <div class="card">
      <div class="card-title">Creative Brief</div>
      <div class="card-desc">Generate brief for next creative batch</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'creative-brief')">Run</button>
      </div>
      <div class="card-status spin" id="status-creative-brief"></div>
    </div>

    <!-- Performance Operations -->
    <div class="role-header ops">Performance Operations</div>

    <div class="card">
      <div class="card-title">Keyword Audit</div>
      <div class="card-desc">Scan enabled keywords for policy violations</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'keyword-audit')">Run</button>
      </div>
      <div class="card-status spin" id="status-keyword-audit"></div>
    </div>

    <div class="card">
      <div class="card-title">Ad Audit</div>
      <div class="card-desc">Scan live ads for pause candidates (zero-conv, junk leads, high CPL)</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'ad-audit')">Run</button>
      </div>
      <div class="card-status spin" id="status-ad-audit"></div>
    </div>

    <div class="card">
      <div class="card-title">Campaign Health</div>
      <div class="card-desc">ROAS + CPL + CPQL health check across all channels</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'campaign-health')">Run</button>
      </div>
      <div class="card-status spin" id="status-campaign-health"></div>
    </div>

    <!-- Technical Health -->
    <div class="role-header tech">Technical Health</div>

    <div class="card">
      <div class="card-title">Connector Health</div>
      <div class="card-desc">Check all data connectors and BQ freshness</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'connector-health')">Run</button>
      </div>
      <div class="card-status spin" id="status-connector-health"></div>
    </div>

    <div class="card">
      <div class="card-title">GTM Audit</div>
      <div class="card-desc">Audit GTM containers (web + server) for tag and trigger issues</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'gtm-audit')">Run</button>
      </div>
      <div class="card-status spin" id="status-gtm-audit"></div>
    </div>

    <div class="card">
      <div class="card-title">LP Brief</div>
      <div class="card-desc">Landing page brief with CRO hypothesis for next test</div>
      <div class="card-footer">
        <span class="card-slack-note">Results &rarr; Slack #approvals</span>
        <button class="btn-run" onclick="triggerTask(this, 'lp-brief')">Run</button>
      </div>
      <div class="card-status spin" id="status-lp-brief"></div>
    </div>

  </div><!-- /card-grid -->

</main>

<script>
async function triggerTask(btn, task) {
  const statusEl = document.getElementById('status-' + task);
  btn.disabled = true;
  btn.textContent = '...';
  statusEl.className = 'card-status spin';
  statusEl.textContent = 'Triggering…';

  try {
    const res = await fetch('/api/ondemand/' + task, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ triggered_by: 'dashboard' }),
    });
    const data = await res.json();

    if (data.status === 'triggered') {
      statusEl.className = 'card-status ok';
      statusEl.textContent = 'Triggered ✓ — check Slack';
      btn.textContent = 'Run';
      btn.disabled = false;
    } else if (data.status === 'not_configured') {
      statusEl.className = 'card-status err';
      statusEl.textContent = data.message || ('Webhook not configured yet — create n8n workflow `od-' + task + '`');
      btn.textContent = 'Run';
      btn.disabled = false;
    } else {
      statusEl.className = 'card-status err';
      statusEl.textContent = data.message || 'Unknown error';
      btn.textContent = 'Run';
      btn.disabled = false;
    }
  } catch (err) {
    statusEl.className = 'card-status err';
    statusEl.textContent = 'Network error — is Railway reachable?';
    btn.textContent = 'Run';
    btn.disabled = false;
  }
}
</script>

</body>
</html>"""
