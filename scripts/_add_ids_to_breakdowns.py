"""Surface adset_id in 2_adsets.sql and ad_id in 3_ads.sql for all 6 channels.
Adds the ID column to SELECT and GROUP BY (so duplicate-named adsets/ads
separate correctly — same Option B behaviour as campaigns)."""
import re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(".claude/hex_drilldown")

def add_id_col(path: Path, id_col: str, base_col: str) -> bool:
    """Insert `id_col,` before the base column in SELECT and update GROUP BY."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    new_lines = []
    inserted_select = False
    updated_group = False

    for line in lines:
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("--"):
            new_lines.append(line)
            continue

        # Detect SELECT projection: `<base_col>` aliased AS <base_col_name>
        # e.g. "utm_audience  AS adset_name," -- want to insert before this
        # Match patterns like:
        #   utm_audience                                  AS adset_name,
        #   utm_content                                   AS ad_name,
        if not inserted_select:
            m = re.fullmatch(rf"(\s+){re.escape(base_col)}\s+AS\s+\w+,?\s*", line)
            if m:
                indent = m.group(1)
                new_lines.append(f"{indent}{id_col},")
                inserted_select = True

        new_lines.append(line)

        # Update GROUP BY: append id_col when we see `GROUP BY <base_col>` (or with subselect indent)
        if not updated_group and re.search(rf"GROUP\s+BY\s+{re.escape(base_col)}\b", line, re.IGNORECASE):
            # Replace last line we appended (the GROUP BY line) with id-version
            # Use a more robust replace: insert id_col, before base_col in GROUP BY
            new_lines[-1] = re.sub(
                rf"GROUP\s+BY\s+{re.escape(base_col)}",
                f"GROUP BY {id_col}, {base_col}",
                line, flags=re.IGNORECASE,
            )
            updated_group = True

    if inserted_select or updated_group:
        path.write_text("\n".join(new_lines), encoding="utf-8")
        return True
    return False


# 2_adsets.sql files use utm_audience AS adset_name in SELECT
for path in ROOT.glob("by_channel/*/2_adsets.sql"):
    if add_id_col(path, id_col="adset_id", base_col="utm_audience"):
        print(f"  [+] {path} — adset_id added")
    else:
        print(f"  [!] {path} — pattern not found")

# 3_ads.sql files use utm_content AS ad_name in SELECT
for path in ROOT.glob("by_channel/*/3_ads.sql"):
    if add_id_col(path, id_col="ad_id", base_col="utm_content"):
        print(f"  [+] {path} — ad_id added")
    else:
        print(f"  [!] {path} — pattern not found")
