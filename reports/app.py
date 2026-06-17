"""
reports/app.py
==============
Thin Flask app for the Nexa Performance Agent activity dashboard.

Routes:
  GET  /health                      → {"status": "ok"}
  GET  /                            → redirect to /activity
  GET  /activity                    → self-contained HTML dashboard
  POST /api/ondemand/<task>         → proxy POST to n8n webhook URL

On-demand tasks proxy to n8n webhook URLs. Results arrive in Slack #approvals
or #data-health depending on the task.
No secrets, no subprocesses, no background threads.
"""
from __future__ import annotations

import os
import requests
from flask import Flask, jsonify, redirect, request


# ─── n8n webhook map ──────────────────────────────────────────────────────────

N8N_BASE = "https://qoyod.app.n8n.cloud/webhook"

ONDEMAND_ROUTES: dict[str, str] = {
    # Performance Lead
    "campaign-brief":       f"{N8N_BASE}/od-campaign-brief",
    "monthly-plan":         f"{N8N_BASE}/od-monthly-plan",
    "quarterly-plan":       f"{N8N_BASE}/od-quarterly-plan",
    "kpi-review":           f"{N8N_BASE}/od-kpi-review",
    # Campaign Manager (under Performance Lead)
    "keyword-audit":        f"{N8N_BASE}/od-keyword-audit",
    "ad-audit":             f"{N8N_BASE}/od-ad-audit",
    "campaign-health":      f"{N8N_BASE}/od-campaign-health",
    "scale-proposal":       f"{N8N_BASE}/od-scale-proposal",
    # Creative Strategist (under Performance Lead)
    "creative-analysis":    f"{N8N_BASE}/od-creative-analysis",
    "creative-brief":       f"{N8N_BASE}/od-creative-brief",
    "creative-audit":       f"{N8N_BASE}/od-creative-audit",
    "ocean-persona":        f"{N8N_BASE}/od-ocean-persona",
    # CRO Specialist
    "lp-brief":             f"{N8N_BASE}/od-lp-brief",
    "lp-analysis":          f"{N8N_BASE}/od-lp-analysis",
    # Growth Analyst
    "period-compare":       f"{N8N_BASE}/od-period-compare",
    "campaign-drilldown":   f"{N8N_BASE}/od-campaign-drilldown",
    "forecast":             f"{N8N_BASE}/od-forecast",
    # Project Coordinator
    "connector-health":     f"{N8N_BASE}/od-connector-health",
    "gtm-audit":            f"{N8N_BASE}/od-gtm-audit",
    "utm-validate":         f"{N8N_BASE}/od-utm-validate",
    "pixel-health":         f"{N8N_BASE}/od-pixel-health",
}

# Tasks that post to #data-health instead of #approvals
DATA_HEALTH_TASKS = {"connector-health", "utm-validate", "pixel-health"}


# ─── App factory ─────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "nexa-activity-dashboard"})

    @app.get("/")
    def root():
        return redirect("/activity", code=302)

    @app.get("/activity")
    def activity():
        return _render_dashboard()

    @app.post("/api/ondemand/<task>")
    def ondemand(task: str):
        if task not in ONDEMAND_ROUTES:
            return jsonify({"error": f"Unknown task: {task}"}), 404

        webhook_url = ONDEMAND_ROUTES[task]
        payload = request.get_json(silent=True) or {}
        payload.setdefault("triggered_by", "dashboard")
        channel = "#data-health" if task in DATA_HEALTH_TASKS else "#approvals"

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
            "message": f"Running… results will arrive in Slack {channel}",
        })

    return app


# ─── Dashboard HTML ───────────────────────────────────────────────────────────

def _render_dashboard() -> str:
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nexa Performance Agent</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d0d0d;--card:#1a1a1a;--panel:#141414;--border:#2a2a2a;
  --text:#e6e6e6;--dim:#aaa;--muted:#888;
  --blue:#58a6ff;--lblue:#79c0ff;--purple:#d2a8ff;
  --orange:#f0883e;--green:#3fb950;--grey:#8b949e;--accent:#00ff88;
}
body{background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  font-size:14px;line-height:1.5;min-height:100vh}
header{display:flex;align-items:center;gap:10px;padding:16px 24px;
  border-bottom:1px solid var(--border);background:#111;
  position:sticky;top:0;z-index:100}
header h1{font-size:16px;font-weight:600;letter-spacing:.3px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 6px var(--accent);flex-shrink:0}
.htag{margin-left:auto;font-size:11px;color:var(--muted);background:#222;
  padding:3px 8px;border-radius:4px;border:1px solid var(--border)}
main{max-width:1160px;margin:0 auto;padding:28px 20px 60px}
.sec{font-size:11px;font-weight:600;text-transform:uppercase;
  letter-spacing:1.2px;color:var(--muted);margin:32px 0 14px;
  display:flex;align-items:center;gap:8px}
.sec::after{content:"";flex:1;height:1px;background:var(--border)}
/* cadence */
.cgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:700px){.cgrid{grid-template-columns:1fr}}
.ccard{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:14px 16px;display:flex;justify-content:space-between;
  align-items:flex-start;gap:12px}
.cname{font-size:13px;font-weight:600}
.cdesc{font-size:11px;color:var(--muted);margin-top:3px}
.csched{font-size:11px;color:var(--muted);background:#111;
  padding:3px 8px;border-radius:4px;font-family:monospace;white-space:nowrap;flex-shrink:0}
/* agent panels */
.agent-panel{border-left:4px solid var(--panel-color,#444);
  background:var(--panel);border-radius:8px;margin-bottom:18px;overflow:hidden}
.agent-header{display:flex;align-items:center;gap:10px;
  padding:14px 18px;border-bottom:1px solid var(--border);
  background:color-mix(in srgb,var(--panel-color,#444) 8%,var(--panel))}
.agent-icon{font-size:18px}
.agent-name{font-size:15px;font-weight:700;color:var(--panel-color,#e6e6e6)}
.agent-desc{font-size:12px;color:var(--dim);flex:1}
.dept-chip{font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;padding:2px 8px;border-radius:10px;
  border:1px solid currentColor;color:var(--panel-color,#888);opacity:.8;white-space:nowrap}
.agent-body{padding:16px 18px}
/* sub-agent */
.sub-panel{border-left:2px solid var(--sub-color,#444);
  background:color-mix(in srgb,var(--sub-color,#444) 5%,#0f0f0f);
  border-radius:6px;margin-bottom:14px;overflow:hidden}
.sub-header{display:flex;align-items:center;gap:8px;
  padding:10px 14px;border-bottom:1px solid var(--border)}
.sub-label{font-size:11px;color:var(--dim)}
.sub-name{font-size:13px;font-weight:700;color:var(--sub-color,#e6e6e6)}
.sub-desc{font-size:11px;color:var(--muted);flex:1}
.sub-body{padding:12px 14px}
/* card grid */
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--border);border-radius:7px;
  padding:14px;display:flex;flex-direction:column;gap:8px;
  transition:border-color .15s}
.card:hover{border-color:#3a3a3a}
.ctitle{font-size:13px;font-weight:600}
.cdesc2{font-size:12px;color:var(--dim);flex:1}
.cfoot{display:flex;align-items:center;justify-content:space-between;
  margin-top:4px;gap:6px}
.cnote{font-size:11px;color:var(--muted)}
.btn{font-size:11px;font-weight:600;padding:5px 12px;border-radius:5px;
  border:none;background:var(--btn-color,var(--accent));
  color:#0d0d0d;cursor:pointer;flex-shrink:0;transition:opacity .15s}
.btn:hover{opacity:.8}
.btn:disabled{background:#333;color:var(--muted);cursor:not-allowed}
.cst{font-size:11px;min-height:15px;transition:color .2s}
.cst.ok{color:var(--accent)}.cst.err{color:var(--orange)}.cst.spin{color:var(--dim)}
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>Nexa Performance Agent</h1>
  <span class="htag">n8n Cloud &bull; Railway</span>
</header>
<main>

<!-- CADENCE -->
<div class="sec">Cadence Flows</div>
<div class="cgrid">
  <div class="ccard">
    <div>
      <div class="cname">Daily Master</div>
      <div class="cdesc">Full daily analysis: spend, leads, CPQL, anomaly detection, Slack summary, pause/scale candidates</div>
    </div>
    <div class="csched">05:00 UTC daily</div>
  </div>
  <div class="ccard">
    <div>
      <div class="cname">Weekly Review</div>
      <div class="cdesc">7-day vs prior-7 period comparison, keyword autofix, channel flags, weekly Slack digest</div>
    </div>
    <div class="csched">Sun 05:00 UTC</div>
  </div>
  <div class="ccard">
    <div>
      <div class="cname">Monthly Review</div>
      <div class="cdesc">MoM review, OKR tracking, budget reconciliation, 30-day forecast</div>
    </div>
    <div class="csched">1st 05:00 UTC</div>
  </div>
</div>

<!-- ON-DEMAND -->
<div class="sec">On-Demand &mdash; by Agent</div>

<!-- ── Performance Lead ── -->
<div class="agent-panel" style="--panel-color:var(--blue)">
  <div class="agent-header">
    <span class="agent-icon">&#127775;</span>
    <span class="agent-name">Performance Lead</span>
    <span class="agent-desc">KPI thresholds &middot; budget allocation &middot; channel mix &middot; triage to Campaign Manager or Creative Strategist</span>
    <span class="dept-chip">Performance</span>
  </div>
  <div class="agent-body">
    <div class="grid" style="margin-bottom:16px">
      <div class="card">
        <div class="ctitle">Campaign Brief</div>
        <div class="cdesc2">Full brief for a new campaign: audience, creative direction, budget, naming, KPI gates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'campaign-brief')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-campaign-brief"></div>
      </div>
      <div class="card">
        <div class="ctitle">Monthly Plan</div>
        <div class="cdesc2">Monthly performance plan with targets, channel allocation, and action priorities</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'monthly-plan')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-monthly-plan"></div>
      </div>
      <div class="card">
        <div class="ctitle">Quarterly Plan</div>
        <div class="cdesc2">Quarterly strategy: OKRs, budget roadmap by month, risk &amp; upside analysis</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'quarterly-plan')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-quarterly-plan"></div>
      </div>
      <div class="card">
        <div class="ctitle">KPI Threshold Review</div>
        <div class="cdesc2">Review live CPQL/CPL/ROAS against config.py thresholds &mdash; flag if calibration needed</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--blue)" onclick="run(this,'kpi-review')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-kpi-review"></div>
      </div>
    </div>

    <!-- Campaign Manager sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--lblue)">
      <div class="sub-header">
        <span style="font-size:13px;color:var(--dim)">&ldquo;</span>
        <span class="sub-label">&#8618;&nbsp;</span>
        <span class="sub-name">Campaign Manager</span>
        <span class="sub-desc">Campaign optimization &middot; keyword policy &middot; ad audit &middot; scale &amp; pause proposals</span>
      </div>
      <div class="sub-body">
        <div class="grid">
          <div class="card">
            <div class="ctitle">Keyword Audit</div>
            <div class="cdesc2">Scan enabled keywords for policy violations: always-negative patterns, wrong language, QS&lt;5+IS&gt;80%</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'keyword-audit')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-keyword-audit"></div>
          </div>
          <div class="card">
            <div class="ctitle">Ad Audit</div>
            <div class="cdesc2">Scan live ads for pause candidates: zero-conv ($70/7d), junk leads (60%+ disqualified), high CPL (&gt;$50/10d)</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'ad-audit')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-ad-audit"></div>
          </div>
          <div class="card">
            <div class="ctitle">Campaign Health</div>
            <div class="cdesc2">ROAS &rarr; CPQL &rarr; CPL waterfall per channel. Flag campaigns outside KPI zones.</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'campaign-health')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-campaign-health"></div>
          </div>
          <div class="card">
            <div class="ctitle">Scale Proposal</div>
            <div class="cdesc2">Identify campaigns with CPQL &le;$60 over 14d and generate full scale proposals for #approvals</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--lblue)" onclick="run(this,'scale-proposal')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-scale-proposal"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Creative Strategist sub-panel -->
    <div class="sub-panel" style="--sub-color:var(--purple)">
      <div class="sub-header">
        <span style="font-size:13px;color:var(--dim)">&ldquo;</span>
        <span class="sub-label">&#8618;&nbsp;</span>
        <span class="sub-name">Creative Strategist</span>
        <span class="sub-desc">OCEAN persona mapping &middot; creative variants &middot; copy direction &middot; LP asset alignment</span>
      </div>
      <div class="sub-body">
        <div class="grid">
          <div class="card">
            <div class="ctitle">Creative Analysis</div>
            <div class="cdesc2">Rank creatives by qualified leads, CPQL, CTR, and video VTR (video-aware analysis)</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'creative-analysis')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-creative-analysis"></div>
          </div>
          <div class="card">
            <div class="ctitle">Creative Brief</div>
            <div class="cdesc2">Generate brief for next creative batch: winning patterns, variants, OCEAN mapping, copy hooks</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'creative-brief')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-creative-brief"></div>
          </div>
          <div class="card">
            <div class="ctitle">Creative Audit</div>
            <div class="cdesc2">Audit live creatives for fatigue (&gt;30d), duplicate variants, CTR &lt;0.5%, VTR &lt;15%</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'creative-audit')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-creative-audit"></div>
          </div>
          <div class="card">
            <div class="ctitle">OCEAN Persona Map</div>
            <div class="cdesc2">Map target audiences to OCEAN dimensions (O/C/E/A/N) for a product or campaign</div>
            <div class="cfoot">
              <span class="cnote">Results &rarr; #approvals</span>
              <button class="btn" style="--btn-color:var(--purple)" onclick="run(this,'ocean-persona')">Run &rarr;</button>
            </div>
            <div class="cst spin" id="st-ocean-persona"></div>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- ── CRO Specialist ── -->
<div class="agent-panel" style="--panel-color:var(--orange)">
  <div class="agent-header">
    <span class="agent-icon">&#127919;</span>
    <span class="agent-name">CRO Specialist</span>
    <span class="agent-desc">LP briefs &middot; qual ratio decisions &middot; A/B test hypotheses &middot; test result calls</span>
    <span class="dept-chip">CRO Chain</span>
  </div>
  <div class="agent-body">
    <div class="grid">
      <div class="card">
        <div class="ctitle">LP Brief</div>
        <div class="cdesc2">8-section LP brief: objective, OCEAN audience, hypothesis, success criteria, ZATCA badge, timeline</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--orange)" onclick="run(this,'lp-brief')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-lp-brief"></div>
      </div>
      <div class="card">
        <div class="ctitle">LP Performance Analysis</div>
        <div class="cdesc2">Analyse qual rate by destination_url. Flag LPs &lt;30% qual rate for immediate redirect.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--orange)" onclick="run(this,'lp-analysis')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-lp-analysis"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Growth Analyst ── -->
<div class="agent-panel" style="--panel-color:var(--green)">
  <div class="agent-header">
    <span class="agent-icon">&#128200;</span>
    <span class="agent-name">Growth Analyst</span>
    <span class="agent-desc">BQ analysis &middot; period comparisons &middot; flag investigations &middot; forecasts &middot; memory ownership</span>
    <span class="dept-chip">DATA</span>
  </div>
  <div class="agent-body">
    <div class="grid">
      <div class="card">
        <div class="ctitle">Period Comparison</div>
        <div class="cdesc2">7d vs prior-7d for all channels: spend, leads, SQLs, CPQL, CPL, ROAS, qual rate, IS, CTR</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--green)" onclick="run(this,'period-compare')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-period-compare"></div>
      </div>
      <div class="card">
        <div class="ctitle">Campaign Deep Dive</div>
        <div class="cdesc2">Root cause analysis on a specific CPQL/ROAS/qual flag: contributing factors, attribution</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--green)" onclick="run(this,'campaign-drilldown')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-campaign-drilldown"></div>
      </div>
      <div class="card">
        <div class="ctitle">Forecast</div>
        <div class="cdesc2">End-of-month projection: spend, leads, SQLs, CPQL, ROAS &mdash; status-quo vs post-action paths</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--green)" onclick="run(this,'forecast')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-forecast"></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Project Coordinator ── -->
<div class="agent-panel" style="--panel-color:var(--grey)">
  <div class="agent-header">
    <span class="agent-icon">&#128295;</span>
    <span class="agent-name">Project Coordinator</span>
    <span class="agent-desc">Connector health &middot; GTM audit &middot; UTM validation &middot; pixel health &middot; Asana task status</span>
    <span class="dept-chip">OPS</span>
  </div>
  <div class="agent-body">
    <div class="grid">
      <div class="card">
        <div class="ctitle">Connector Health</div>
        <div class="cdesc2">Check BQ freshness for all source tables. Flag STALE (&gt;12h) or DEAD (&gt;24h) connectors.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #data-health</span>
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'connector-health')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-connector-health"></div>
      </div>
      <div class="card">
        <div class="ctitle">GTM Audit</div>
        <div class="cdesc2">Audit GTM-TFH26VC2 (web) + GTM-PK6924TJ (server): pixel tags, UTM passthrough, duplicates</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #approvals</span>
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'gtm-audit')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-gtm-audit"></div>
      </div>
      <div class="card">
        <div class="ctitle">UTM Validation</div>
        <div class="cdesc2">Scan all live campaign names against naming convention: {Channel}_{Type}_{Language}_{Product}_{Audience}</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #data-health</span>
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'utm-validate')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-utm-validate"></div>
      </div>
      <div class="card">
        <div class="ctitle">Meta Pixel Health</div>
        <div class="cdesc2">Verify both Meta pixels fire on every LP form submit. Flag gaps in Events Manager.</div>
        <div class="cfoot">
          <span class="cnote">Results &rarr; #data-health</span>
          <button class="btn" style="--btn-color:var(--grey)" onclick="run(this,'pixel-health')">Run &rarr;</button>
        </div>
        <div class="cst spin" id="st-pixel-health"></div>
      </div>
    </div>
  </div>
</div>

</main>
<script>
async function run(btn, task) {
  const el = document.getElementById('st-' + task);
  btn.disabled = true; btn.textContent = '...';
  el.className = 'cst spin'; el.textContent = 'Triggering…';
  try {
    const r = await fetch('/api/ondemand/' + task, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({triggered_by:'dashboard'})
    });
    const d = await r.json();
    if (d.status === 'triggered') {
      el.className = 'cst ok';
      el.textContent = 'Triggered ✓ — ' + (d.message || 'check Slack');
    } else if (d.status === 'not_configured') {
      el.className = 'cst err';
      el.textContent = d.message || 'Webhook not configured';
    } else {
      el.className = 'cst err';
      el.textContent = d.message || 'Unknown error';
    }
  } catch(e) {
    el.className = 'cst err';
    el.textContent = 'Network error — is Railway reachable?';
  }
  btn.textContent = 'Run →'; btn.disabled = false;
}
</script>
</body>
</html>"""
