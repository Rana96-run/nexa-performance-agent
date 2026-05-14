"""Bulk-update Hex dashboard SQL files in .claude/hex_drilldown/ to match the
slimmed views (new_biz only) and the ID-attribution architecture.

What we remove:
  - SUM/SELECT lines aliasing or referencing the all-pipeline deal cols:
    deals_won, deals_lost, deals_open, revenue_won, amount_lost, amount_open,
    amount_total, total_deal_amount, closed_won_amount, closed_lost_amount,
    open_deal_amount, roas (case-insensitive)
  - The _prev pivot variants and the _change_pct lines built off them
  - Comment lines tagging these sections ("all pipelines", "All-pipeline")

What we keep:
  - Every new_biz_* variant (incl. new_biz_roas, new_biz_*_prev, new_biz_*_change_pct)

What we ADD:
  - 1_campaigns.sql files: campaign_id column in SELECT + GROUP BY
    (so duplicate-named campaigns separate by ID — Option B output).
"""
import os, sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(".claude/hex_drilldown")

# Bare alias tokens to drop. We drop any LINE whose stripped form contains
# `AS <token>,` or `AS <token>` at end-of-line, OR a bare `<token>,` listed
# alone in a SELECT projection. The new_biz_* variants are preserved because
# they have a different alias prefix.
ALL_PIPELINE_ALIASES = [
    "deals_won", "deals_lost", "deals_open",
    "revenue_won", "amount_lost", "amount_open", "amount_total",
    "total_deal_amount", "closed_won_amount", "closed_lost_amount", "open_deal_amount",
    "roas", "ROAS",
    # _prev and _change_pct variants (in 1_channel_overview pivots)
    "deals_won_prev", "deals_lost_prev", "deals_open_prev",
    "revenue_won_prev", "amount_lost_prev", "amount_open_prev", "amount_total_prev",
    "roas_prev",
    "revenue_won_change_pct", "amount_total_change_pct", "roas_change_pct",
]

# Comment fragments (case-insensitive) that flag the all-pipeline sections.
DROP_COMMENT_FRAGMENTS = [
    "all pipelines",
    "all-pipeline",
    "ROAS — two flavors",  # comment line; will keep new_biz_roas below it
    "Deal counts (all pipelines)",
    "Deal amounts (all pipelines)",
]


def line_drops_for_alias(line: str) -> bool:
    """Return True if the line should be dropped because it aliases or
    references an all-pipeline column we removed."""
    stripped = line.strip()
    # Skip blank
    if not stripped:
        return False
    low = stripped.lower()

    # Never drop if line mentions a new_biz_ alias — safety guard
    if "new_biz_" in low:
        return False

    for tok in ALL_PIPELINE_ALIASES:
        # Match cases:
        #   ... AS roas,
        #   ... AS roas
        #   roas,
        #   roas
        # Use word boundaries so deals_won doesn't match new_biz_deals_won.
        pattern = rf"\bAS\s+{re.escape(tok)}\b\s*,?\s*$"
        if re.search(pattern, stripped, re.IGNORECASE):
            return True
        # Bare-token line in a SELECT projection: "  deals_won,"
        if re.fullmatch(rf"{re.escape(tok)}\s*,?", stripped):
            return True
    return False


def line_is_dropped_comment(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("--"):
        return False
    low = stripped.lower()
    for frag in DROP_COMMENT_FRAGMENTS:
        if frag.lower() in low:
            return True
    return False


def slim_file(path: Path) -> dict:
    """Process one file. Returns stats."""
    text = path.read_text(encoding="utf-8")
    out_lines = []
    dropped = 0
    for line in text.splitlines(keepends=True):
        if line_drops_for_alias(line) or line_is_dropped_comment(line):
            dropped += 1
            continue
        out_lines.append(line)

    # Clean up: a trailing `,` on the last projection column before FROM is
    # syntactically OK in BQ if next non-blank line starts with FROM only if
    # the comma is BEFORE FROM. But BQ rejects `col1, col2, FROM ...`.
    # We need to make sure the last kept projection line doesn't end with a
    # trailing comma if the next non-empty line starts with FROM/`)` (subquery
    # close) or GROUP BY etc.
    joined = "".join(out_lines)
    # Regex: trailing `,` on a line, followed by whitespace, optional comments,
    # then a line starting with FROM | ) | GROUP BY | ORDER BY | WHERE | HAVING
    # We trim that trailing comma.
    pattern = re.compile(
        r",(\s*(?:--[^\n]*\n\s*)*)(?=\s*(?:FROM|\)|GROUP\s+BY|ORDER\s+BY|WHERE|HAVING))",
        re.IGNORECASE,
    )
    fixed, n_commas = pattern.subn(r"\1", joined)

    if dropped > 0 or n_commas > 0:
        path.write_text(fixed, encoding="utf-8")
    return {"dropped_lines": dropped, "trailing_commas_fixed": n_commas}


def add_campaign_id_to_campaign_files():
    """1_campaigns.sql files: surface campaign_id from paid_channel_campaign_daily
    so duplicate-name campaigns separate cleanly (Option B output)."""
    for path in ROOT.glob("by_channel/*/1_campaigns.sql"):
        text = path.read_text(encoding="utf-8")
        if "campaign_id" in text and "GROUP BY campaign_id" in text:
            print(f"  [skip] {path} — already has campaign_id")
            continue
        # Insert `campaign_id,` right before `campaign_name,` in SELECT
        new_text = re.sub(
            r"(\s+)campaign_name(,?)",
            r"\1campaign_id\2\1campaign_name\2",
            text,
            count=1,
        )
        # Update GROUP BY campaign_name -> GROUP BY campaign_id, campaign_name
        new_text = re.sub(
            r"GROUP BY campaign_name",
            "GROUP BY campaign_id, campaign_name",
            new_text,
        )
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            print(f"  [+] {path} — added campaign_id col + GROUP BY")
        else:
            print(f"  [!] {path} — no campaign_name match found, skip")


def main():
    sql_files = list(ROOT.rglob("*.sql"))
    print(f"Scanning {len(sql_files)} SQL files…\n")

    total_dropped = 0
    files_changed = 0
    for path in sql_files:
        stats = slim_file(path)
        if stats["dropped_lines"] > 0 or stats["trailing_commas_fixed"] > 0:
            files_changed += 1
            total_dropped += stats["dropped_lines"]
            print(f"  [edit] {path}: -{stats['dropped_lines']} lines, "
                  f"-{stats['trailing_commas_fixed']} trailing commas")

    print(f"\nSlim phase: {files_changed} files edited, "
          f"{total_dropped} all-pipeline lines removed.\n")

    print("Adding campaign_id to 1_campaigns.sql files…")
    add_campaign_id_to_campaign_files()


if __name__ == "__main__":
    main()
