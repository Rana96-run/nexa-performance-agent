/**
 * Apply color formatting to the BI Tool Comparison Google Sheet.
 *
 * How to use:
 *   1. Open the sheet: https://docs.google.com/spreadsheets/d/1Rq6tsAvD-2mlA0cJOiF46EB0fkX5HkeEGFXZr4drHuI/edit
 *   2. Extensions → Apps Script
 *   3. Paste this entire file, replacing any existing code
 *   4. Click Run → formatComparison
 *   5. Approve the permissions popup
 *
 * Takes ~5 seconds to run.
 */

function formatComparison() {
  const ss     = SpreadsheetApp.getActiveSpreadsheet();
  const sheet  = ss.getSheets()[0];
  const data   = sheet.getDataRange().getValues();
  const nRows  = data.length;
  const nCols  = data[0].length;

  // ── colours ───────────────────────────────────────────────────────────────
  const C_NAVY    = "#1E5FA4";
  const C_CAT     = "#E8ECF2";
  const C_GREEN   = "#D9F2E0";
  const C_RED     = "#FCE0E0";
  const C_AMBER   = "#FEF3CC";
  const C_GREY    = "#F5F5F5";
  const C_WHITE   = "#FFFFFF";
  const C_HEADTXT = "#FFFFFF";
  const C_CATTXT  = "#2C3E6B";

  // ── helpers ───────────────────────────────────────────────────────────────
  function isCategory(row) {
    // A category row has something in col A and nothing in col B
    return row[0] !== "" && row[1] === "";
  }

  function statusColor(val) {
    const s = String(val).trim();
    if (s === "✓" || s.startsWith("PRIMARY") || s.startsWith("INTERNAL OPTIMIZATION"))
      return C_GREEN;
    if (s === "✗" || s.startsWith("DROPPED"))
      return C_RED;
    if (s.startsWith("⚠"))
      return C_AMBER;
    return null;
  }

  // ── row 1: header ─────────────────────────────────────────────────────────
  const headerRange = sheet.getRange(1, 1, 1, nCols);
  headerRange.setBackground(C_NAVY);
  headerRange.setFontColor(C_HEADTXT);
  headerRange.setFontWeight("bold");
  headerRange.setFontSize(11);
  headerRange.setHorizontalAlignment("center");
  headerRange.setVerticalAlignment("middle");
  headerRange.setWrap(true);
  sheet.setRowHeight(1, 28);

  // ── freeze header row ─────────────────────────────────────────────────────
  sheet.setFrozenRows(1);

  // ── data rows ─────────────────────────────────────────────────────────────
  for (let r = 1; r < nRows; r++) {
    const row      = data[r];
    const sheetRow = r + 1;

    if (isCategory(row)) {
      // section header
      const catRange = sheet.getRange(sheetRow, 1, 1, nCols);
      catRange.setBackground(C_CAT);
      catRange.setFontColor(C_CATTXT);
      catRange.setFontWeight("bold");
      catRange.setFontSize(10);
      catRange.setVerticalAlignment("middle");
      catRange.setWrap(true);
      sheet.setRowHeight(sheetRow, 22);
    } else {
      // feature row
      const rowBg = (sheetRow % 2 === 0) ? C_GREY : C_WHITE;

      for (let c = 0; c < nCols; c++) {
        const cell = sheet.getRange(sheetRow, c + 1);
        const val  = row[c];

        // columns B/C/D (index 1/2/3) get status colours
        if (c >= 1 && c <= 3) {
          const sc = statusColor(val);
          cell.setBackground(sc || C_WHITE);
          cell.setFontWeight(sc ? "bold" : "normal");
          cell.setHorizontalAlignment("center");
        } else {
          cell.setBackground(rowBg);
          cell.setHorizontalAlignment(c === 0 ? "left" : "left");
          cell.setFontColor(c === 0 ? C_CATTXT : "#555555");
          cell.setFontSize(10);
        }

        cell.setVerticalAlignment("middle");
        cell.setWrap(true);
      }
      sheet.setRowHeight(sheetRow, 38);
    }
  }

  // ── column widths ─────────────────────────────────────────────────────────
  sheet.setColumnWidth(1, 280);   // Feature
  sheet.setColumnWidth(2, 120);   // Databox
  sheet.setColumnWidth(3, 120);   // Hex
  sheet.setColumnWidth(4, 150);   // Funnel
  sheet.setColumnWidth(5, 280);   // Databox Notes
  sheet.setColumnWidth(6, 280);   // Hex Notes
  sheet.setColumnWidth(7, 280);   // Funnel Notes

  SpreadsheetApp.flush();
  SpreadsheetApp.getActiveSpreadsheet().toast("Formatting applied!", "Done", 3);
}
