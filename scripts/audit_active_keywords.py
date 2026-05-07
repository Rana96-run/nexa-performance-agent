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
from executors.keyword_policy import (
    classify_term,
    keyword_first_impression_dates,
    days_since,
)
from config import MIN_KEYWORD_AGE_DAYS


def scan_active_keywords() -> list[dict]:
    """
    Returns one dict per ENABLED keyword that violates policy.

    Violation kinds:
      - always_negative           — pattern match (login / free / دورة / etc.)
      - brand_only_block          — قيود/qoyod outside Brand campaign
      - competitor_in_generic     — competitor outside Competitor campaign
      - language_mismatch         — script doesn't match `_AR_`/`_EN_` token
      - low_qs_high_lost_is_delete — QS<5 AND rank-lost-IS>80% AND zero all-time spend
                                      → safe to delete (no historical cost)
      - low_qs_high_lost_is_pause  — QS<5 AND rank-lost-IS>80% AND has spend
                                      → pause (per "never delete with cost" rule)
    """
    client = get_client()
    ga = client.get_service("GoogleAdsService")

    # Per-keyword 30d lifetime metrics: QS, rank-lost-IS, spend.
    # QS lives at criterion level; metrics aggregated across the window we ask for.
    # We use a long lookback (180d) so "all-time spend = 0" is meaningful.
    from datetime import date, timedelta
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=179)

    query = f"""
      SELECT
        ad_group_criterion.resource_name,
        ad_group_criterion.criterion_id,
        ad_group_criterion.keyword.text,
        ad_group_criterion.keyword.match_type,
        ad_group_criterion.status,
        ad_group_criterion.quality_info.quality_score,
        ad_group.name,
        ad_group.resource_name,
        ad_group.status,
        campaign.id,
        campaign.name,
        campaign.resource_name,
        campaign.status,
        metrics.cost_micros,
        metrics.conversions,
        metrics.search_rank_lost_impression_share
      FROM keyword_view
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND ad_group_criterion.status   = 'ENABLED'
        AND ad_group.status             = 'ENABLED'
        AND campaign.status             = 'ENABLED'
        AND ad_group_criterion.negative = FALSE
    """

    violations: list[dict] = []
    # Aggregate per criterion since segments.date returns daily rows. We sum
    # cost and take the last-seen QS / IS-lost values.
    from collections import defaultdict
    LOW_QS = 5
    HIGH_LOST_IS = 0.80

    for cid in _customer_ids():
        try:
            rows = list(ga.search(customer_id=cid, query=query))
        except Exception as e:
            print(f"[active-kw-audit] account {cid} skipped: {e}")
            continue

        # Aggregate metrics per criterion + capture latest QS / IS-lost
        agg: dict[str, dict] = {}
        for r in rows:
            key = r.ad_group_criterion.resource_name
            slot = agg.setdefault(key, {
                "row":           r,
                "cost_micros":   0,
                "conversions":   0.0,
                "qs_seen":       [],
                "is_lost_seen":  [],
            })
            slot["cost_micros"]  += int(r.metrics.cost_micros or 0)
            slot["conversions"]  += float(r.metrics.conversions or 0)
            qs = getattr(r.ad_group_criterion.quality_info, "quality_score", None)
            if qs is not None and qs > 0:
                slot["qs_seen"].append(qs)
            lost = r.metrics.search_rank_lost_impression_share
            if lost is not None and lost >= 0:
                slot["is_lost_seen"].append(lost)

        # Count enabled keywords per ad group — used by zero-keyword guard below
        enabled_kw_per_adgroup: dict[str, int] = defaultdict(int)
        for slot in agg.values():
            ag_rn = slot["row"].ad_group.resource_name
            enabled_kw_per_adgroup[ag_rn] += 1

        for key, slot in agg.items():
            r = slot["row"]
            term = r.ad_group_criterion.keyword.text
            campaign_name = r.campaign.name
            kind = classify_term(term, campaign_name)

            base = {
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
            }

            # Policy-pattern violations
            if kind in ("always_negative", "brand_only_block",
                        "competitor_in_generic", "language_mismatch"):
                violations.append(base)
                continue

            # QS + IS-lost combined check
            qs_seen      = slot["qs_seen"]
            is_lost_seen = slot["is_lost_seen"]
            spend        = slot["cost_micros"] / 1_000_000
            conversions  = slot["conversions"]

            if qs_seen and is_lost_seen:
                latest_qs    = qs_seen[-1]
                max_is_lost  = max(is_lost_seen)
                if latest_qs < LOW_QS and max_is_lost > HIGH_LOST_IS:

                    # Guard 1 — converting keyword exception.
                    # conv > 4 AND $10 ≤ CPA ≤ $70 → keyword is working despite
                    # low QS; pausing it would cut real lead volume.
                    cpa = spend / conversions if conversions > 0 else None
                    if conversions > 4 and cpa is not None and 10 <= cpa <= 70:
                        continue

                    # Guard 2 — zero-active-keyword guard.
                    # Never flag the last enabled keyword in an ad group for
                    # pause/delete — that would leave the group with 0 active
                    # keywords and silently kill the campaign.
                    ag_rn = r.ad_group.resource_name
                    if enabled_kw_per_adgroup.get(ag_rn, 0) <= 1:
                        print(f"[kw-audit] zero-kw guard: skipping sole keyword "
                              f"{term!r!s} in {r.ad_group.name!r!s} "
                              f"(would leave 0 active keywords)")
                        continue

                    base["qs"]          = latest_qs
                    base["is_lost"]     = round(max_is_lost, 2)
                    base["spend"]       = round(spend, 2)
                    base["conversions"] = round(conversions, 1)
                    base["cpa"]         = round(cpa, 2) if cpa is not None else None
                    if spend == 0:
                        base["violation"] = "low_qs_high_lost_is_delete"
                    else:
                        base["violation"] = "low_qs_high_lost_is_pause"
                    violations.append(base)

    # ── Age guard for performance-based actions ──────────────────────────────
    # ALWAYS-NEGATIVE / brand-only / competitor-in-generic / language-mismatch
    # are POLICY violations and bypass the age check. QS + IS-lost are
    # PERFORMANCE actions and must respect MIN_KEYWORD_AGE_DAYS — a 3-day-old
    # keyword hasn't had time to perform.
    perf_kinds = {"low_qs_high_lost_is_delete", "low_qs_high_lost_is_pause"}
    perf_violations = [v for v in violations if v["violation"] in perf_kinds]
    if perf_violations:
        # Look up first-impression dates for these criteria, per account
        from collectors.google_ads import get_client as _get
        client = _get()
        by_cid: dict[str, list[dict]] = {}
        for v in perf_violations:
            by_cid.setdefault(v["customer_id"], []).append(v)
        for cid, vs in by_cid.items():
            firsts = keyword_first_impression_dates(
                client, cid, [v["criterion_resource"] for v in vs]
            )
            for v in vs:
                first = firsts.get(v["criterion_resource"])
                age = days_since(first)
                v["age_days"] = age
                v["first_impression"] = first or ""
                if age < MIN_KEYWORD_AGE_DAYS:
                    v["age_guard_skip"] = True
        # Filter out skipped ones from the actionable list
        skipped = [v for v in perf_violations if v.get("age_guard_skip")]
        if skipped:
            print(f"[age-guard] skipped {len(skipped)} performance violation(s) "
                  f"under {MIN_KEYWORD_AGE_DAYS} days old (will reconsider next week)")
        violations = [v for v in violations if not v.get("age_guard_skip")]

    return violations


def write_csv(violations: list[dict]) -> Path:
    out_dir = Path(__file__).resolve().parent.parent / "logs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"active_keyword_violations_{date.today().isoformat()}.csv"
    if not violations:
        out.write_text("violation,customer_id,campaign,ad_group,keyword,match_type\n",
                       encoding="utf-8")
        return out
    # Union of all keys across violations (rows have variable shape — QS/IS-lost
    # rows have extra columns vs pure pattern violations)
    all_keys: list[str] = []
    seen = set()
    for v in violations:
        for k in v.keys():
            if k not in seen:
                seen.add(k); all_keys.append(k)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        w.writeheader()
        for row in violations:
            # Pad with None for missing keys
            w.writerow({k: row.get(k, "") for k in all_keys})
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
            "low_qs_high_lost_is_delete":
                                    "have QS<5 AND >80% lost impression share (rank) "
                                    "AND zero historical spend — broken keywords that "
                                    "never gained traction. SAFE TO DELETE per the "
                                    "'never delete with cost' rule (zero cost ⇒ ok).",
            "low_qs_high_lost_is_pause":
                                    "have QS<5 AND >80% lost impression share (rank) "
                                    "AND historical spend > $0 — pause (not delete) "
                                    "because we keep history for keywords that ever "
                                    "spent money.",
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
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--silent", action="store_true",
                   help="Skip Asana task creation (used by weekly auto-fix)")
    args = p.parse_args()

    violations = scan_active_keywords()
    csv_path = write_csv(violations)
    print_summary(violations)
    print(f"\nCSV written: {csv_path}")
    if violations and not args.silent:
        create_review_task(violations, csv_path)
    elif not violations:
        print("\nNo policy violations among ENABLED keywords. ✅")
