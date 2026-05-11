"""
analysers/microsoft_ads_audit_tasks.py
=======================================
Turn the daily Microsoft Ads audit into Asana tasks.

Mirrors analysers/google_ads_audit_tasks.py but for Microsoft Ads. All
tasks log under role='performance_audit', channel='microsoft_ads' so the
activity dashboard's `performance_audit` row aggregates both Google + MS.
"""
from __future__ import annotations

from analysers.microsoft_ads_audit import run_full_audit
from analysers.google_ads_audit_tasks import (
    _is_card, _qs_card, _term_card,           # reuse identical formatters
    _is_weekly_keyword_day,
)
from executors.asana import create_task
from logs.activity_logger import log_activity_async


def create_audit_tasks() -> list[tuple[str, str | None]]:
    """Run MS Ads audit + create Asana tasks. Returns [(title, gid)]."""
    audit = run_full_audit()
    out: list[tuple[str, str | None]] = []

    # ── 1. Impression-share ──────────────────────────────────────────────
    is_findings = audit["impression_share"]
    if is_findings:
        scale     = [f for f in is_findings if f["verdict"] == "scale-budget-candidate"]
        rank      = [f for f in is_findings if f["verdict"] == "rank-issue"]
        saturated = [f for f in is_findings if f["verdict"] == "saturated"]

        body = (f"Microsoft Ads impression-share audit (last 14d). "
                f"{len(is_findings)} campaign(s) flagged.\n\n"
                f"**IS = share of auctions your ads actually appeared in (Bing/Yahoo/AOL).**\n"
                f"Lost-Budget = Microsoft stopped showing ads because daily budget ran out.\n"
                f"Lost-Rank = Microsoft ranked the ad too low to show (QS × bid insufficient).\n\n")
        if scale:
            body += f"### 📉 Lost to BUDGET — {len(scale)} campaign(s)\n\n" + _is_card(scale) + "\n"
        if rank:
            body += f"### 🎯 Lost to RANK — {len(rank)} campaign(s)\n\n"  + _is_card(rank)  + "\n"
        if saturated:
            body += f"### 🛑 SATURATED (>80% IS) — {len(saturated)} campaign(s)\n\n" + _is_card(saturated) + "\n"

        gid = create_task(
            title=f"Microsoft Ads — Impression-share audit ({len(is_findings)} campaigns)",
            description=body,
            project_key="optimization",
            task_type="Recommendation",
            channel="microsoft_ads",
            asset_level="campaign",
            action="optimize",
        )
        out.append((f"MS IS audit ({len(is_findings)})", gid))

    # ── 2. Quality Score ────────────────────────────────────────────────
    qs_findings = audit["quality_score"]
    if qs_findings:
        urgent = [f for f in qs_findings if f["urgency"] == "URGENT"]
        review = [f for f in qs_findings if f["urgency"] == "review"]

        body = (f"Microsoft Ads Quality Score audit (last 14d). {len(qs_findings)} keyword(s) "
                f"with QS < 5 and $70+ spend.\n\n"
                f"**Why this matters:** Low QS means higher CPC and lower IS on Bing.\n\n")
        if urgent:
            body += f"### Urgent (QS < 4) — {len(urgent)} keyword(s)\n\n" + _qs_card(urgent[:30]) + "\n"
        if review:
            body += f"### Review (QS < 5) — {len(review)} keyword(s)\n\n" + _qs_card(review[:30]) + "\n"

        gid = create_task(
            title=f"Microsoft Ads — Low Quality Score keywords ({len(qs_findings)})",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="microsoft_ads",
            asset_level="keyword",
            action="optimize",
        )
        out.append((f"MS QS audit ({len(qs_findings)})", gid))

    # ── 3. Keyword expansion (weekly only) ──────────────────────────────
    add_kw      = audit["keyword_expansion"]["add_as_keyword"]
    add_neg     = audit["keyword_expansion"]["add_as_negative"]
    auto_neg    = audit["keyword_expansion"].get("auto_negative", [])
    pause_watch = audit["keyword_expansion"].get("pause_watch", [])

    if add_kw and _is_weekly_keyword_day():
        body = (f"Microsoft Ads search-terms audit (last 30d). {len(add_kw)} "
                f"converting queries are NOT yet in our keyword list.\n\n"
                f"**Cadence:** Weekly (Sunday Riyadh).\n"
                f"**Action:** Review, then run `python scripts/bulk_keywords.py "
                f"add --channel microsoft_ads`.\n\n"
                + _term_card(add_kw[:30], mode="add"))
        gid = create_task(
            title=f"Microsoft Ads — {len(add_kw)} new keyword candidates (weekly)",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="microsoft_ads",
            asset_level="keyword",
            action="launch",
        )
        out.append((f"MS keyword expansion ({len(add_kw)})", gid))
        log_activity_async(
            role="keyword_management", action="positive_keywords_added",
            channel="microsoft_ads", rows_affected=len(add_kw),
            details={"keywords": [k["keyword"] for k in add_kw[:50]]},
        )

    # 4. Wasted-spend search terms → pause matched keywords (not negate)
    if add_neg:
        body = (f"{len(add_neg)} Microsoft Ads search terms spent $25+ each with 0 conversions.\n\n"
                f"**Action:** Review and pause the keywords matching these queries.\n"
                f"**How:** Run `python scripts/bulk_keywords.py audit --channel microsoft_ads`.\n\n"
                f"These terms are NOT added as negatives — they may be triggered by a "
                f"broad keyword that needs pausing, not the query itself.\n\n"
                + _term_card(add_neg[:50], mode="negative"))
        gid = create_task(
            title=f"Microsoft Ads — Review {len(add_neg)} wasted-spend queries → pause matched keywords",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="microsoft_ads",
            asset_level="keyword",
            action="pause",
        )
        out.append((f"MS wasted queries ({len(add_neg)})", gid))

    # 4b. Auto-negative direct-executed (always-negative policy matches)
    if auto_neg:
        body = (f"{len(auto_neg)} Microsoft Ads terms match permanent always-negative "
                f"rules (login / free / دورة / تحميل / قرض / تمويل / وظيفة).\n\n"
                f"**EXECUTED AUTOMATICALLY** — no approval needed.\n\n"
                + _term_card(auto_neg[:50], mode="negative"))
        gid = create_task(
            title=f"Microsoft Ads — Auto-excluded {len(auto_neg)} always-negative terms",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="microsoft_ads",
            asset_level="keyword",
            action="exclude",
        )
        out.append((f"MS auto-neg ({len(auto_neg)})", gid))

    # 4c. Pause-watch — قيود/competitors/lang-mismatch (manual review only)
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
                f"**Reason:**      {r.get('policy_reason', r.get('policy_kind', ''))}\n"
                f"**Rule:**        Review — do NOT add as negative"
            )
        body = (f"{len(pause_watch)} Microsoft Ads terms need human review:\n"
                f"• قيود / Qoyod variants in non-brand campaigns\n"
                f"• Competitor brand names outside Competitor campaigns\n"
                f"• Language mismatches (AR↔EN)\n\n"
                + "\n\n---\n\n".join(pw_cards) + "\n")
        gid = create_task(
            title=f"Microsoft Ads — {len(pause_watch)} pause-watch terms",
            description=body,
            project_key="daily_activity",
            task_type="Keyword",
            channel="microsoft_ads",
            asset_level="keyword",
            action="pause",
        )
        out.append((f"MS pause-watch ({len(pause_watch)})", gid))

    # Wasted-spend negatives (add_neg) require human review — Asana task
    # already created above. Only always-negative policy matches auto-execute.
    if auto_neg:
        try:
            from executors.keyword_approval import _execute_negatives
            _execute_negatives(auto_neg)
        except Exception as e:
            print(f"[ms-audit-tasks] auto-neg execution failed (non-fatal): {e}")

    log_activity_async(role="performance_audit", action="create_audit_tasks",
                       status="success", channel="microsoft_ads",
                       rows_affected=len(out),
                       details={"is": len(is_findings), "qs": len(qs_findings),
                                "add_kw": len(add_kw), "add_neg": len(add_neg),
                                "auto_neg": len(auto_neg),
                                "pause_watch": len(pause_watch)})
    return out
