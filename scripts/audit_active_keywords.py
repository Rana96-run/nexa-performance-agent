"""
scripts/audit_active_keywords.py
================================
One-off / on-demand audit: scan all currently-ENABLED Google Ads keywords
across all customer accounts and flag any that violate the keyword policy:

  • always_negative          — should never have been added (login / free /
                                دورات / تحميل / قرض / تمويل / وظيفة / etc.)
  • brand_only_block         — قيود/qoyod outside a Brand campaign
  • competitor_in_generic    — competitor name (Foodics, Daftra, Manager.io,
                                Zoho, Odoo, …) outside a Competitor campaign
  • language_mismatch        — Arabic keyword in `_EN_` campaign or vice versa

Output:
  • Console table grouped by violation type.
  • CSV at logs/active_keyword_violations_<date>.csv.
  • Asana task per violation type for human review. We do NOT autonomously
    pause — per CLAUDE.md, paused via `bulk_keywords.py pause` after review.

Usage:
  python scripts/audit_active_keywords.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# Make repo root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.google_ads import get_client
from collectors.google_ads_bq import _customer_ids
from executors.keyword_policy import classify_term


def scan_active_keywords() -> list[dict]:
    """
    Returns one dict per ENABLED keyword that violates policy.
    """
    client = get_client()
    ga = client.get_service("GoogleAdsService")

    query = """
      SELECT
        ad_group_criterion.resource_name,
        ad_group_criterion.criterion_id,
        ad_group_criterion.keyword.text,
        ad_group_criterion.keyword.match_type,
        ad_group_criterion.status,
        ad_group.name,
        ad_group.resource_name,
        ad_group.status,
        campaign.id,
        campaign.name,
        campaign.resource_name,
        campaign.status
      FROM keyword_view
      WHERE ad_group_criterion.status  = 'ENABLED'
        AND ad_group.status            = 'ENABLED'
        AND campaign.status            = 'ENABLED'
        AND ad_group_criterion.negative = FALSE
    """

    violations: list[dict] = []
    for cid in _customer_ids():
        try:
            rows = list(ga.search(customer_id=cid, query=query))
        except Exception as e:
            print(f"[active-kw-audit] account {cid} skipped: {e}")
            continue

        for r in rows:
            term = r.ad_group_criterion.keyword.text
            campaign_name = r.campaign.name
            kind = classify_term(term, campaign_name)
            # All four are violations when ENABLED:
            #  - always_negative      → never should be a keyword
            #  - brand_only_block     → قيود in non-Brand campaign
            #  - competitor_in_generic → competitor in non-Competitor campaign
            #  - language_mismatch    → AR/EN mismatch with campaign language
            if kind in ("always_negative", "brand_only_block",
                        "competitor_in_generic", "language_mismatch"):
                violations.append({
                    "violation":         kind,
                    "customer_id":       cid,
                    "campaign":          campaign_name,
                    "campaign_resource": r.campaign.resource_name,
                    "ad_group":          r.ad_group.name,
                    "ad_group_resource": r.ad_group.resource_name,
                    "keyword":           term,
                    "match_type":        r.ad_group_criterion.keyword.match_type.name,
                    "criterion_id":      r.ad_group_criterion.criterion_id,
                    "criterion_resource": r.ad_group_criterion.resource_name,
                })

    return violations


def write_csv(violations: list[dict]) -> Path:
    out_dir = Path(__file__).resolve().parent.parent / "logs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"active_keyword_violations_{date.today().isoformat()}.csv"
    if not violations:
        out.write_text("violation,customer_id,campaign,ad_group,keyword,match_type\n",
                       encoding="utf-8")
        return out
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(violations[0].keys()))
        w.writeheader()
        w.writerows(violations)
    return out


def print_summary(violations: list[dict]) -> None:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for v in violations:
        by_kind[v["violation"]].append(v)

    print(f"\n{'='*70}\nACTIVE KEYWORD POLICY VIOLATIONS — {len(violations)} total\n{'='*70}")
    for kind, items in by_kind.items():
        print(f"\n[{kind}] — {len(items)} keyword(s)")
        for v in items[:50]:
            print(f"  • {v['keyword']!r:40}  in  {v['campaign']}  ({v['ad_group']})")
        if len(items) > 50:
            print(f"  …and {len(items) - 50} more")


def create_review_task(violations: list[dict], csv_path: Path) -> str | None:
    """Create one Asana task summarising violations so a human can pause via bulk_keywords."""
    if not violations:
        return None
    try:
        from executors.asana import create_task
    except Exception as e:
        print(f"[active-kw-audit] could not import asana create_task: {e}")
        return None

    by_kind: dict[str, list[dict]] = defaultdict(list)
    for v in violations:
        by_kind[v["violation"]].append(v)

    parts: list[str] = [
        f"**{len(violations)} ENABLED keywords violate policy as of {date.today().isoformat()}.**",
        "",
        "These were caught by `scripts/audit_active_keywords.py`. They are still "
        "running and accruing spend. Review and pause via `bulk_keywords.py pause`.",
        "",
        f"Full CSV: `{csv_path.name}`",
        "",
    ]
    for kind, items in by_kind.items():
        rule_explanation = {
            "always_negative":      "match an ALWAYS-NEGATIVE pattern (login / free / "
                                    "دورات / تحميل / قرض / تمويل / وظائف / etc.) — "
                                    "should never have been ENABLED.",
            "brand_only_block":     "contain قيود / qoyod but live in a NON-BRAND "
                                    "campaign — must be moved to a Brand campaign "
                                    "or paused. (قيود محاسبية / قيود المحاسبة "
                                    "are accounting nouns and excluded from this rule.)",
            "competitor_in_generic":"are competitor brand names (Foodics, Daftra, "
                                    "Manager.io, Zoho, Odoo, Xero, …) sitting in a "
                                    "non-Competitor campaign. Move to the matching "
                                    "Competitor campaign or pause.",
            "language_mismatch":    "are Arabic keywords in an `_EN_` campaign or "
                                    "Latin-script keywords in an `_AR_` campaign. "
                                    "Move to a campaign of the matching language "
                                    "or pause.",
        }.get(kind, kind)

        parts.append(f"### {kind} — {len(items)} keyword(s)")
        parts.append(f"_{rule_explanation}_")
        parts.append("")
        for v in items[:50]:
            parts.append(f"- `{v['keyword']}` ({v['match_type']}) — {v['campaign']} → {v['ad_group']}")
        if len(items) > 50:
            parts.append(f"_…and {len(items) - 50} more (see CSV)._")
        parts.append("")

    body = "\n".join(parts)
    try:
        gid = create_task(
            title=f"Google Ads — {len(violations)} active keywords violate policy",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="google_ads",
            asset_level="keyword",
            action="pause",
        )
        print(f"[active-kw-audit] Asana task created: {gid}")
        return gid
    except Exception as e:
        print(f"[active-kw-audit] Asana task creation failed: {e}")
        return None


if __name__ == "__main__":
    violations = scan_active_keywords()
    csv_path = write_csv(violations)
    print_summary(violations)
    print(f"\nCSV written: {csv_path}")
    if violations:
        create_review_task(violations, csv_path)
    else:
        print("\nNo policy violations among ENABLED keywords. ✅")
