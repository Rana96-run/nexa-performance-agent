"""Add the all-pipeline metrics BACK to overview-level Hex SQL files.

Channel breakdown files (1_campaigns / 2_adsets / 3_ads) stay slim per user
direction. Overview-level files get the all-pipeline cols restored alongside
the new_biz_* cols so the user sees both views side-by-side.

Files to restore (23):
  - 0_scorecard.sql (top-level)
  - 1_channel_overview.sql
  - by_channel/<channel>/0_kpi_scorecard.sql × 6
  - by_trends/* (5 files)
  - by_pipeline/* (10 files)

Restoration patterns:
  For each `new_biz_<col>` line, add an unfiltered parallel `<col>` line.
"""
import os, sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(".claude/hex_drilldown")

FILES_TO_RESTORE = [
    ROOT / "0_scorecard.sql",
    ROOT / "1_channel_overview.sql",
    *list(ROOT.glob("by_channel/*/0_kpi_scorecard.sql")),
    *list(ROOT.glob("by_trends/*.sql")),
    *list(ROOT.glob("by_pipeline/*.sql")),
]

# Map: new_biz_<X> column suffix → source column from hubspot_deals_daily
# (for CTE SUM rebuilds)
NEWBIZ_TO_SOURCE = {
    "new_biz_deals_won":    "deals_won",
    "new_biz_deals_lost":   "deals_lost",
    "new_biz_deals_open":   "deals_open",
    "new_biz_deals_total":  "deals_total",
    "new_biz_revenue_won":  "amount_won",
    "new_biz_amount_lost":  "amount_lost",
    "new_biz_amount_open":  "amount_open",
    "new_biz_amount_total": "amount_total",
}
# Map: new_biz_<X> alias → all-pipeline alias (for SELECT outputs and ROAS)
NEWBIZ_TO_ALL_ALIAS = {
    "new_biz_deals_won":    "deals_won",
    "new_biz_deals_lost":   "deals_lost",
    "new_biz_deals_open":   "deals_open",
    "new_biz_deals_total":  "deals_total",
    "new_biz_revenue_won":  "revenue_won",   # All-pipeline alias is revenue_won (sum of amount_won)
    "new_biz_amount_lost":  "amount_lost",
    "new_biz_amount_open":  "amount_open",
    "new_biz_amount_total": "amount_total",
    "new_biz_roas":         "roas",
}


def restore_file(path: Path) -> int:
    """Add all-pipeline aliases beside new_biz aliases. Returns # of lines added."""
    text = path.read_text(encoding="utf-8")
    out_lines = []
    added = 0

    for line in text.split("\n"):
        out_lines.append(line)

        # Skip restoration if all-pipeline counterpart already in this file
        # (avoid duplicates).
        for nbz, all_alias in NEWBIZ_TO_ALL_ALIAS.items():
            # Detect a line that ends with `AS new_biz_<x>` or `AS new_biz_<x>,`
            m = re.search(rf"\bAS\s+{re.escape(nbz)}\b\s*(,?)\s*$", line)
            if not m:
                continue
            # Skip if file already has the all-pipeline equivalent somewhere
            if re.search(rf"\bAS\s+{re.escape(all_alias)}\b", text):
                continue

            # Build the parallel line. Detect pattern type:
            # (a) CTE SUM with CASE WHEN / IF pipeline filter (drop the filter)
            # (b) CTE SUM(d.new_biz_x) — pass-through aggregate (also use all_alias)
            # (c) SELECT COALESCE(d.new_biz_x, 0)
            # (d) SELECT ROUND(COALESCE(d.new_biz_x, 0), 2)
            # (e) SELECT SAFE_DIVIDE(...) AS new_biz_roas

            indent = re.match(r"^(\s*)", line).group(1)
            trailing_comma = m.group(1) or ","

            # Pattern (a): SUM(CASE WHEN pipeline IN (...) THEN <col> ELSE 0 END) AS new_biz_<x>
            ca = re.search(
                rf"SUM\(\s*CASE\s+WHEN\s+pipeline\s+IN\s*\([^)]+\)\s*\n?\s*THEN\s+(\w+)\s*ELSE\s*0\s*END\s*\)\s*AS\s+{re.escape(nbz)}\b",
                line, re.IGNORECASE,
            )
            cb = re.search(
                rf"SUM\(\s*IF\(\s*(?:\w+\.)?pipeline\s+IN\s*\([^)]+\)\s*,\s*(?:\w+\.)?(\w+)\s*,\s*0\s*\)\s*\)\s*AS\s+{re.escape(nbz)}\b",
                line, re.IGNORECASE,
            )
            src_col = None
            if ca:
                src_col = ca.group(1)
            elif cb:
                src_col = cb.group(1)

            if src_col is not None:
                # CTE aggregation: rebuild without pipeline filter
                # If the source was amount_won, output alias is revenue_won
                out_alias = "revenue_won" if src_col == "amount_won" else src_col
                # Detect table alias from line (e.g. d.amount_won)
                alias_m = re.search(rf"(\w+\.)?{re.escape(src_col)}", line)
                prefix = alias_m.group(1) or "" if alias_m else ""
                new_line = f"{indent}SUM({prefix}{src_col}) AS {out_alias}{trailing_comma}"
                out_lines.append(new_line)
                added += 1
                continue

            # Pattern (e): SAFE_DIVIDE / new_biz_roas
            if nbz == "new_biz_roas":
                # Find the SAFE_DIVIDE expression in this line
                sd = re.search(r"SAFE_DIVIDE\(([^,]+),\s*NULLIF\(([^,]+),\s*0\)\)", line)
                if sd:
                    num_expr = sd.group(1)
                    # Swap new_biz_revenue_won → revenue_won in numerator
                    num_all = num_expr.replace("new_biz_revenue_won", "revenue_won")
                    den_expr = sd.group(2)
                    # Detect ROUND wrap
                    if "ROUND(" in line:
                        new_line = f"{indent}ROUND(SAFE_DIVIDE({num_all}, NULLIF({den_expr}, 0)), 2) AS roas{trailing_comma}"
                    else:
                        new_line = f"{indent}SAFE_DIVIDE({num_all}, NULLIF({den_expr}, 0)) AS roas{trailing_comma}"
                    out_lines.append(new_line)
                    added += 1
                    continue

            # Pattern (c)/(d): COALESCE(d.new_biz_x, 0) AS new_biz_x  (optionally ROUND-wrapped)
            ce = re.search(
                rf"COALESCE\(\s*(\w+\.)?{re.escape(nbz)}\s*,\s*0\s*\)\s*AS\s+{re.escape(nbz)}\b",
                line, re.IGNORECASE,
            )
            if ce:
                tbl = ce.group(1) or ""
                if "ROUND(" in line:
                    new_line = f"{indent}ROUND(COALESCE({tbl}{all_alias}, 0), 2) AS {all_alias}{trailing_comma}"
                else:
                    new_line = f"{indent}COALESCE({tbl}{all_alias}, 0) AS {all_alias}{trailing_comma}"
                out_lines.append(new_line)
                added += 1
                continue

            # Pattern: SUM(d.new_biz_x) AS new_biz_x  (pass-through in nested CTE)
            cf = re.search(
                rf"SUM\(\s*(\w+\.)?{re.escape(nbz)}\s*\)\s*AS\s+{re.escape(nbz)}\b",
                line, re.IGNORECASE,
            )
            if cf:
                tbl = cf.group(1) or ""
                new_line = f"{indent}SUM({tbl}{all_alias}) AS {all_alias}{trailing_comma}"
                out_lines.append(new_line)
                added += 1
                continue

            # Pattern: MAX(IF(period='current', new_biz_x, NULL)) AS new_biz_x   (pivot in 1_channel_overview)
            cg = re.search(
                rf"MAX\(IF\(period='(\w+)',\s*{re.escape(nbz)}\s*,\s*NULL\)\)\s*AS\s+(\w+)",
                line, re.IGNORECASE,
            )
            if cg:
                period = cg.group(1)
                old_alias = cg.group(2)
                new_alias = old_alias.replace("new_biz_", "").replace(nbz.replace("new_biz_", ""), all_alias)
                # Actually simpler: just sub new_biz_ → empty / new_biz_X → X
                new_alias_line = re.sub(rf"new_biz_{re.escape(nbz.replace('new_biz_', ''))}", all_alias, old_alias)
                new_line = line.replace(f"MAX(IF(period='{period}', {nbz}", f"MAX(IF(period='{period}', {all_alias}")
                new_line = new_line.replace(f"AS {old_alias}", f"AS {new_alias_line}")
                out_lines.append(new_line)
                added += 1
                continue

    if added > 0:
        path.write_text("\n".join(out_lines), encoding="utf-8")
    return added


total_added = 0
files_changed = 0
for path in FILES_TO_RESTORE:
    if not path.exists():
        continue
    n = restore_file(path)
    if n > 0:
        files_changed += 1
        total_added += n
        print(f"  [restore] {path}: +{n} all-pipeline lines")
print(f"\n{files_changed} files restored, {total_added} all-pipeline lines added back.")
