/**
 * BI Tool Comparison — Google Slides (via PPTX)
 * Source: Google Sheet 1Rq6tsAvD-2mlA0cJOiF46EB0fkX5HkeEGFXZr4drHuI
 * Slide 1: DATA & CONNECTORS + VISUALIZATION
 * Slide 2: ANALYSIS & SQL + OPS & AUTOMATION + SHARING & ACCESS + PRICING + DECISION
 * Upload to Google Drive → Open with Google Slides.
 */
const pptxgen = require("pptxgenjs");
const path    = require("path");

// ── Colors (no # prefix) ─────────────────────────────────────────────────────
const C = {
  NAVY:     "1E3A5F",
  DARK_NAV: "162D4A",
  DEEP_NAV: "0F1E30",
  CAT_BG:   "EEF2FF",
  CAT_TX:   "1E3A5F",
  GREEN_BG: "D1FAE5",
  GREEN_TX: "065F46",
  RED_BG:   "FEE2E2",
  RED_TX:   "991B1B",
  AMBER_BG: "FEF3C7",
  AMBER_TX: "92400E",
  WHITE:    "FFFFFF",
  ROW_ALT:  "F8FAFC",
  BORDER:   "CBD5E1",
  TXT:      "1E293B",
  BLUE_LT:  "93C5FD",
};

// ── Source data from spreadsheet ──────────────────────────────────────────────
// [category, feature, databox, hex, funnel, db_note, hx_note, fn_note]
const ALL_ROWS = [
  ["DATA & CONNECTORS","","","","","","",""],
  ["","Native ad platform connectors (Meta / Google / Snap / TikTok / LinkedIn / Microsoft)","✓","✗","✓","Direct integration — all major platforms built in","Needs our own collectors per platform","325+ connectors maintained by Funnel"],
  ["","HubSpot Contact connector","✓","✓","✓","Direct integration","Via our collector → BQ",""],
  ["","HubSpot Deals connector","✓","✓","✓","Direct integration","hubspot_deals_daily",""],
  ["","HubSpot Lead Module (object 0-136)","⚠ verify","✓","⚠ verify","Likely via HubSpot connector — scope TBC","hubspot_leads_module_daily — confirmed","User confirms Funnel sees it — exact field mapping needs audit"],
  ["","BigQuery as data source — SQL support","✓","✓","✓","BQ connected; SQL queries written directly in Databox","Primary connection — full SQL","Funnel exports to BQ; Data Studio reads it"],
  ["","Zero connector maintenance effort","✓","✗","✓","Databox owns all API updates and auth refreshes","We absorb every API deprecation (LinkedIn / TikTok / Meta all bit us)","Funnel maintains all 325+ connectors"],
  ["","Cross-channel blended CPL / CPQL","⚠ partial","✓","✓","Requires manual formula builder; limited join depth","channel_roas_daily view — our SQL our rules","Custom metrics in Funnel (best in class)"],
  ["","Data refresh frequency","15 min – 24 h","On-demand + 6 h","6 h (Funnel confirmed)","Depends on plan + connector","Railway nightly collector cycle","Data Studio shows last Funnel export — not real-time"],
  ["","Historical backfill","⚠ partial","✓","✓","Some connectors limited to 90 d history","We control the backfill range per collector","Full historical pull per platform"],
  ["","Custom dimension definitions via API / code","✗","✓","✗","UI-only metric builder","Defined in SQL / views.py — git-tracked","UI-only; no read API for custom dim rules"],
  ["","USD normalization across all channels","⚠ partial","✓","⚠ partial","Ad channels already USD; HubSpot SAR convertible inside Databox","campaigns_daily.spend always USD; _native cols for SAR","Funnel workspace currency (SAR) caused historical divide-by-3.75 confusion"],
  ["","UTC → Asia/Riyadh timezone handling","⚠ partial","✓","⚠ partial","Connector-defined not always configurable","Controlled in SQL per query","Funnel workspace TZ configurable — confirm Asia/Riyadh is set"],

  ["VISUALIZATION","","","","","","",""],
  ["","Drag-and-drop dashboard builder","✓","✗","✓","","Code-first; no drag-drop","Data Studio canvas"],
  ["","Chart types (line / bar / donut / table / funnel)","✓","✓","✓","~20 chart types","Plotly + custom HTML — unlimited","Data Studio standard chart set"],
  ["","Mobile-friendly view / native app","✓","✗","⚠ partial","Native iOS + Android app","Desktop only","Data Studio renders on mobile but not optimized"],
  ["","Real-time auto-refresh while viewing","✓","⚠ partial","✗","Configurable per plan","1 h cache; manual force-refresh button","6 h Funnel cycle; Data Studio shows last export only"],
  ["","Branded dashboard (logo / custom colors)","✓","✓","⚠ partial","","Qoyod navy #003DA5 theme configured","Data Studio has limited theming options"],
  ["","Period-over-period delta tiles","✓","✓","✓","Built-in comparison widget","period_compare.py feeds Hex cells","Data Studio date comparison built-in"],

  ["ANALYSIS & SQL","","","","","","",""],
  ["","Raw SQL query support","✓","✓","⚠ partial","SQL written against BQ tables directly in Databox","Full BigQuery SQL in every cell","Data Studio calculated fields only; SQL only if BQ is the source"],
  ["","Python / Pandas cells","✗","✓","✗","","Python cells in same notebook as SQL",""],
  ["","Formula / calculated metrics","✓","✓","⚠ partial","Formula builder — basic arithmetic","Unlimited — full SQL + Python expressions","Funnel formula metrics can't nest; can't reference another formula metric"],
  ["","Ad-level / adset-level drill-down","✓","✓","✓","Direct from ad platform connectors","v_ad_performance / v_adset_performance views","Funnel has campaign/adset/ad grain per platform"],
  ["","Disqualification reason breakdown","✗","✓","✗","Not a standard ad platform metric","Lead Module disq reasons in BQ → Hex",""],
  ["","CPQL from Lead Module (true qualified count)","⚠ verify","✓","⚠ verify","Depends on HubSpot connector scope — needs audit","hubspot_leads_module_daily.leads_qualified — confirmed","User confirms Funnel sees Lead Module — exact field mapping TBC"],
  ["","Version control on metric definitions","✗","✓","✗","No history of metric or dashboard changes","SQL in GitHub (views.py / bq_writer.py) + Hex notebook versions","Funnel UI changes are silent; no history"],

  ["OPS & AUTOMATION","","","","","","",""],
  ["","Metric-based alerts (email / Slack)","✓","⚠ partial","✓","Best in class — core Databox product","Custom via Python + our Slack webhook","Funnel has alert rules; Data Studio does not"],
  ["","Writeback to ad platforms (pause / scale / keywords)","✗","✓","✗","Display only","Python cells call Google Ads / Meta APIs directly","Read-only; no writeback"],
  ["","Scheduled report delivery","✓","✓","✓","","Hex scheduled runs + Railway cron","Data Studio scheduled email"],
  ["","Programmatic / API access for agent reads","✗","✓","⚠ partial","No machine-readable output API","Agent reads BQ directly — Hex is the UI layer only","Funnel has a data read API; no API for custom dim definitions"],
  ["","Connector maintenance (API version updates)","✓","✗","✓","Databox maintains all connectors","We own every collector — we absorb every API deprecation","Funnel maintains all 325+ connectors"],

  ["SHARING & ACCESS","","","","","","",""],
  ["","Public shareable link (no login required)","✓","✓","✓","","Team plan — published app URL","Data Studio link sharing"],
  ["","Embed in other tools (iframe)","✓","⚠ partial","✓","","","Data Studio embeds cleanly"],
  ["","Mobile native app","✓","✗","✗","iOS + Android","",""],

  ["PRICING","","","","","","",""],
  ["","Free tier available","✗","✓","⚠ partial","Trial only","1 user free forever","Funnel: no. Data Studio: free."],
  ["","Approximate monthly cost","~$59–$199/mo","~$24/user/mo","Funnel $1k–$3k+/mo","Scales with connection count","Team plan; BQ compute billed separately","Data Studio = free"],
  ["","Cost scales with data volume","✗","⚠ partial","✓","Flat per plan tier","BQ compute scales; Hex seat fee flat","Funnel prices by connector count + row volume"],

  ["DECISION","","","","","","",""],
  ["","Verdict — what we keep","PRIMARY ✓","INTERNAL\nOPTIMIZATION ✓","DROPPED ✗","Team dashboards / KPIs / alerts / mobile — zero maintenance","Python analysis / forecasting / writeback / ad pauses","~$1–3k/mo replaced by Databox; connector advantage eliminated"],
];

// Split: Slide 1 = DATA & CONNECTORS + VISUALIZATION, Slide 2 = rest
const SLIDE1_SECTIONS = new Set(["DATA & CONNECTORS", "VISUALIZATION"]);
const rows1 = [], rows2 = [];
let inSlide1 = true;
for (const r of ALL_ROWS) {
  if (r[0] && !SLIDE1_SECTIONS.has(r[0])) inSlide1 = false;
  if (r[0] && SLIDE1_SECTIONS.has(r[0])) inSlide1 = true;
  (inSlide1 ? rows1 : rows2).push(r);
}

// ── Layout ────────────────────────────────────────────────────────────────────
const X_START  = 0.15;
const Y_START  = 0.08;
const TABLE_W  = 13.3 - X_START * 2;   // 13.0"
const COL_W    = [5.0, 2.5, 2.3, 3.2]; // Feature | Databox | Hex | Funnel
const TITLE_H  = 0.50;
const HDR_H    = 0.30;
const CAT_H    = 0.22;
const ROW_H    = 0.215;

function valStyle(val) {
  const s = String(val);
  if (s === "✓" || s === "PRIMARY ✓" || s.startsWith("INTERNAL"))
    return { bg: C.GREEN_BG, tx: C.GREEN_TX, bold: true };
  if (s === "✗" || s === "DROPPED ✗")
    return { bg: C.RED_BG, tx: C.RED_TX, bold: true };
  if (s.startsWith("⚠"))
    return { bg: C.AMBER_BG, tx: C.AMBER_TX, bold: false };
  return { bg: null, tx: null, bold: false };
}

function drawTable(pres, slide, rows, title, subtitle) {
  const x0 = X_START;
  let y    = Y_START;
  const tw = TABLE_W;

  // Title bar
  slide.addShape(pres.ShapeType.rect, {
    x: x0, y, w: tw, h: TITLE_H,
    fill: { color: C.NAVY }, line: { color: C.NAVY, pt: 0 },
  });
  slide.addText(title, {
    x: x0, y: y + 0.04, w: tw, h: 0.28,
    fontSize: 16, bold: true, color: C.WHITE,
    align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
  });
  slide.addText(subtitle, {
    x: x0, y: y + 0.32, w: tw, h: 0.16,
    fontSize: 8.5, color: C.BLUE_LT,
    align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
  });
  y += TITLE_H;

  // Column headers
  const colLabels = ["Feature / Capability", "Databox", "Hex", "Funnel + Data Studio"];
  let cx = x0;
  for (let i = 0; i < colLabels.length; i++) {
    slide.addShape(pres.ShapeType.rect, {
      x: cx, y, w: COL_W[i], h: HDR_H,
      fill: { color: C.DARK_NAV }, line: { color: C.DEEP_NAV, pt: 0.5 },
    });
    slide.addText(colLabels[i], {
      x: cx, y, w: COL_W[i], h: HDR_H,
      fontSize: 9, bold: true, color: C.WHITE,
      align: "center", valign: "middle", fontFace: "Calibri", margin: 2,
    });
    cx += COL_W[i];
  }
  y += HDR_H;

  let dataIdx = 0;
  const speakerNotes = [];

  for (const rec of rows) {
    const [cat, feature, db, hx, fn, dbNote, hxNote, fnNote] = rec;

    if (cat) {
      slide.addShape(pres.ShapeType.rect, {
        x: x0, y, w: tw, h: CAT_H,
        fill: { color: C.CAT_BG }, line: { color: "C7D2E8", pt: 0.5 },
      });
      slide.addText(`  ${cat}`, {
        x: x0, y, w: tw, h: CAT_H,
        fontSize: 9, bold: true, color: C.CAT_TX,
        align: "left", valign: "middle", fontFace: "Calibri", margin: 4,
      });
      y += CAT_H;
    } else {
      dataIdx++;
      const rowBg = dataIdx % 2 === 1 ? C.WHITE : C.ROW_ALT;

      // Feature cell
      slide.addShape(pres.ShapeType.rect, {
        x: x0, y, w: COL_W[0], h: ROW_H,
        fill: { color: rowBg }, line: { color: C.BORDER, pt: 0.5 },
      });
      slide.addText(`  ${feature}`, {
        x: x0, y, w: COL_W[0], h: ROW_H,
        fontSize: 8.5, color: C.TXT,
        align: "left", valign: "middle", fontFace: "Calibri", margin: 3,
      });

      // Value cells
      let vx = x0 + COL_W[0];
      for (const [val, cw] of [[db, COL_W[1]], [hx, COL_W[2]], [fn, COL_W[3]]]) {
        const vs = valStyle(val);
        slide.addShape(pres.ShapeType.rect, {
          x: vx, y, w: cw, h: ROW_H,
          fill: { color: vs.bg || rowBg }, line: { color: C.BORDER, pt: 0.5 },
        });
        slide.addText(String(val), {
          x: vx, y, w: cw, h: ROW_H,
          fontSize: 8.5, bold: vs.bold, color: vs.tx || C.TXT,
          align: "center", valign: "middle", fontFace: "Calibri", margin: 2,
        });
        vx += cw;
      }

      // Collect speaker notes
      const notes = [dbNote, hxNote, fnNote].filter(Boolean);
      if (notes.length) {
        speakerNotes.push(`${feature}:\n  Databox: ${dbNote || "—"}\n  Hex: ${hxNote || "—"}\n  Funnel: ${fnNote || "—"}`);
      }

      y += ROW_H;
    }
  }

  if (speakerNotes.length) {
    slide.addNotes(speakerNotes.join("\n\n"));
  }
}

// ── Build ─────────────────────────────────────────────────────────────────────
const pres   = new pptxgen();
pres.layout  = "LAYOUT_WIDE";
pres.author  = "Qoyod Performance Agent";
pres.title   = "BI Tool Comparison — Databox vs Hex vs Funnel";
pres.subject = "Qoyod BI Stack Decision — 2026-06-10";

const s1 = pres.addSlide();
s1.background = { color: "F8FAFC" };
drawTable(pres, s1, rows1,
  "BI Tool Comparison — Databox vs Hex vs Funnel + Data Studio",
  "Data & Connectors  ·  Visualization  ·  Qoyod 2026-06-10"
);

const s2 = pres.addSlide();
s2.background = { color: "F8FAFC" };
drawTable(pres, s2, rows2,
  "BI Tool Comparison — Databox vs Hex vs Funnel + Data Studio",
  "Analysis & SQL  ·  Ops & Automation  ·  Sharing  ·  Pricing  ·  Decision  ·  Qoyod 2026-06-10"
);

const OUT = path.join(__dirname, "..", "BI_Tool_Comparison.pptx");
pres.writeFile({ fileName: OUT }).then(() => {
  console.log("Done:", OUT);
}).catch(e => { console.error(e.message); process.exit(1); });
