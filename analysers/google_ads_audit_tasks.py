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

from datetime import datetime, timezone, timedelta

from analysers.google_ads_audit import run_full_audit
from executors.asana import create_task
from logs.activity_logger import log_activity_async


# ── Weekly cadence ────────────────────────────────────────────────────────────
# Adding new keywords and pausing keywords run WEEKLY (not nightly). Negatives
# direct-execute daily, QS / IS audits surface daily, but "add as keyword" and
# "pause keyword" actions only fire on Sunday Riyadh time — first day of the
# Saudi work week, so the team sees the proposal list at Sunday standup.
_RIYADH = timezone(timedelta(hours=3))
WEEKLY_KEYWORD_WEEKDAY = 6   # Python: Monday=0 … Sunday=6


def _is_weekly_keyword_day() -> bool:
    """True if today (Riyadh time) is the weekly keyword-action day."""
    import os
    if os.getenv("FORCE_WEEKLY_KEYWORDS", "").lower() in ("1", "true", "yes"):
        return True
    return datetime.now(_RIYADH).weekday() == WEEKLY_KEYWORD_WEEKDAY


def _is_card(findings: list[dict]) -> str:
    if not findings:
        return ""
    cards = []
    for i, f in enumerate(findings, 1):
        header = f"**[{i}/{len(findings)}]**\n" if len(findings) > 1 else ""
        cards.append(
            f"{header}"
            f"**Campaign:**      {f['campaign']}\n"
            f"**Spend:**         ${f['spend']:.0f}\n"
            f"**IS:**            {f['is_share']*100:.0f}%\n"
            f"**Lost (Budget):** {f['is_lost_budget']*100:.0f}%\n"
            f"**Lost (Rank):**   {f['is_lost_rank']*100:.0f}%\n"
            f"**Verdict:**       {f['verdict']}"
        )
    return "\n\n---\n\n".join(cards) + "\n"


def _qs_card(findings: list[dict]) -> str:
    if not findings:
        return ""
    cards = []
    for i, f in enumerate(findings, 1):
        header = f"**[{i}/{len(findings)}]**\n" if len(findings) > 1 else ""
        cards.append(
            f"{header}"
            f"**Keyword:**       {f['keyword']}\n"
            f"**Campaign:**      {f['campaign']}\n"
            f"**Quality Score:** {f['quality_score']}/10\n"
            f"**Spend:**         ${f['spend']:.0f}\n"
            f"**Ad Relevance:**  {f['ad_relevance']}\n"
            f"**LP Experience:** {f['landing_page_experience']}\n"
            f"**Expected CTR:**  {f['expected_ctr']}"
        )
    return "\n\n---\n\n".join(cards) + "\n"


def _term_card(rows: list[dict], mode: str) -> str:
    if not rows:
        return ""
    cards = []
    for i, r in enumerate(rows, 1):
        header = f"**[{i}/{len(rows)}]**\n" if len(rows) > 1 else ""
        if mode == "add":
            cpa = f"${r['cpa']:.0f}" if r.get("cpa") else "—"
            cards.append(
                f"{header}"
                f"**Search Term:**      {r['term']}\n"
                f"**Campaign:**         {r['campaign']}\n"
                f"**Conversions:**      {r['conv']:.1f}\n"
                f"**Spend:**            ${r['spend']:.0f}\n"
                f"**CPA:**              {cpa}\n"
                f"**Match Suggestion:** EXACT or PHRASE"
            )
        else:
            cards.append(
                f"{header}"
                f"**Search Term:**      {r['term']}\n"
                f"**Campaign:**         {r['campaign']}\n"
                f"**Spend:**            ${r['spend']:.0f}\n"
                f"**Clicks:**           {r['clicks']}\n"
                f"**Action:**           Add as NEGATIVE EXACT"
            )
    return "\n\n---\n\n".join(cards) + "\n"


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
            body += f"### 📉 Lost to BUDGET — {len(scale)} campaign(s)\n\n"
            body += _is_card(scale) + "\n"
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
            body += f"### 🎯 Lost to RANK — {len(rank)} campaign(s)\n\n"
            body += _is_card(rank) + "\n"
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
            body += f"### ✅ Saturated (IS > 80%) — {len(saturated)} campaign(s)\n\n"
            body += _is_card(saturated) + "\n"
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
                f"with QS < 5 and $70+ spend.\n\n"
                f"**Why this matters:** Low QS means higher CPC and lower IS. "
                f"Improving QS reduces cost AND wins more impressions.\n\n")
        if urgent:
            body += f"### Urgent (QS < 4) — {len(urgent)} keywords\n\n" + _qs_card(urgent[:30]) + "\n"
        if review:
            body += f"### Review (QS < 5) — {len(review)} keywords\n\n" + _qs_card(review[:30]) + "\n"

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
            project_key="daily_activity",
            task_type="Keyword",
            channel="google_ads",
            asset_level="keyword",
            action="optimize",
        )
        out.append((f"QS audit ({len(qs_findings)})", gid))

    # ── 3. Keyword expansion (add as keyword) — Keyword & Placement Audit project
    add_kw      = audit["keyword_expansion"]["add_as_keyword"]
    add_neg     = audit["keyword_expansion"]["add_as_negative"]
    auto_neg    = audit["keyword_expansion"].get("auto_negative", [])
    pause_watch = audit["keyword_expansion"].get("pause_watch", [])

    # KEYWORD EXPANSION runs WEEKLY (Sunday Riyadh) — not nightly. The audit
    # still computes candidates daily so we know the latest state, but the
    # Asana task only fires once per week to cut review noise + force a
    # batched, considered review.
    if add_kw and _is_weekly_keyword_day():
        # Apply the 30-keyword-per-ad-group cap (rule from 2026-05-06): keep
        # add candidates only up to (30 - existing_count) per destination ad
        # group. Drop the rest with a note in the task body.
        from analysers.google_ads_audit import filter_kw_against_adgroup_cap
        capped, dropped = filter_kw_against_adgroup_cap(add_kw, max_per_adgroup=30)

        cap_note = ""
        if dropped:
            cap_note = (f"\n**30-keyword cap applied:** {len(dropped)} candidate(s) "
                        f"dropped because their target ad group already has 30+ keywords. "
                        f"To add them, first prune low performers in those ad groups.\n")

        body = (f"Search-terms audit (last 30d). {len(capped)} converting queries "
                f"are NOT yet in our keyword list (was {len(add_kw)} before "
                f"30-per-adgroup cap).\n\n"
                f"**Rule:** Queries with ≥1 conversion that triggered our ads but "
                f"aren't a keyword we bid on → add as EXACT match.\n"
                f"**Cadence:** Keyword expansion runs WEEKLY on Sunday Riyadh.\n"
                f"**Cap:** No ad group may exceed 30 keywords — candidates beyond "
                f"that are dropped (see note below if any).\n\n"
                f"**Action:** Review, then run `python scripts/bulk_keywords.py "
                f"add` to execute. قيود/Qoyod in non-brand, competitors in non-"
                f"competitor campaigns, and language-mismatched terms were "
                f"already filtered out (see Pause Watch task).\n"
                + cap_note
                + "\n" + _term_card(capped[:30], mode="add"))

        gid = create_task(
            title=f"Google Ads — {len(capped)} new keyword candidates (weekly)",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="google_ads",
            asset_level="keyword",
            action="launch",
        )
        out.append((f"keyword expansion ({len(capped)})", gid))
        # Log keywords so the dashboard can show individual terms
        log_activity_async(
            role="keyword_management", action="positive_keywords_added",
            channel="google_ads", rows_affected=len(capped),
            details={"keywords": [k["keyword"] for k in capped[:50]]},
        )
    elif add_kw:
        # Off-day — log only, don't create the task.
        log_activity_async(
            role="keyword_management",
            action="keyword_candidates_queued_for_weekly_review",
            channel="google_ads", status="ok", rows_affected=len(add_kw),
            details={"candidate_count": len(add_kw), "keywords": [k["keyword"] for k in add_kw[:50]],
                     "next_review_day": "Sunday Riyadh"},
        )

    # ── 4. Wasted-spend search terms — handled by keyword pause audit ──────────
    # Non-converting keywords are paused by audit_and_pause_nonconverting_keywords()
    # after 10 days (MIN_KEYWORD_AGE_DAYS). No separate task needed here.
    if add_neg:
        print(f"[audit-tasks] {len(add_neg)} wasted-spend search terms — keyword audit will handle")

    # ── 4b. Always-negative auto-executed (silent log) ────────────────────────
    if auto_neg:
        body = (f"{len(auto_neg)} terms match permanent always-negative rules:\n"
                f"• login / sign in / تسجيل الدخول\n"
                f"• free / مجاني / مجانية\n"
                f"• course / دورة / دورات / كورس\n"
                f"• download / تحميل / تنزيل\n"
                f"• loan / قرض / قروض / تمويل\n"
                f"• job / وظيفة / وظائف / فرص عمل\n\n"
                f"**EXECUTED AUTOMATICALLY** — no approval needed, never shown as expansion candidates.\n\n"
                + _term_card(auto_neg[:50], mode="negative"))

        gid = create_task(
            title=f"Google Ads — Auto-excluded {len(auto_neg)} always-negative terms",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="google_ads",
            asset_level="keyword",
            action="exclude",
        )
        out.append((f"auto-neg ({len(auto_neg)})", gid))

    # ── 4c. Pause-watch: قيود + competitors — NEVER negative, pause if needed ─
    if pause_watch:
        pw_cards = []
        for i, r in enumerate(pause_watch, 1):
            header = f"**[{i}/{len(pause_watch)}]**\n" if len(pause_watch) > 1 else ""
            pw_cards.append(
                f"{header}"
                f"**Search Term:** {r['term']}\n"
                f"**Campaign:**    {r['campaign']}\n"
                f"**Spend:**       ${r['spend']:.0f}\n"
                f"**Clicks:**      {r['clicks']}\n"
                f"**Rule:**        PAUSE if not converting — do NOT add as negative"
            )
        body = (f"{len(pause_watch)} terms need human review (NEVER added as negatives):\n"
                f"• قيود / Qoyod variants in non-brand campaigns (brand-only rule — these "
                f"belong in a Brand campaign or shouldn't be bid on at all)\n"
                f"• Competitor brand names (zoho, quickbooks, etc. — pause if not "
                f"converting after 14 days; never exclude)\n\n"
                + "\n\n---\n\n".join(pw_cards) + "\n")

        gid = create_task(
            title=f"Google Ads — {len(pause_watch)} pause-watch terms (قيود / competitors)",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="google_ads",
            asset_level="keyword",
            action="pause",
        )
        out.append((f"pause-watch ({len(pause_watch)})", gid))

    # Wasted-spend negatives (add_neg) require human review — Asana task
    # already created above. Never auto-execute; only always-negative policy
    # matches (auto_neg) are safe to execute without approval.

    if auto_neg:
        try:
            from executors.keyword_approval import _execute_negatives
            _execute_negatives(auto_neg)
            print(f"[audit-tasks] auto-neg: {len(auto_neg)} always-negative terms executed")
        except Exception as e:
            print(f"[audit-tasks] auto-neg execution failed (non-fatal): {e}")

    # ── 5. Non-converting keywords auto-paused ──────────────────────────────
    kw_paused = audit.get("keywords_paused", [])
    if kw_paused:
        kw_cards = []
        for i, kw in enumerate(kw_paused, 1):
            header = f"**[{i}/{len(kw_paused)}]**\n" if len(kw_paused) > 1 else ""
            kw_cards.append(
                f"{header}"
                f"**Keyword:**    {kw['keyword']}\n"
                f"**Match Type:** {kw['match_type']}\n"
                f"**Campaign:**   {kw['campaign']}\n"
                f"**Ad Group:**   {kw['ad_group']}\n"
                f"**Spend:**      ${kw['spend']:.2f}\n"
                f"**Status:**     {kw['status']}"
            )
        body = (f"**EXECUTED:** {len(kw_paused)} keywords auto-paused (7+ days, $4+ spend, 0 leads).\n\n"
                + "\n\n---\n\n".join(kw_cards) + "\n")
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

    log_activity_async(role="performance_audit", action="create_audit_tasks",
                       status="success", channel="google_ads",
                       rows_affected=len(out),
                       details={"tasks": [t[0] for t in out]})
    return out


if __name__ == "__main__":
    created = create_audit_tasks()
    print()
    print(f"Created {len(created)} audit task(s):")
    for label, gid in created:
        print(f"  ✓ gid={gid}  {label}")
