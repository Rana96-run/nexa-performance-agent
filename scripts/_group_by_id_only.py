"""Collapse name variations under the same ID — change GROUP BY in all 18
channel breakdown SQL files to group by ID only, with MAX(name) for display.

Result: a renamed campaign/adset/ad shows as ONE row (latest name + all
historical spend + leads), regardless of how many times it was renamed.

Files affected (3 levels × 6 channels = 18):
  by_channel/<channel>/1_campaigns.sql
  by_channel/<channel>/2_adsets.sql
  by_channel/<channel>/3_ads.sql
"""
import re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(".claude/hex_drilldown")

# Per file pattern: (file_glob, id_col, name_source_col)
# For campaign files, name source is `campaign_name` (direct field on view)
# For adset files,    name source is `utm_audience` (= adset_name)
# For ad files,       name source is `utm_content`  (= ad_name)
PATTERNS = [
    ("by_channel/*/1_campaigns.sql", "campaign_id", "campaign_name"),
    ("by_channel/*/2_adsets.sql",    "adset_id",    "utm_audience"),
    ("by_channel/*/3_ads.sql",       "ad_id",       "utm_content"),
]


def collapse_to_id(path: Path, id_col: str, name_col: str) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    # 1) Convert SELECT `<name_col> AS <alias>` → `MAX(<name_col>) AS <alias>`
    #    Match patterns like:  `utm_content                AS ad_name,`
    #    But ONLY in projection (not GROUP BY etc).
    text = re.sub(
        rf"(\s+){re.escape(name_col)}(\s+AS\s+\w+,?)",
        rf"\1MAX({name_col}){re.sub(r'^\s+', '', '\\2')}",
        text,
        count=1,  # first match only — the SELECT projection
    )
    # Above regex's \2 starts with whitespace; we need to keep formatting clean.
    # Simpler form below — just rewrite the specific line:
    text = re.sub(
        rf"^(\s+){re.escape(name_col)}(\s+)AS(\s+)(\w+)(,?)$",
        rf"\1MAX({name_col})\2AS\3\4\5",
        text,
        count=1,
        flags=re.MULTILINE,
    )

    # 2) Update GROUP BY to drop name_col.
    #    Cases:
    #    a) "GROUP BY <id>, <name>"  → "GROUP BY <id>"
    #    b) "GROUP BY <name>"        → "GROUP BY <id>"  (where id was just added)
    text = re.sub(
        rf"GROUP\s+BY\s+{re.escape(id_col)}\s*,\s*{re.escape(name_col)}",
        f"GROUP BY {id_col}",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"GROUP\s+BY\s+{re.escape(name_col)}\b",
        f"GROUP BY {id_col}",
        text,
        flags=re.IGNORECASE,
    )

    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


for pattern, id_col, name_col in PATTERNS:
    for path in ROOT.glob(pattern):
        changed = collapse_to_id(path, id_col, name_col)
        flag = "[+]" if changed else "[!]"
        print(f"  {flag} {path} — GROUP BY → {id_col} only, {name_col} wrapped in MAX()")
