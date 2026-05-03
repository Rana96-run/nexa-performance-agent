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
                f"**IS = share of auctions your ads actually appeared in.**\n"
                f"Lost-Budget = Google stopped showing ads because daily budget ran out.\n"
                f"Lost-Rank = Google ranked your ad too low to show (QS × bid insufficient).\n\n")

        if scale:
            body += f"### 📉 Lost to BUDGET — {len(scale)} campaign(s)\n"
            body += _is_table(scale) + "\n"
            body += (
                "**Root causes to investigate before touching budget:**\n"
                "1. **Dayparting drain** — Run an hourly impression report. "
                "If budget is exhausted by noon, split into two budget cycles or use "
                "shared budget + ad scheduling to concentrate spend in peak-conversion hours.\n"
                "2. **Match-type waste** — If Broad or BMM keywords are present, check "
                "the search terms report. If > 30% of spend goes to irrelevant queries, "
                "add negatives first — this frees budget for winning auctions.\n"
                "3. **Bid strategy conflict** — If on Target CPA with a very low target, "
                "Google caps bids to meet the target, exhausting budget in low-competition "
                "slots before peak hours. Try raising target CPA by 15% and re-evaluate.\n"
                "4. **ROAS/CPL validation before scaling** — Only raise budget if this "
                "campaign has CPQL ≤ account target (check Asana KPI board). "
                "If CPQL is above target, scaling wastes money — fix lead quality first.\n"
                "5. **Impression Share bid strategy** — For campaigns with strong CPLs, "
                "switch to Target Impression Share (Absolute Top 50–70%) to let Google "
                "auto-bid for visibility without manual budget guessing.\n\n"
            )

        if rank:
            body += f"### 🎯 Lost to RANK — {len(rank)} campaign(s)\n"
            body += _is_table(rank) + "\n"
            body += (
                "**Lost-Rank is a Quality Score problem, not a budget problem.**\n"
                "Raising bid helps short-term but costs more — fix QS first:\n"
                "1. **Ad relevance below average** → Headlines don't match the keyword's "
                "intent. Add the exact keyword into H1/H2 of the ad. Create tighter ad "
                "groups (1-3 keywords per group — SKAGs) so every ad is hyper-relevant.\n"
                "2. **Landing page experience below average** → LP doesn't deliver what "
                "the ad promises. Check: does the LP headline match the ad CTA? "
                "Is the form above the fold on mobile? Page load > 3s kills LP score — "
                "run PageSpeed Insights and fix the top 3 issues.\n"
                "3. **Expected CTR below average** → Ad copy isn't compelling. "
                "Actions: add a number ('Get a quote in 2 minutes'), urgency "
                "('Limited offer — expires this week'), or social proof "
                "('Trusted by 10,000+ businesses'). Test RSA with pinned H1.\n"
                "4. **Ad extensions gap** — Missing extensions reduce predicted CTR. "
                "Ensure all campaigns have: Sitelinks (≥4), Callouts (≥4), "
                "Structured Snippets, and a Call extension if applicable.\n"
                "5. **Bid floor** — After QS fixes, if rank IS is still low after 7d, "
                "raise CPC bids by 20% on the specific ad groups with rank issues only.\n\n"
            )

        if saturated:
            body += f"### ✅ Saturated (IS > 80%) — {len(saturated)} campaign(s)\n"
            body += _is_table(saturated) + "\n"
            body += (
                "**Campaign is winning most auctions it's eligible for — expand the pool:**\n"
                "1. Add new keyword themes from the search terms report (converting queries "
                "not yet in the keyword list → add as exact match).\n"
                "2. Duplicate the ad group and test Phrase match on top performers.\n"
                "3. Add RLSA bid adjustments to increase bids for website visitors.\n"
                "4. Test new geographic areas if the product has national reach.\n\n"
            )

        body += ("**Approval:** Budget/bid changes are routed to #approvals. "
                 "QS / ad copy / LP fixes can be executed directly without approval.")

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
                 "1. **Ad relevance** below average -> ad copy doesn't match the "
                 "keyword's intent. Rewrite ad headlines to include the keyword.\n"
                 "2. **Landing page experience** below average -> LP doesn't deliver "
                 "what the ad promises. Either tighten LP copy or move keyword to "
                 "a more relevant ad group.\n"
                 "3. **Expected CTR** below average -> ad is not compelling. Try "
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
    add_kw  = audit["keyword_expansion"]["add_as_keyword"]
    add_neg = audit["keyword_expansion"]["add_as_negative"]

    if add_kw:
        body = (f"Daily search-terms audit (last 30d). {len(add_kw)} converting "
                f"queries are NOT yet in our keyword list.\n\n"
                f"**Rule:** Queries with >=1 conversion that triggered our ads but "
                f"aren't a keyword we bid on -> add as EXACT match.\n\n"
                + _term_table(add_kw[:30], mode="add"))
        body += ("\n**Action:** Slack approval request posted to #approvals. "
                 "React ✅ to execute all additions or ❌ to skip. "
                 "Negatives execute automatically (direct-execute).")

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

    # Post Slack approval for keyword candidates (+ direct-execute negatives)
    if add_kw or add_neg:
        try:
            from executors.keyword_approval import post_keyword_approval
            post_keyword_approval(add_kw=add_kw, add_neg=add_neg)
        except Exception as e:
            print(f"[audit-tasks] keyword approval post failed (non-fatal): {e}")

    # ── 4. Negative-keyword candidates ─────────────────────────────────────
    if add_neg:
        body = (f"{len(add_neg)} search terms wasted $25+ each with 0 conversions "
                f"and aren't yet excluded.\n\n"
                f"**Rule:** Negative-keyword adds for clearly irrelevant queries are "
                f"DIRECT-EXECUTE (no approval needed) per the Media Buyer playbook.\n\n"
                + _term_table(add_neg[:50], mode="negative"))
        body += ("\n**EXECUTED:** These are being added automatically as EXACT negatives "
                 "at campaign level via `executors/keyword_approval.py`. "
                 "No manual action needed — verify in Google Ads UI.")

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

    # ── 5. Non-converting keywords auto-paused ──────────────────────────────
    kw_paused = audit.get("keywords_paused", [])
    if kw_paused:
        body = (f"**EXECUTED:** {len(kw_paused)} keywords auto-paused (7+ days, $4+ spend, 0 leads).\n\n"
                f"| Keyword | Match | Campaign | Ad Group | Spend | Status |\n"
                f"|---|---|---|---|---|---|\n")
        for kw in kw_paused:
            body += (f"| `{kw['keyword']}` | {kw['match_type']} | {kw['campaign']} | "
                     f"{kw['ad_group']} | ${kw['spend']:.2f} | {kw['status']} |\n")
        body += ("\n**Rule:** Keywords running 7+ days with spend > $4 and 0 HubSpot-qualified "
                 "leads are paused automatically. Re-enable only after fixing match type or "
                 "moving keyword to a more relevant ad group.")

        gid = create_task(
            title=f"EXECUTED: Auto-paused {len(kw_paused)} non-converting keyword(s) (7d, $4+)",
            description=body,
            project_key="optimization",
            task_type="Direct Log",
            channel="google_ads",
            asset_level="keyword",
            action="pause",
        )
        out.append((f"kw-auto-paused ({len(kw_paused)})", gid))

    return out


if __name__ == "__main__":
    created = create_audit_tasks()
    print()
    print(f"Created {len(created)} audit task(s):")
    for label, gid in created:
        print(f"  ✓ gid={gid}  {label}")
