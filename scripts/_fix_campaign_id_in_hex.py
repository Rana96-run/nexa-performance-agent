"""Fix the 6 channel/1_campaigns.sql files where the campaign_id insertion
accidentally hit a comment line. We need to:
1. Restore the comment line (remove campaign_id token added inside it).
2. Insert `campaign_id,` BEFORE the SELECT projection's campaign_name line."""
import os, sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(".claude/hex_drilldown")

for path in ROOT.glob("by_channel/*/1_campaigns.sql"):
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    new_lines = []
    inserted = False
    for line in lines:
        stripped = line.strip()

        # 1) Restore comment if my earlier regex polluted it (e.g.,
        # "column: campaign_id campaign_name)" → "column: campaign_name)")
        if stripped.startswith("--") and "campaign_id campaign_name" in line:
            line = line.replace("campaign_id campaign_name", "campaign_name")

        # 2) Detect the SELECT projection line for campaign_name (indented,
        # ends with comma, not a comment) and insert campaign_id before it.
        if (not inserted and not stripped.startswith("--")
                and re.fullmatch(r"\s+campaign_name,?", line)):
            # Match indentation
            indent = re.match(r"^(\s*)", line).group(1)
            new_lines.append(f"{indent}campaign_id,")
            inserted = True

        new_lines.append(line)

    if inserted:
        path.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"  [fix] {path} — campaign_id inserted before campaign_name in SELECT")
    else:
        print(f"  [!] {path} — campaign_name projection not found, manual check needed")
