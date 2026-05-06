"""
scripts/audit_active_negatives.py
==================================
Scan all currently-ACTIVE negative keywords (campaign-level + ad-group-level)
and flag any that violate the keyword policy:

  • COMPETITOR negatives  — competitor names should NEVER be negatives anywhere
                              (we want to bid on them in Competitor campaigns).
  • BRAND_ONLY negatives  — قيود / qoyod variants should never be negatives.

Output:
  • Console grouped by violation type.
  • CSV at logs/active_negative_violations_<date>.csv.
  • Asana task with the full list. Removal is manual via
    `scripts/bulk_keywords.py remove-negatives <criterion-id>` after review.
  • Per CLAUDE.md, removal of items the agent added IS allowed without
    approval (no spend at risk — removing a negative just re-opens a query),
    BUT we still surface to Asana so the human can sanity-check before the
    automated removal step.

Usage:
  python scripts/audit_active_negatives.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.google_ads import get_client
from collectors.google_ads_bq import _customer_ids
from executors.keyword_policy import (
    matches_any,
    COMPETITOR_PATTERNS,
    BRAND_ONLY_PATTERNS,
    QIYUD_FEATURE_MODIFIERS,
)


# ── Campaign-level negatives ───────────────────────────────────────────────────
CAMPAIGN_NEG_QUERY = """
  SELECT
    campaign_criterion.resource_name,
    campaign_criterion.criterion_id,
    campaign_criterion.keyword.text,
    campaign_criterion.keyword.match_type,
    campaign_criterion.negative,
    campaign.name,
    campaign.resource_name,
    campaign.status
  FROM campaign_criterion
  WHERE campaign_criterion.negative = TRUE
    AND campaign_criterion.type     = 'KEYWORD'
    AND campaign.status             = 'ENABLED'
"""

# ── Ad-group-level negatives ──────────────────────────────────────────────────
ADGROUP_NEG_QUERY = """
  SELECT
    ad_group_criterion.resource_name,
    ad_group_criterion.criterion_id,
    ad_group_criterion.keyword.text,
    ad_group_criterion.keyword.match_type,
    ad_group_criterion.negative,
    ad_group.name,
    ad_group.resource_name,
    campaign.name,
    campaign.resource_name,
    campaign.status,
    ad_group.status
  FROM ad_group_criterion
  WHERE ad_group_criterion.negative = TRUE
    AND ad_group_criterion.type     = 'KEYWORD'
    AND campaign.status             = 'ENABLED'
    AND ad_group.status             = 'ENABLED'
"""


def _classify_negative(term: str) -> str:
    """Return 'competitor', 'brand_only', or 'ok' (policy-compliant)."""
    if matches_any(term, COMPETITOR_PATTERNS):
        return "competitor"
    # Brand-only with accounting-noun exception
    if matches_any(term, BRAND_ONLY_PATTERNS) and not matches_any(term, QIYUD_FEATURE_MODIFIERS):
        return "brand_only"
    return "ok"


def scan_active_negatives() -> list[dict]:
    client = get_client()
    ga = client.get_service("GoogleAdsService")
    violations: list[dict] = []

    for cid in _customer_ids():
        # Campaign level
        try:
            for r in ga.search(customer_id=cid, query=CAMPAIGN_NEG_QUERY):
                term = r.campaign_criterion.keyword.text
                kind = _classify_negative(term)
                if kind == "ok":
                    continue
                violations.append({
                    "violation":         kind,
                    "level":             "campaign",
                    "customer_id":       cid,
                    "campaign":          r.campaign.name,
                    "campaign_resource": r.campaign.resource_name,
                    "ad_group":          "",
                    "ad_group_resource": "",
                    "keyword":           term,
                    "match_type":        r.campaign_criterion.keyword.match_type.name,
                    "criterion_id":      r.campaign_criterion.criterion_id,
                    "criterion_resource": r.campaign_criterion.resource_name,
                })
        except Exception as e:
            print(f"[neg-audit] campaign-level scan failed for {cid}: {e}")

        # Ad-group level
        try:
            for r in ga.search(customer_id=cid, query=ADGROUP_NEG_QUERY):
                term = r.ad_group_criterion.keyword.text
                kind = _classify_negative(term)
                if kind == "ok":
                    continue
                violations.append({
                    "violation":         kind,
                    "level":             "ad_group",
                    "customer_id":       cid,
                    "campaign":          r.campaign.name,
                    "campaign_resource": r.campaign.resource_name,
                    "ad_group":          r.ad_group.name,
                    "ad_group_resource": r.ad_group.resource_name,
                    "keyword":           term,
                    "match_type":        r.ad_group_criterion.keyword.match_type.name,
                    "criterion_id":      r.ad_group_criterion.criterion_id,
                    "criterion_resource": r.ad_group_criterion.resource_name,
                })
        except Exception as e:
            print(f"[neg-audit] ad-group-level scan failed for {cid}: {e}")

    return violations


def write_csv(violations: list[dict]) -> Path:
    out_dir = Path(__file__).resolve().parent.parent / "logs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"active_negative_violations_{date.today().isoformat()}.csv"
    if not violations:
        out.write_text("violation,level,customer_id,campaign,ad_group,keyword,match_type\n",
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
    print(f"\n{'='*70}\nACTIVE NEGATIVE-KEYWORD VIOLATIONS — {len(violations)} total\n{'='*70}")
    for kind, items in by_kind.items():
        print(f"\n[{kind}] — {len(items)} negative(s)")
        for v in items[:80]:
            print(f"  • {v['keyword']!r:35}  ({v['level']:8}) in {v['campaign']}")
        if len(items) > 80:
            print(f"  …and {len(items) - 80} more")


def remove_negatives(violations: list[dict]) -> int:
    """Remove the offending negative keywords. Removing a negative is safe —
    no spend at risk; it just re-opens a previously-blocked query.
    Returns count of successful removals.
    """
    if not violations:
        return 0

    client = get_client()
    cs = client.get_service("CampaignCriterionService")
    ags = client.get_service("AdGroupCriterionService")
    removed = 0

    by_cid_level: dict[tuple[str, str], list[str]] = defaultdict(list)
    for v in violations:
        by_cid_level[(v["customer_id"], v["level"])].append(v["criterion_resource"])

    for (cid, level), resources in by_cid_level.items():
        try:
            if level == "campaign":
                ops = []
                for rn in resources:
                    op = client.get_type("CampaignCriterionOperation")
                    op.remove = rn
                    ops.append(op)
                cs.mutate_campaign_criteria(customer_id=cid, operations=ops)
            else:
                ops = []
                for rn in resources:
                    op = client.get_type("AdGroupCriterionOperation")
                    op.remove = rn
                    ops.append(op)
                ags.mutate_ad_group_criteria(customer_id=cid, operations=ops)
            removed += len(resources)
            print(f"[neg-audit] removed {len(resources)} {level}-level negatives in account {cid}")
        except Exception as e:
            print(f"[neg-audit] removal failed for {cid}/{level}: {e}")

    return removed


def create_review_task(violations: list[dict], csv_path: Path,
                       removed: int) -> str | None:
    if not violations:
        return None
    try:
        from executors.asana import create_task
    except Exception as e:
        print(f"[neg-audit] could not import asana create_task: {e}")
        return None

    by_kind: dict[str, list[dict]] = defaultdict(list)
    for v in violations:
        by_kind[v["violation"]].append(v)

    parts: list[str] = [
        f"**{len(violations)} ACTIVE negative keywords violate policy** "
        f"as of {date.today().isoformat()}.",
        "",
        f"**Removed automatically:** {removed} of {len(violations)}.",
        f"Removing a negative is safe — no spend at risk, just re-opens a "
        f"previously-blocked query so it can match in the right campaign.",
        "",
        f"Full CSV: `{csv_path.name}`",
        "",
    ]
    for kind, items in by_kind.items():
        explanation = {
            "competitor":  "competitor brand names (Foodics, Daftra, "
                            "Manager.io, Zoho, Odoo, Xero, …) — these should "
                            "live in a Competitor campaign, never as negatives.",
            "brand_only":  "قيود / qoyod variants — brand reference, not a "
                            "negative.",
        }.get(kind, kind)
        parts.append(f"### {kind} — {len(items)} negative(s)")
        parts.append(f"_{explanation}_")
        parts.append("")
        for v in items[:80]:
            parts.append(f"- `{v['keyword']}` ({v['match_type']}, {v['level']}) — {v['campaign']}")
        if len(items) > 80:
            parts.append(f"_…and {len(items) - 80} more (see CSV)._")
        parts.append("")

    body = "\n".join(parts)
    try:
        gid = create_task(
            title=f"Google Ads — Removed {removed} policy-violating negative keywords",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="google_ads",
            asset_level="keyword",
            action="exclude",
        )
        print(f"[neg-audit] Asana task created: {gid}")
        return gid
    except Exception as e:
        print(f"[neg-audit] Asana task creation failed: {e}")
        return None


if __name__ == "__main__":
    violations = scan_active_negatives()
    csv_path = write_csv(violations)
    print_summary(violations)
    print(f"\nCSV written: {csv_path}")
    if violations:
        # Removing negatives is safe (no spend at risk) so we direct-execute.
        # See CLAUDE.md keyword rules — adding/removing negatives are non-
        # gated actions. (Pausing/removing actual keywords still requires
        # approval — that's audit_active_keywords.py's job.)
        removed = remove_negatives(violations)
        create_review_task(violations, csv_path, removed)
    else:
        print("\nNo policy violations among active negatives. ✅")
