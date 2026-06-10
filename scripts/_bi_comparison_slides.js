/**
 * BI Tool Comparison — Google Slides (via PPTX)
 * Two slides: Qoyod Performance | Generic SaaS
 * Upload output to Google Drive to auto-convert to Google Slides.
 */
const pptxgen = require("pptxgenjs");
const path = require("path");

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
  SUBTX:    "64748B",
  BLUE_LT:  "93C5FD",
  BLUE_MID: "BFDBFE",
};

const YES  = "✓";
const NO   = "✗";
const PART = "⚠ partial";
const VER  = "⚠ verify";

// ── Table data ────────────────────────────────────────────────────────────────
const ROWS_QOYOD = [
  ["DATA & CONNECTORS", "", "", "", ""],
  ["", "Ad platform connectors (Meta / Google / Snap / TikTok / LinkedIn)", YES, NO, YES],
  ["", "HubSpot Lead Module (object 0-136)", VER, YES, VER],
  ["", "HubSpot Deals connector", YES, YES, YES],
  ["", "BigQuery — raw SQL", YES, YES, YES],
  ["", "Zero connector maintenance", YES, NO, YES],
  ["", "USD normalization across channels", PART, YES, YES],
  ["", "UTC → Asia/Riyadh timezone", PART, YES, PART],
  ["", "Data refresh frequency", "15 min–24 h", "On-demand + 6 h", "6 h"],

  ["ANALYSIS — QOYOD KPIs", "", "", "", ""],
  ["", "CPQL from Lead Module (true qualified)", VER, YES, VER],
  ["", "Cross-channel blended CPL / CPQL", PART, YES, YES],
  ["", "Disqualification reason breakdown", NO, YES, NO],
  ["", "Ad / adset-level drill-down", YES, YES, YES],
  ["", "Raw SQL + Python in same workspace", NO, YES, NO],
  ["", "Version control on metric definitions", NO, YES, NO],

  ["VISUALIZATION", "", "", "", ""],
  ["", "Drag-and-drop dashboard builder", YES, NO, YES],
  ["", "Mobile-friendly / native app", YES, NO, PART],
  ["", "Real-time auto-refresh", YES, PART, NO],
  ["", "Branded (Qoyod navy + logo)", YES, YES, PART],
  ["", "Period-over-period delta tiles", YES, YES, YES],

  ["OPS & AUTOMATION", "", "", "", ""],
  ["", "Metric alerts (email / Slack)", YES, PART, YES],
  ["", "Writeback — pause / scale / keywords", NO, YES, NO],
  ["", "Scheduled report delivery", YES, YES, YES],
  ["", "API access for agent reads", NO, YES, PART],
  ["", "Connector maintenance ownership", "Databox", "We own it", "Funnel"],

  ["PRICING (current)", "", "", "", ""],
  ["", "Approximate monthly cost", "~$59–$199", "~$24/user", "$1k–$3k+"],
  ["", "Free tier available", NO, YES, PART],

  ["DECISION", "", "", "", ""],
  ["", "Verdict", "PRIMARY ✓", "INTERNAL\nOPTIMIZATION ✓", "DROPPED ✗"],
];

const ROWS_SAAS = [
  ["DATA & CONNECTORS", "", "", "", ""],
  ["", "Ad platform connectors (major channels)", YES, NO, YES],
  ["", "CRM connector (any — HubSpot / SF / Pipedrive)", YES, YES, YES],
  ["", "E-commerce / product analytics", YES, PART, YES],
  ["", "Data warehouse (BQ / Snowflake / Redshift)", YES, YES, YES],
  ["", "Zero connector maintenance", YES, NO, YES],
  ["", "Currency normalization", PART, YES, YES],
  ["", "Timezone control", PART, YES, PART],
  ["", "Data refresh frequency", "15 min–24 h", "On-demand + 6 h", "6 h"],

  ["SAAS KPIs", "", "", "", ""],
  ["", "MRR / ARR tracking", YES, YES, YES],
  ["", "Churn rate & cohort retention", PART, YES, PART],
  ["", "CAC / LTV / Payback period", PART, YES, YES],
  ["", "Pipeline velocity & win rate", YES, YES, YES],
  ["", "Product funnel (trial → paid)", PART, YES, PART],
  ["", "Custom formula metrics", YES, YES, PART],

  ["VISUALIZATION", "", "", "", ""],
  ["", "No-code dashboard builder", YES, NO, YES],
  ["", "Mobile app / responsive view", YES, NO, PART],
  ["", "Real-time refresh", YES, PART, NO],
  ["", "White-label / branded dashboards", YES, YES, PART],
  ["", "Exec-ready shareable link", YES, YES, YES],

  ["OPS & AUTOMATION", "", "", "", ""],
  ["", "KPI alerts (email / Slack / Teams)", YES, PART, YES],
  ["", "Automated report delivery", YES, YES, YES],
  ["", "API / programmatic access", NO, YES, PART],
  ["", "Writeback to ad platforms", NO, YES, NO],
  ["", "Connector maintenance ownership", "Vendor", "You own it", "Vendor"],

  ["PRICING", "", "", "", ""],
  ["", "Approx monthly cost (small team)", "~$59–$199", "~$24/user", "$500–$3k+"],
  ["", "Scales with data volume", NO, PART, YES],
  ["", "Free tier", NO, YES, PART],

  ["DECISION", "", "", "", ""],
  ["", "Best for", "Fast team\ndashboards", "Analyst +\nautomation", "Multi-source\nblending"],
];

// ── Layout constants ──────────────────────────────────────────────────────────
const SLIDE_W  = 13.3;
const SLIDE_H  = 7.5;
const X_START  = 0.15;
const Y_START  = 0.08;
const TABLE_W  = SLIDE_W - X_START * 2;   // 13.0"
const COL_W    = [5.0, 2.5, 2.3, 3.2];    // Feature | Databox | Hex | Funnel
const TITLE_H  = 0.52;
const HDR_H    = 0.30;
const CAT_H    = 0.22;
const ROW_H    = 0.195;

// ── Value styling ─────────────────────────────────────────────────────────────
function valStyle(val) {
  const s = String(val);
  if (s === YES || s === "PRIMARY ✓" || s.startsWith("INTERNAL"))
    return { bg: C.GREEN_BG, tx: C.GREEN_TX, bold: true };
  if (s === NO || s === "DROPPED ✗")
    return { bg: C.RED_BG, tx: C.RED_TX, bold: true };
  if (s.startsWith("⚠"))
    return { bg: C.AMBER_BG, tx: C.AMBER_TX, bold: false };
  return { bg: null, tx: null, bold: false };
}

// ── Draw one table on a slide ─────────────────────────────────────────────────
function drawTable(pres, slide, rows, title, subtitle) {
  const x0 = X_START;
  let y   = Y_START;
  const tw = TABLE_W;

  // Title bar (navy background)
  slide.addShape(pres.ShapeType.rect, {
    x: x0, y, w: tw, h: TITLE_H,
    fill: { color: C.NAVY }, line: { color: C.NAVY, pt: 0 },
  });
  // Title text
  slide.addText(title, {
    x: x0, y: y + 0.04, w: tw, h: 0.28,
    fontSize: 15, bold: true, color: C.WHITE,
    align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
  });
  // Subtitle text
  slide.addText(subtitle, {
    x: x0, y: y + 0.31, w: tw, h: 0.18,
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

  // Data rows
  let dataRowIdx = 0;

  for (const rec of rows) {
    const [cat, feature, db, hx, fn] = rec;

    if (cat) {
      // Section header — full-width
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
      dataRowIdx++;
      const rowBg = dataRowIdx % 2 === 1 ? C.WHITE : C.ROW_ALT;

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
        const cellBg = vs.bg || rowBg;
        const cellTx = vs.tx || C.TXT;

        slide.addShape(pres.ShapeType.rect, {
          x: vx, y, w: cw, h: ROW_H,
          fill: { color: cellBg }, line: { color: C.BORDER, pt: 0.5 },
        });
        slide.addText(String(val), {
          x: vx, y, w: cw, h: ROW_H,
          fontSize: 8.5, bold: vs.bold, color: cellTx,
          align: "center", valign: "middle", fontFace: "Calibri", margin: 2,
        });
        vx += cw;
      }

      y += ROW_H;
    }
  }
}

// ── Build presentation ────────────────────────────────────────────────────────
const pres = new pptxgen();
pres.layout  = "LAYOUT_WIDE";
pres.author  = "Qoyod Performance Agent";
pres.title   = "BI Tool Comparison — Databox vs Hex vs Funnel";
pres.subject = "Qoyod & Generic SaaS";

// Slide 1 — Qoyod
const s1 = pres.addSlide();
s1.background = { color: "F8FAFC" };
drawTable(pres, s1, ROWS_QOYOD,
  "BI Tool Comparison — Qoyod Performance",
  "Qoyod-specific  ·  CPQL / Lead Module / Writeback / Attribution  ·  2026-06-10"
);

// Slide 2 — Generic SaaS
const s2 = pres.addSlide();
s2.background = { color: "F8FAFC" };
drawTable(pres, s2, ROWS_SAAS,
  "BI Tool Comparison — Generic SaaS Business",
  "Applies to any B2B SaaS  ·  MRR / CAC / LTV / Churn / Pipeline  ·  2026-06-10"
);

const OUT = path.join(__dirname, "..", "BI_Tool_Comparison.pptx");
pres.writeFile({ fileName: OUT }).then(() => {
  console.log("Done:", OUT);
}).catch(e => {
  console.error("Error:", e.message);
  process.exit(1);
});
