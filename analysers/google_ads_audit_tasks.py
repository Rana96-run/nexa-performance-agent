"""
analysers/google_ads_audit_tasks.py
====================================
Turn the daily Google Ads audit into Asana tasks.

Called from operational_scheduler nightly cadence after run_full_audit().

Task design (always consolidated, never one task per row):
  - 1 task per channel × asset_level summarising all findings
  - Each task body lists every finding with the data
  - Direct-execute candidates flagged so the user can approve in bulk
"""
from __future__ import annotations

from analysers.google_ads_audit import run_full_audit
from executors.asana import create_task


def _is_table(findings: list[dict]) -> str:
    if not findings:
        return ""
    body = "| Spend | IS | Lost-Budget | Lost-Rank | Verdict | Campaign |\n"
    body += "|---|---|---|---|---|---|\n"
    for f in findings:
        body += (f"| ${f['spend']:.0f} | {f['is_share']*100:.0f}% | "
                 f"{f['is_lost_budget']*100:.0f}% | {f['is_lost_rank']*100:.0f}% | "
                 f"**{f['verdict']}** | {f['campaign']} |\n")
    return body


def _qs_table(findings: list[dict]) -> str:
    if not findings:
        return ""
    body = "| QS | Spend | Ad-Relevance | LP-Experience | Expected-CTR | Keyword | Campaign |\n"
    body += "|---|---|---|---|---|---|---|\n"
    for f in findings:
        body += (f"| **{f['quality_score']}** | ${f['spend']:.0f} | "
                 f"{f['ad_relevance']} | {f['landing_page_experience']} | "
                 f"{f['expected_ctr']} | `{f['keyword']}` | {f['campaign']} |\n")
    return body


def _term_table(rows: list[dict], mode: str) -> str:
    if not rows:
        return ""
    if mode == "add":
        body = "| Conv | Spend | CPA | Search Term | Match Suggestion | Campaign |\n"
        body += "|---|---|---|---|---|---|\n"
        for r in rows:
            cpa = f"${r['cpa']:.0f}" if r.get("cpa") else "—"
            body += (f"| {r['conv']:.1f} | ${r['spend']:.0f} | {cpa} | "
                     f"`{r['term']}` | EXACT or PHRASE | {r['campaign']} |\n")
    else:
        body = "| Spend | Clicks | Search Term | Recommended Match | Campaign |\n"
        body += "|---|---|---|---|---|\n"
        for r in rows:
            body += (f"| ${r['spend']:.0f} | {r['clicks']} | `{r['term']}` | "
                     f"NEGATIVE EXACT | {r['campaign']} |\n")
    return body


def create_audit_tasks() -> list[tuple[str, str | None]]:
    """Run audit and create consolidated Asana tasks. Returns [(title, gid)]."""
    audit = run_full_audit()
    out: list[tuple[str, str | None]] = []

    # ── 1. Impression-share recommendations ─────────────────────────────────
    is_findings = audit["impression_share"]
    if is_findings:
        scale     = [f for f in is_findings if f["verdict"] == "scale-budget-candidate"]
        rank      = [f for f in is_findings if f["verdict"] == "rank-issue"]
        saturated = [f for f in is_findings if f["verdict"] == "saturated"]

        body = (f"Daily impression-share audit (last 14d). "
                f"{len(is_findings)} campaigns flagged.\n\n"
                f"**Rules:**\n"
                f"- Lost-IS to BUDGET > 20% → scale candidate (raise budget)\n"
                f"- Lost-IS to RANK > 30% → quality / bid issue (improve QS or raise bid)\n"
                f"- IS > 80% → saturated (broaden keywords / new ad groups)\n\n")
        if scale:
            body += f"### Scale candidates ({len(scale)})\n" + _is_table(scale) + "\n"
        if rank:
            body += f"### Rank issues ({len(rank)})\n" + _is_table(rank) + "\n"
        if saturated:
            body += f"### Saturated ({len(saturated)})\n" + _is_table(saturated) + "\n"
        body += ("\n**Action:** Budget changes are approval-gated. Open the channel "
                 "optimization board, review, and approve the bid/budget mutations "
                 "in the Slack approval channel.")

        gid = create_task(
            title=f"Google Ads — Impression-share audit ({len(is_findings)} campaigns)",
            description=body,
            project_key="optimization",
            task_type="Recommendation",
            channel="google_ads",
            asset_level="campaign",
            action="optimize",
        )
        out.append((f"IS audit ({len(is_findings)})", gid))

    # ── 2. Quality-score recommendations ────────────────────────────────────
    qs_findings = audit["quality_score"]
    if qs_findings:
        urgent = [f for f in qs_findings if f["urgency"] == "URGENT"]
        review = [f for f in qs_findings if f["urgency"] == "review"]

        body = (f"Daily Quality Score audit (last 14d). {len(qs_findings)} keywords "
                f"with QS < 5 and $50+ spend.\n\n"
                f"**Why this matters:** Low QS means higher CPC and lower IS. "
                f"Improving QS reduces cost AND wins more impressions.\n\n")
        if urgent:
            body += f"### Urgent (QS < 4) — {len(urgent)} keywords\n" + _qs_table(urgent[:30]) + "\n"
        if review:
            body += f"### Review (QS < 5) — {len(review)} keywords\n" + _qs_table(review[:30]) + "\n"

        body += ("\n**How to improve QS:**\n"
                 "1. **Ad relevance** below average → ad copy doesn't match the "
                 "keyword's intent. Rewrite ad headlines to include the keyword.\n"
                 "2. **Landing page experience** below average → LP doesn't deliver "
                 "what the ad promises. Either tighten LP copy or move keyword to "
                 "a more relevant ad group.\n"
                 "3. **Expected CTR** below average → ad is not compelling. Try "
                 "stronger CTAs / new headline tests.")

        gid = create_task(
            title=f"Google Ads — Low Quality Score keywords ({len(qs_findings)})",
            description=body,
            project_key="optimization",
            task_type="Recommendation",
            channel="google_ads",
            asset_level="keyword",
            action="optimize",
        )
        out.append((f"QS audit ({len(qs_findings)})", gid))

    # ── 3. Keyword expansion (add as keyword) ──────────────────────────────
    add_kw = audit["keyword_expansion"]["add_as_keyword"]
    if add_kw:
        body = (f"Daily search-terms audit (last 30d). {len(add_kw)} converting "
                f"queries are NOT yet in our keyword list.\n\n"
                f"**Rule:** Queries with ≥1 conversion that triggered our ads but "
                f"aren't a keyword we bid on → add as EXACT or PHRASE match.\n\n"
                + _term_table(add_kw[:30], mode="add"))
        body += ("\n**Action:** Approve the additions and the Media Buyer will "
                 "create the keyword in the relevant ad group. (Adding new positive "
                 "keywords is approval-gated; only NEGATIVE adds are direct-execute.)")

        gid = create_task(
            title=f"Google Ads — {len(add_kw)} new keyword candidates from search terms",
            description=body,
            project_key="optimization",
            task_type="Recommendation",
            channel="google_ads",
            asset_level="keyword",
            action="launch",
        )
        out.append((f"keyword expansion ({len(add_kw)})", gid))

    # ── 4. Negative-keyword candidates ─────────────────────────────────────
    add_neg = audit["keyword_expansion"]["add_as_negative"]
    if add_neg:
        body = (f"{len(add_neg)} search terms wasted $25+ each with 0 conversions "
                f"and aren't yet excluded.\n\n"
                f"**Rule:** Negative-keyword adds for clearly irrelevant queries are "
                f"DIRECT-EXECUTE (no approval needed) per the Media Buyer playbook.\n\n"
                + _term_table(add_neg[:50], mode="negative"))
        body += ("\n**Action:** The agent will add these as negatives on the next "
                 "nightly run once the executor lands. For now: review and approve "
                 "in bulk, or add manually via Google Ads UI.")

        gid = create_task(
            title=f"Google Ads — Add {len(add_neg)} negative keywords (waste)",
            description=body,
            project_key="optimization",
            task_type="Direct Log",
            channel="google_ads",
            asset_level="keyword",
            action="exclude",
        )
        out.append((f"negatives ({len(add_neg)})", gid))

    return out


if __name__ == "__main__":
    created = create_audit_tasks()
    print()
    print(f"Created {len(created)} audit task(s):")
    for label, gid in created:
        print(f"  ✓ gid={gid}  {label}")
