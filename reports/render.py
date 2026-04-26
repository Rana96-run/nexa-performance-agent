"""
reports/render.py
=================
Renders the Nexa daily performance report as a self-contained HTML file.

Design decisions
----------------
- ALL data is embedded as a single JSON blob (window.NEXA_DATA).
  Charts and tables are built by JS, so:
    • Switching date windows (yesterday / 7d / 30d) is instant.
    • Toggling metric columns is instant.
    • No server round-trips for the pre-baked windows.

- For custom date ranges, JS fires fetch("/api/report?start=…&end=…")
  which hits the tiny Flask route in reports/app.py.

- Plotly is loaded from CDN (pinned version). Everything else is vanilla JS
  — no framework dependencies.

- Column visibility is persisted to localStorage under key "nexa_col_prefs".

- Zone colours use CSS custom properties, defined once in :root.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

REPORTS_DIR = Path(__file__).parent
_PLOTLY_CDN = (
    '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" '
    'charset="utf-8"></script>'
)

# ─── Zone colour maps ──────────────────────────────────────────────────────────
_ZONE_CSS = {
    "scale":      "#d1fae5",
    "acceptable": "#fef9c3",
    "warning":    "#fed7aa",
    "pause_zone": "#fecaca",
    "no_data":    "#f1f5f9",
}
_ZONE_BORDER = {
    "scale":      "#10b981",
    "acceptable": "#f59e0b",
    "warning":    "#f97316",
    "pause_zone": "#ef4444",
    "no_data":    "#cbd5e1",
}
_ZONE_LABEL = {
    "scale":      "Scale",
    "acceptable": "OK",
    "warning":    "Watch",
    "pause_zone": "Pause",
    "no_data":    "—",
}

# ─── CSS ──────────────────────────────────────────────────────────────────────
_CSS = """
:root {
  --accent:   #4f46e5;
  --accent-lt:#eef2ff;
  --surface:  #ffffff;
  --bg:       #f8fafc;
  --border:   #e2e8f0;
  --text:     #0f172a;
  --muted:    #64748b;
  --radius:   8px;
  --shadow:   0 1px 3px rgba(0,0,0,.08);
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }

/* ── Layout ── */
.app { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.sidebar {
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  background: var(--surface); border-right: 1px solid var(--border);
  padding: 16px 12px; display: flex; flex-direction: column; gap: 4px;
}
.main { padding: 24px 32px; max-width: 1400px; }
.sidebar-logo { font-weight: 700; font-size: 16px; color: var(--accent);
                padding: 0 8px 16px; border-bottom: 1px solid var(--border);
                margin-bottom: 8px; }
.sidebar-section { font-size: 10px; font-weight: 600; color: var(--muted);
                   text-transform: uppercase; letter-spacing: .06em;
                   padding: 12px 8px 4px; }
.nav-pill {
  display: flex; align-items: center; gap: 8px; padding: 7px 10px;
  border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
  color: var(--muted); text-decoration: none; transition: all .15s;
  border: none; background: transparent; width: 100%; text-align: left;
}
.nav-pill:hover  { background: var(--accent-lt); color: var(--accent); }
.nav-pill.active { background: var(--accent-lt); color: var(--accent); }
.nav-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

/* ── Page header ── */
.page-header { display: flex; align-items: flex-start; justify-content: space-between;
               margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }
.page-title { font-size: 22px; font-weight: 700; }
.page-meta  { font-size: 12px; color: var(--muted); margin-top: 4px; }
.header-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

/* ── Window selector ── */
.window-tabs { display: flex; border: 1px solid var(--border); border-radius: 6px;
               overflow: hidden; }
.window-tab { padding: 6px 14px; font-size: 12px; font-weight: 500; cursor: pointer;
              border: none; background: var(--surface); color: var(--muted);
              transition: all .15s; white-space: nowrap; }
.window-tab.active { background: var(--accent); color: #fff; }

/* ── Date range ── */
.date-range { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.date-range input { padding: 5px 8px; border: 1px solid var(--border);
                    border-radius: 5px; font-size: 12px; }
.date-range button { padding: 5px 12px; background: var(--accent); color: #fff;
                     border: none; border-radius: 5px; cursor: pointer;
                     font-size: 12px; font-weight: 500; }

/* ── Metric toggles ── */
.metric-toggle-btn { padding: 6px 12px; font-size: 12px; font-weight: 500;
                     border: 1px solid var(--border); border-radius: 6px;
                     background: var(--surface); cursor: pointer;
                     display: flex; align-items: center; gap: 6px; }
.metric-dropdown { position: absolute; top: calc(100% + 6px); right: 0; z-index: 200;
                   background: var(--surface); border: 1px solid var(--border);
                   border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.12);
                   padding: 14px 16px; min-width: 230px; display: none;
                   flex-direction: column; gap: 8px; }
.metric-dropdown.open { display: flex; }
.metric-toggle-item { display: flex; align-items: center; gap: 8px;
                      font-size: 13px; cursor: pointer; user-select: none; }
.metric-toggle-item input { cursor: pointer; }

/* ── Hero KPI tiles ── */
.hero-strip { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px,1fr));
              gap: 12px; margin-bottom: 28px; }
.kpi-tile { background: var(--surface); border: 1px solid var(--border);
            border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow); }
.kpi-label { font-size: 11px; font-weight: 600; text-transform: uppercase;
             letter-spacing: .05em; color: var(--muted); }
.kpi-value { font-size: 24px; font-weight: 700; margin: 6px 0 4px; }
.kpi-delta { font-size: 12px; font-weight: 500; }
.kpi-delta.pos { color: #10b981; }
.kpi-delta.neg { color: #ef4444; }
.kpi-delta.neu { color: var(--muted); }
.zone-badge { display: inline-block; padding: 2px 8px; border-radius: 99px;
              font-size: 11px; font-weight: 600; margin-top: 4px; }

/* ── Cards ── */
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--radius); box-shadow: var(--shadow); margin-bottom: 24px;
        overflow: hidden; }
.card-header { padding: 14px 20px; border-bottom: 1px solid var(--border);
               display: flex; align-items: center; justify-content: space-between;
               flex-wrap: wrap; gap: 8px; }
.card-title { font-size: 14px; font-weight: 600; }
.card-body { padding: 20px; }

/* ── Narrative / Summary ── */
.summary-card .card-body { padding: 0; }
.summary-headline { padding: 24px 24px 16px;
                    background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
                    border-bottom: 1px solid var(--border); }
.headline-text { font-size: 22px; font-weight: 700; margin: 0 0 4px;
                 line-height: 1.35; color: #0f172a; letter-spacing: -0.01em; }
.headline-meta { font-size: 12px; color: var(--muted); font-weight: 500; }
.summary-body { padding: 20px 24px; display: grid;
                grid-template-columns: 1fr 1fr; gap: 24px; }
.summary-block h4 { font-size: 11px; font-weight: 700; color: var(--muted);
                    text-transform: uppercase; letter-spacing: .08em;
                    margin: 0 0 10px; }
.what-changed { list-style: none; display: flex; flex-direction: column; gap: 8px;
                margin: 0; padding: 0; }
.what-changed li { font-size: 13.5px; line-height: 1.55;
                   padding-left: 22px; position: relative; }
.what-changed li::before { content: "▸"; position: absolute; left: 0;
                           color: var(--accent); font-weight: 700; }
.why-text { color: #334155; line-height: 1.7; font-size: 13.5px;
            white-space: pre-wrap; margin: 0; }
@media (max-width: 900px) {
  .summary-body { grid-template-columns: 1fr; }
}

/* ── Channel section ── */
.channel-section { scroll-margin-top: 20px; }
.channel-header { display: flex; align-items: center; gap: 10px; }
.channel-dot { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }
.channel-kpis { display: grid;
                grid-template-columns: repeat(auto-fill, minmax(120px,1fr));
                gap: 10px; margin-bottom: 20px; }
.ck-tile { border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
.ck-label { font-size: 10px; font-weight: 600; text-transform: uppercase;
            letter-spacing: .05em; color: var(--muted); }
.ck-value { font-size: 18px; font-weight: 700; margin-top: 4px; }

/* ── Sub-tabs ── */
.sub-tabs { display: flex; gap: 0; border-bottom: 2px solid var(--border);
            margin-bottom: 16px; overflow-x: auto; flex-wrap: nowrap; }
.sub-tab { padding: 8px 16px; font-size: 12px; font-weight: 500; cursor: pointer;
           border: none; background: transparent; color: var(--muted);
           border-bottom: 2px solid transparent; margin-bottom: -2px;
           white-space: nowrap; flex-shrink: 0; }
.sub-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.sub-panel { display: none; }
.sub-panel.active { display: block; }

/* ── Data tables ── */
.data-table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 8px 12px; background: #f8fafc; border-bottom: 2px solid var(--border);
     font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
     color: var(--muted); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; text-align: right; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f8fafc; }
.zone-cell { border-radius: 4px; padding: 3px 8px; display: inline-block; font-weight: 600; }

/* ── Disq reasons ── */
.disq-bar { height: 6px; background: #fecaca; border-radius: 3px; margin-top: 3px; width: 100%; }
.disq-bar-inner { height: 100%; background: #ef4444; border-radius: 3px; }

/* ── Pending badge ── */
.pending-badge { display: inline-flex; align-items: center; gap: 6px; padding: 10px 14px;
                 border: 1px dashed var(--border); border-radius: 6px;
                 color: var(--muted); font-size: 12px; background: #f8fafc; }

/* ── Chart containers ── */
.chart-wrap { border-radius: var(--radius); overflow: hidden; min-height: 240px; }
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }

/* ── Loading overlay ── */
#custom-loading { display: none; position: fixed; inset: 0;
                  background: rgba(255,255,255,.75); backdrop-filter: blur(2px);
                  z-index: 999; align-items: center; justify-content: center; }
#custom-loading.on { display: flex; }
.spinner { width: 36px; height: 36px; border: 3px solid var(--border);
           border-top-color: var(--accent); border-radius: 50%;
           animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Responsive ── */
@media (max-width: 900px) {
  .app { grid-template-columns: 1fr; }
  .sidebar { display: none; }
  .chart-row { grid-template-columns: 1fr; }
}
@media print {
  .sidebar, .header-controls, #custom-loading { display: none !important; }
  .app { display: block; }
  .card { break-inside: avoid; }
}
"""

# ─── JS ───────────────────────────────────────────────────────────────────────
_JS = r"""
// ── State ──────────────────────────────────────────────────────────────────
let currentWindow = 'last_7d';
const D = window.NEXA_DATA;

const ALL_METRICS = [
  {key:'cost',         label:'Cost (USD)',         default:true},
  {key:'leads',        label:'Leads',              default:true},
  {key:'qualified',    label:'Qualified Leads',    default:true},
  {key:'disqualified', label:'Disqualified Leads', default:false},
  {key:'cpl',          label:'CPL',                default:true},
  {key:'cpql',         label:'CPQL',               default:true},
  {key:'deals',        label:'Deals',              default:true},
  {key:'deal_amount',  label:'Deal Amount (USD)',   default:false},
  {key:'roas',         label:'ROAS',               default:true},
];

let enabledMetrics = loadMetricPrefs();

function loadMetricPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem('nexa_col_prefs') || '{}');
    const out = {};
    ALL_METRICS.forEach(m => { out[m.key] = m.key in saved ? saved[m.key] : m.default; });
    return out;
  } catch { return Object.fromEntries(ALL_METRICS.map(m => [m.key, m.default])); }
}
function saveMetricPrefs() {
  localStorage.setItem('nexa_col_prefs', JSON.stringify(enabledMetrics));
}

// ── Formatters ─────────────────────────────────────────────────────────────
const fmtUSD = v => {
  if (v == null) return '—';
  if (Math.abs(v) >= 1e6) return '$' + (v/1e6).toFixed(2) + 'M';
  if (Math.abs(v) >= 1e3) return '$' + (v/1e3).toFixed(1) + 'K';
  return '$' + parseFloat(v).toFixed(2);
};
const fmtNum  = v => v == null ? '—' : Number(v).toLocaleString();
const fmtPct  = v => v == null ? '—' : (v * 100).toFixed(1) + '%';
const fmtX    = v => v == null ? '—' : parseFloat(v).toFixed(2) + 'x';
const truncate = (s, n) => !s ? '—' : s.length > n ? s.slice(0, n) + '…' : s;

const ZONE_CSS = {
  scale:     'background:#d1fae5;color:#065f46;border:1px solid #10b981',
  acceptable:'background:#fef9c3;color:#78350f;border:1px solid #f59e0b',
  warning:   'background:#fed7aa;color:#7c2d12;border:1px solid #f97316',
  pause_zone:'background:#fecaca;color:#7f1d1d;border:1px solid #ef4444',
  no_data:   'background:#f1f5f9;color:#64748b;border:1px solid #cbd5e1',
};
const ZONE_LABEL = {scale:'Scale',acceptable:'OK',warning:'Watch',pause_zone:'Pause',no_data:'—'};

function zoneCell(val, zone, fmt) {
  const z   = zone || 'no_data';
  const css = ZONE_CSS[z] || ZONE_CSS.no_data;
  const lbl = fmt ? fmt(val) : (val == null ? '—' : val);
  return `<span class="zone-cell" style="${css}">${lbl}</span>`;
}

// ── Table builder ──────────────────────────────────────────────────────────
/*
  Column def: {
    key,                // data field name  (or 'label' for UTM tables)
    label,              // th text
    always?: bool,      // never hidden by metric toggle
    fmt?: fn,           // value formatter
    zone_key?: str,     // if set, render as zone-colored cell
    zone_fmt?: fn,      // formatter used inside the zone cell
    left?: bool,        // left-align
    title_key?: str,    // data field to use as tooltip (for long text)
  }
*/
function buildTable(rows, columns, emptyMsg) {
  if (!rows || !rows.length) {
    return `<p style="color:var(--muted);padding:12px 0">${emptyMsg || 'No data.'}</p>`;
  }
  const vis = columns.filter(c => c.always || enabledMetrics[c.key] !== false);
  let h = '<div class="data-table-wrap"><table><thead><tr>';
  vis.forEach(c => { h += `<th style="${c.left||c.always?'text-align:left':''}">${c.label}</th>`; });
  h += '</tr></thead><tbody>';
  rows.forEach(row => {
    h += '<tr>';
    vis.forEach(c => {
      const val = row[c.key];
      let cell;
      if (c.zone_key) {
        cell = zoneCell(val, row[c.zone_key], c.zone_fmt || fmtUSD);
      } else if (c.fmt) {
        cell = c.fmt(val);
      } else {
        cell = val == null ? '—' : String(val);
      }
      const tip = c.title_key ? ` title="${(row[c.title_key]||'').replace(/"/g,'')}"` : '';
      const align = (c.left || c.always) ? 'text-align:left' : '';
      h += `<td style="${align}"${tip}>${cell}</td>`;
    });
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  return h;
}

// ── Column defs ────────────────────────────────────────────────────────────
const CAMP_COLS = [
  {key:'campaign',     label:'Campaign',    always:true, left:true,
   fmt: v => `<span title="${(v||'').replace(/"/g,'')}">${truncate(v,55)}</span>`},
  {key:'cost',         label:'Cost',        zone_key:'cpl_zone',  zone_fmt:fmtUSD},
  {key:'leads',        label:'Leads',       fmt:fmtNum},
  {key:'qualified',    label:'Qualified',   fmt:fmtNum},
  {key:'disqualified', label:'Disqual.',    fmt:fmtNum},
  {key:'cpl',          label:'CPL',         zone_key:'cpl_zone',  zone_fmt:fmtUSD},
  {key:'cpql',         label:'CPQL',        zone_key:'cpql_zone', zone_fmt:fmtUSD},
  {key:'deals',        label:'Deals',       fmt:fmtNum},
  {key:'deal_amount',  label:'Deal Amt',    fmt:fmtUSD},
  {key:'roas',         label:'ROAS',        fmt:fmtX},
];

function utmCols(dimLabel) {
  return [
    {key:'label',       label:dimLabel,      always:true, left:true,
     fmt: v => `<span title="${(v||'').replace(/"/g,'')}">${truncate(v,50)}</span>`},
    {key:'cost',        label:'Cost',        fmt:fmtUSD},
    {key:'leads',       label:'Leads',       fmt:fmtNum},
    {key:'qualified',   label:'Qualified',   fmt:fmtNum},
    {key:'disqualified',label:'Disqual.',    fmt:fmtNum},
    {key:'cpl',         label:'CPL',         zone_key:'cpl_zone',  zone_fmt:fmtUSD},
    {key:'cpql',        label:'CPQL',        zone_key:'cpql_zone', zone_fmt:fmtUSD},
    {key:'deals',       label:'Deals',       fmt:fmtNum},
    {key:'deal_amount', label:'Deal Amt',    fmt:fmtUSD},
    {key:'roas',        label:'ROAS',        fmt:fmtX},
  ];
}

// ── Channel KPI strip ──────────────────────────────────────────────────────
function channelKpiHtml(kpis) {
  if (!kpis) return '';
  const items = [
    {label:'Cost',         val:fmtUSD(kpis.spend),        zone:null},
    {label:'Leads',        val:fmtNum(kpis.leads),        zone:null},
    {label:'Qualified',    val:fmtNum(kpis.qualified),    zone:null},
    {label:'Disqualified', val:fmtNum(kpis.disqualified), zone:null},
    {label:'CPL',          val:fmtUSD(kpis.cpl),          zone:kpis.cpl_zone},
    {label:'CPQL',         val:fmtUSD(kpis.cpql),         zone:kpis.cpql_zone},
    {label:'Deals',        val:fmtNum(kpis.deals),        zone:null},
    {label:'Deal Amt',     val:fmtUSD(kpis.deal_amount),  zone:null},
    {label:'ROAS',         val:fmtX(kpis.roas),           zone:null},
  ];
  let h = '<div class="channel-kpis">';
  items.forEach(({label, val, zone}) => {
    let zHtml = '';
    if (zone) {
      const css = ZONE_CSS[zone] || ZONE_CSS.no_data;
      const lbl = ZONE_LABEL[zone] || '—';
      zHtml = `<br><span class="zone-badge" style="${css}">${lbl}</span>`;
    }
    h += `<div class="ck-tile"><div class="ck-label">${label}</div><div class="ck-value">${val}</div>${zHtml}</div>`;
  });
  h += '</div>';
  return h;
}

// ── Disq reasons table ─────────────────────────────────────────────────────
function disqTable(reasons) {
  if (!reasons || !reasons.length) {
    return '<p style="color:var(--muted);padding:12px 0">No disqualification data for this window.</p>';
  }
  let h = '<div class="data-table-wrap"><table><thead><tr>'
        + '<th style="text-align:left">Reason</th><th>Count</th><th>Share</th><th>Bar</th>'
        + '</tr></thead><tbody>';
  reasons.forEach(r => {
    const pct = ((r.share || 0) * 100).toFixed(1);
    const w   = Math.min(100, (r.share || 0) * 100).toFixed(0);
    h += `<tr>
      <td style="text-align:left">${r.reason}</td>
      <td>${r.count}</td>
      <td>${pct}%</td>
      <td style="min-width:100px"><div class="disq-bar"><div class="disq-bar-inner" style="width:${w}%"></div></div></td>
    </tr>`;
  });
  h += '</tbody></table></div>';
  return h;
}

// ── Sub-tab wiring ─────────────────────────────────────────────────────────
function initSubTabs(sectionEl) {
  sectionEl.querySelectorAll('.sub-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const panel = tab.dataset.panel;
      sectionEl.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
      sectionEl.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const el = sectionEl.querySelector(`.sub-panel[data-panel="${panel}"]`);
      if (el) el.classList.add('active');
    });
  });
}

// ── Render one channel section ─────────────────────────────────────────────
// Panels use data-panel attributes (campaign / utm-campaign / utm-audience /
// utm-content / disq / adgroups / ads) — match the scaffold in render.py.
function setPanel(el, panelKey, html) {
  const p = el.querySelector(`.sub-panel[data-panel="${panelKey}"]`);
  if (p) p.innerHTML = html;
}

function renderChannel(ch) {
  const el = document.getElementById('ch-' + ch.channel);
  if (!el) return;

  const narrative = el.querySelector('.ch-narrative');
  if (narrative) narrative.textContent = ch.narrative || '';
  const kpiStrip = el.querySelector('.ch-kpi-strip');
  if (kpiStrip) kpiStrip.innerHTML = channelKpiHtml(ch.kpis);

  setPanel(el, 'campaign',     buildTable(ch.campaigns,    CAMP_COLS, 'No campaign data for this period.'));
  setPanel(el, 'utm-campaign', buildTable(ch.utm_campaign, utmCols('UTM Campaign'),  'No UTM campaign data.'));
  setPanel(el, 'utm-audience', buildTable(ch.utm_audience, utmCols('UTM Audience'),  'No UTM audience data.'));
  setPanel(el, 'utm-content',  buildTable(ch.utm_content,  utmCols('UTM Content'),   'No UTM content data.'));
  setPanel(el, 'disq',         disqTable(ch.disq_reasons));

  const agNote = ((ch.ad_groups || {}).note) || 'Ad-group grain — collector pending';
  const adNote = ((ch.ads       || {}).note) || 'Ad-creative grain — collector pending';
  setPanel(el, 'adgroups', `<span class="pending-badge">⏳ ${agNote}</span>`);
  setPanel(el, 'ads',      `<span class="pending-badge">⏳ ${adNote}</span>`);
}

function renderAllChannels() {
  const chs = ((D.windows || {})[currentWindow]) || D.channels || [];
  chs.forEach(renderChannel);
}

// ── Plotly charts ──────────────────────────────────────────────────────────
function renderTrends() {
  const trends = D.trends_30d || [];
  if (!trends.length || !window.Plotly) return;

  const CH_COLORS = {
    google_ads:'#4285F4', meta:'#1877F2', snapchat:'#FFFC00',
    tiktok:'#69C9D0',    linkedin:'#0A66C2', microsoft_ads:'#00A4EF',
  };
  const CH_LABEL = {
    google_ads:'Google Ads', meta:'Meta', snapchat:'Snapchat',
    tiktok:'TikTok', linkedin:'LinkedIn', microsoft_ads:'Microsoft',
  };
  const cfg = {responsive:true, displayModeBar:false};

  // Group by channel
  const byChannel = {};
  trends.forEach(r => {
    if (!byChannel[r.channel]) byChannel[r.channel] = {dates:[],spend:[],leads:[],cpl:[]};
    byChannel[r.channel].dates.push(r.date);
    byChannel[r.channel].spend.push(r.spend);
    byChannel[r.channel].leads.push(r.leads);
    byChannel[r.channel].cpl.push(r.cpl);
  });

  // Stacked area — spend
  const spendTraces = Object.entries(byChannel).map(([ch, d]) => ({
    x: d.dates, y: d.spend, name: CH_LABEL[ch]||ch,
    type:'scatter', mode:'lines', stackgroup:'one',
    fillcolor: (CH_COLORS[ch]||'#888') + '55',
    line: {color: CH_COLORS[ch]||'#888', width:2},
  }));
  Plotly.newPlot('chart-spend', spendTraces, {
    margin:{t:10,r:10,b:40,l:60}, height:240, showlegend:true,
    paper_bgcolor:'transparent', plot_bgcolor:'transparent',
    font:{family:'-apple-system,sans-serif',size:11},
    legend:{orientation:'h', y:-0.25},
    xaxis:{showgrid:false, rangeslider:{visible:true, thickness:0.06}},
    yaxis:{showgrid:true, gridcolor:'#e2e8f0', tickprefix:'$'},
  }, cfg);

  // Leads bar + avg CPL line
  const allDates = [...new Set(trends.map(r=>r.date))].sort();
  const totalLeads = allDates.map(d => trends.filter(r=>r.date===d).reduce((s,r)=>s+(r.leads||0),0));
  const avgCpl     = allDates.map(d => {
    const rs = trends.filter(r=>r.date===d && r.cpl!=null);
    return rs.length ? rs.reduce((s,r)=>s+r.cpl,0)/rs.length : null;
  });
  Plotly.newPlot('chart-leads', [
    {x:allDates, y:totalLeads, name:'Leads', type:'bar', marker:{color:'#a5b4fc'}},
    {x:allDates, y:avgCpl, name:'Avg CPL', type:'scatter', mode:'lines+markers',
     yaxis:'y2', line:{color:'#f97316',width:2}, marker:{size:4}},
  ], {
    margin:{t:10,r:60,b:40,l:60}, height:240,
    paper_bgcolor:'transparent', plot_bgcolor:'transparent',
    font:{family:'-apple-system,sans-serif',size:11},
    legend:{orientation:'h', y:-0.25},
    xaxis:{showgrid:false},
    yaxis:{showgrid:true, gridcolor:'#e2e8f0'},
    yaxis2:{overlaying:'y', side:'right', tickprefix:'$', showgrid:false},
    barmode:'stack',
  }, cfg);
}

// ── Window switcher ────────────────────────────────────────────────────────
function setWindow(w) {
  currentWindow = w;
  document.querySelectorAll('.window-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.w === w);
  });
  renderAllChannels();
}

// ── Custom date range (Flask-backed) ──────────────────────────────────────
async function fetchCustomRange() {
  const start = document.getElementById('date-start').value;
  const end   = document.getElementById('date-end').value;
  if (!start || !end) { alert('Pick start and end dates.'); return; }
  const loading = document.getElementById('custom-loading');
  loading.classList.add('on');
  try {
    const resp = await fetch(`/api/report?start=${start}&end=${end}`);
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    D.windows = D.windows || {};
    D.windows['custom'] = data.channels || [];
    // Add or update custom tab
    const tabs = document.querySelector('.window-tabs');
    let btn = tabs.querySelector('[data-w="custom"]');
    if (!btn) {
      btn = document.createElement('button');
      btn.className = 'window-tab';
      btn.dataset.w = 'custom';
      btn.onclick = () => setWindow('custom');
      tabs.appendChild(btn);
    }
    btn.textContent = `${start} → ${end}`;
    setWindow('custom');
  } catch(e) {
    alert('Failed: ' + e.message);
  } finally {
    loading.classList.remove('on');
  }
}

// ── Metric dropdown ────────────────────────────────────────────────────────
function buildMetricToggles() {
  const container = document.getElementById('metric-toggle-list');
  if (!container) return;
  ALL_METRICS.forEach(m => {
    const label = document.createElement('label');
    label.className = 'metric-toggle-item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!enabledMetrics[m.key];
    cb.addEventListener('change', () => {
      enabledMetrics[m.key] = cb.checked;
      saveMetricPrefs();
      renderAllChannels();
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(' ' + m.label));
    container.appendChild(label);
  });
}

function toggleMetricDropdown() {
  document.getElementById('metric-dropdown').classList.toggle('open');
}
document.addEventListener('click', e => {
  const btn = document.getElementById('metric-toggle-btn');
  const dd  = document.getElementById('metric-dropdown');
  if (btn && dd && !btn.contains(e.target) && !dd.contains(e.target)) {
    dd.classList.remove('open');
  }
});

// ── Scroll-spy sidebar ────────────────────────────────────────────────────
function initScrollSpy() {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        const id = e.target.id;
        document.querySelectorAll('.nav-pill[data-target]').forEach(p => {
          p.classList.toggle('active', p.dataset.target === id);
        });
      }
    });
  }, {threshold: 0.25});
  document.querySelectorAll('.channel-section[id]').forEach(s => observer.observe(s));
}

// ── Default date inputs to last 7 days ────────────────────────────────────
function initDateInputs() {
  const e = document.getElementById('date-end');
  const s = document.getElementById('date-start');
  if (!e || !s) return;
  const today = new Date();
  const yest  = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);
  const fmt = d => d.toISOString().slice(0, 10);
  if (!e.value) e.value = fmt(yest);
  if (!s.value) s.value = fmt(weekAgo);
}

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  buildMetricToggles();
  initDateInputs();
  renderAllChannels();
  renderTrends();
  initScrollSpy();

  document.querySelectorAll('.channel-section').forEach(el => initSubTabs(el));
  document.querySelectorAll('.window-tab').forEach(t => {
    t.addEventListener('click', () => setWindow(t.dataset.w));
  });
  document.getElementById('fetch-custom')?.addEventListener('click', fetchCustomRange);
  document.getElementById('metric-toggle-btn')?.addEventListener('click', toggleMetricDropdown);
  document.querySelectorAll('.nav-pill[data-target]').forEach(p => {
    p.addEventListener('click', () => {
      document.getElementById(p.dataset.target)?.scrollIntoView({behavior:'smooth'});
    });
  });
});
"""


# ─── Utility ──────────────────────────────────────────────────────────────────

def _j(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _fmt_usd(v: float | int | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.2f}"


def _delta_html(d: float | None, lower_is_better: bool = False) -> str:
    if d is None:
        return '<span class="kpi-delta neu">—</span>'
    sign = "+" if d > 0 else ""
    good = (d < 0) if lower_is_better else (d > 0)
    cls  = "pos" if good else ("neg" if d != 0 else "neu")
    arrow = "↑" if d > 0 else ("↓" if d < 0 else "→")
    return f'<span class="kpi-delta {cls}">{arrow} {sign}{d:.1f}%</span>'


def _zone_badge(zone: str | None) -> str:
    z  = zone or "no_data"
    bg = _ZONE_CSS.get(z, _ZONE_CSS["no_data"])
    bd = _ZONE_BORDER.get(z, _ZONE_BORDER["no_data"])
    lb = _ZONE_LABEL.get(z, "—")
    return (f'<span class="zone-badge" style="background:{bg};'
            f'border:1px solid {bd};color:{bd}">{lb}</span>')


# ─── Hero strip (server-side, doesn't change with window) ────────────────────

def _hero_strip_html(hero: dict) -> str:
    if not hero:
        return '<p style="color:var(--muted)">Hero KPIs unavailable.</p>'

    def tile(label, key, fmt, lower_is_better=False, show_zone=False):
        val  = hero.get(key, {})
        v    = val.get("value")
        d    = val.get("delta_pct")
        zone = val.get("zone")
        v_html = fmt(v) if v is not None else "—"
        z_html = (_zone_badge(zone) + "<br>") if (show_zone and zone) else ""
        return (
            f'<div class="kpi-tile">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{v_html}</div>'
            f'{z_html}'
            f'{_delta_html(d, lower_is_better)}'
            f'</div>'
        )

    return '<div class="hero-strip">' + "".join([
        tile("Spend",     "spend",     _fmt_usd),
        tile("Leads",     "leads",     lambda v: f"{v:,}"),
        tile("SQLs",      "sql",       lambda v: f"{v:,}"),
        tile("CPL",       "cpl",       _fmt_usd,  lower_is_better=True, show_zone=True),
        tile("CPQL",      "cpql",      _fmt_usd,  lower_is_better=True, show_zone=True),
        tile("Qual Rate", "qual_rate", lambda v: f"{v*100:.1f}%" if v else "—"),
    ]) + "</div>"


# ─── Channel section scaffold (static HTML, JS fills tables) ─────────────────

def _channel_section_scaffold(ch: dict) -> str:
    key   = ch["channel"]
    label = ch.get("label", key)
    color = ch.get("color", "#888")

    tabs = [
        ("campaign",     "Campaigns"),
        ("utm-campaign", "UTM Campaign"),
        ("utm-audience", "UTM Audience"),
        ("utm-content",  "UTM Content"),
        ("disq",         "Disqual. Reasons"),
        ("adgroups",     "Ad Groups ⏳"),
        ("ads",          "Ads ⏳"),
    ]
    tabs_html = "".join(
        f'<button class="sub-tab{" active" if i == 0 else ""}" data-panel="{k}">{lbl}</button>'
        for i, (k, lbl) in enumerate(tabs)
    )
    panels_html = "".join(
        f'<div class="sub-panel{" active" if i == 0 else ""}" data-panel="{k}">'
        f'<p style="color:var(--muted)">Loading…</p></div>'
        for i, (k, _) in enumerate(tabs)
    )

    return f"""
<section id="ch-{key}" class="channel-section">
  <div class="card">
    <div class="card-header">
      <div class="channel-header">
        <span class="channel-dot" style="background:{color}"></span>
        <span class="card-title">{label}</span>
      </div>
    </div>
    <div class="card-body">
      <p class="ch-narrative" style="color:var(--muted);margin-bottom:16px;line-height:1.7"></p>
      <div class="ch-kpi-strip"></div>
      <div class="sub-tabs">{tabs_html}</div>
      {panels_html}
    </div>
  </div>
</section>"""


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def _sidebar(channels: list[dict]) -> str:
    links = "".join(
        f'<button class="nav-pill" data-target="ch-{ch["channel"]}">'
        f'<span class="nav-dot" style="background:{ch.get("color","#888")}"></span>'
        f'{ch.get("label", ch["channel"])}</button>\n'
        for ch in channels
    )
    return f"""
<nav class="sidebar">
  <div class="sidebar-logo">Nexa</div>
  <div class="sidebar-section">Overview</div>
  <button class="nav-pill" data-target="section-hero">Hero KPIs</button>
  <button class="nav-pill" data-target="section-trends">Trends</button>
  <button class="nav-pill" data-target="section-narrative">Summary</button>
  <div class="sidebar-section">Channels</div>
  {links}
</nav>"""


# ─── Main entry ───────────────────────────────────────────────────────────────

def render_html(report: dict) -> str:
    """Render the full interactive HTML from the assembled report dict."""
    headline     = report.get("headline", "")
    what_changed = report.get("what_changed", [])
    why          = report.get("why", "")
    hero         = report.get("hero", {})
    report_date  = report.get("report_date", "")
    generated_at = report.get("generated_at", "")
    cadence      = report.get("cadence", "daily")
    channels_7d  = (report.get("windows") or {}).get("last_7d") or report.get("channels", [])

    # Friendly date for the summary block, e.g. "Sun, 26 Apr 2026"
    try:
        from datetime import datetime as _dt
        report_date_human = _dt.fromisoformat(report_date).strftime("%a, %d %b %Y")
    except Exception:
        report_date_human = report_date

    # Default values if AI roles haven't run (e.g. on_demand regen via /api/regenerate)
    if not headline:
        active = [c.get("label") or c.get("channel", "") for c in channels_7d]
        headline = (
            f"{len(channels_7d)} active channel(s): " + ", ".join(active)
        ) if channels_7d else "Awaiting first nightly analysis."
    if not what_changed:
        what_changed = ["Nightly Claude analysis runs at 03:00 Riyadh — full insights tomorrow."]
    if not why:
        why = "This dashboard refreshes once nightly. Live BigQuery data feeds the per-channel campaign tables."

    sidebar_html   = _sidebar(channels_7d)
    ch_scaffolds   = "\n".join(_channel_section_scaffold(ch) for ch in channels_7d)
    bullets_html   = "".join(f"<li>{b}</li>" for b in what_changed)
    hero_html      = _hero_strip_html(hero)
    data_json      = _j(report)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nexa Report — {report_date}</title>
{_PLOTLY_CDN}
<style>{_CSS}</style>
</head>
<body>

<div id="custom-loading"><div class="spinner"></div></div>

<div class="app">
  {sidebar_html}

  <main class="main">

    <!-- Page header -->
    <div class="page-header">
      <div>
        <div class="page-title">Performance Report</div>
        <div class="page-meta">{report_date} &middot; {cadence.title()} &middot; Generated {generated_at}</div>
      </div>
      <div class="header-controls">

        <div class="window-tabs">
          <button class="window-tab" data-w="yesterday">Yesterday</button>
          <button class="window-tab active" data-w="last_7d">7 Days</button>
          <button class="window-tab" data-w="last_30d">30 Days</button>
        </div>

        <div class="date-range">
          <input type="date" id="date-start" title="Start date">
          <span style="color:var(--muted)">→</span>
          <input type="date" id="date-end" title="End date">
          <button id="fetch-custom">Apply</button>
        </div>

        <div style="position:relative">
          <button class="metric-toggle-btn" id="metric-toggle-btn">
            ⚙ Metrics
          </button>
          <div class="metric-dropdown" id="metric-dropdown">
            <strong style="font-size:12px;display:block;margin-bottom:6px">Show / hide columns</strong>
            <div id="metric-toggle-list"></div>
          </div>
        </div>

      </div>
    </div>

    <!-- Hero KPIs (server-rendered, always yesterday) -->
    <section id="section-hero">
      {hero_html}
    </section>

    <!-- Trends charts -->
    <section id="section-trends">
      <div class="chart-row">
        <div class="card">
          <div class="card-header"><span class="card-title">Spend by Channel — 30d</span></div>
          <div class="card-body"><div class="chart-wrap" id="chart-spend"></div></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Leads &amp; Avg CPL — 30d</span></div>
          <div class="card-body"><div class="chart-wrap" id="chart-leads"></div></div>
        </div>
      </div>
    </section>

    <!-- Narrative summary -->
    <section id="section-narrative">
      <div class="card summary-card">
        <div class="card-header"><span class="card-title">Daily Summary</span></div>
        <div class="card-body">
          <div class="summary-headline">
            <div class="headline-text">{headline}</div>
            <div class="headline-meta">{report_date_human}</div>
          </div>
          <div class="summary-body">
            <div class="summary-block">
              <h4>What changed</h4>
              <ul class="what-changed">{bullets_html}</ul>
            </div>
            <div class="summary-block">
              <h4>Why it matters</h4>
              <p class="why-text">{why}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Per-channel sections -->
    {ch_scaffolds}

  </main>
</div>

<script>window.NEXA_DATA = {data_json};</script>
<script>{_JS}</script>
</body>
</html>"""


def save_report(report: dict, report_date: date | None = None) -> Path:
    """Render and write reports/<date>.html + reports/latest.html.
    Also uploads to Google Drive so the report survives Railway restarts.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    d    = report_date or date.fromisoformat(report.get("report_date") or str(date.today()))
    html = render_html(report)
    dated  = REPORTS_DIR / f"{d}.html"
    latest = REPORTS_DIR / "latest.html"
    dated.write_text(html, encoding="utf-8")
    latest.write_text(html, encoding="utf-8")
    print(f"[render] Report saved locally -> {dated}")

    # Upload to Google Drive for persistence across Railway container restarts.
    try:
        from collectors.drive_writer import save_report_to_drive
        drive_id = save_report_to_drive(dated)
        if drive_id:
            print(f"[render] Report uploaded to Drive (id={drive_id})")
        else:
            print("[render] Drive upload skipped (Drive not configured or unavailable)")
    except Exception as e:
        print(f"[render] Drive upload failed (non-fatal): {e}")

    return dated
