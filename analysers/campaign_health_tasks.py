"""
analysers/campaign_health_tasks.py
====================================
Turn campaign health findings into Asana tasks and EXECUTE direct actions.

Action policy (no approval gate — force-execute per playbook):
  - scale     -> budget +25% executed immediately, Asana task logged
  - pause     -> campaign paused immediately (CPQL > 3x warning), Asana task logged
  - optimize  -> Asana task for team investigation (no execution)
  - monitor   -> no task

Junk-leads alert: CPL in scale zone but CPQL in pause/warning + qual < 30%
  -> flag in task, do NOT scale, investigate attribution and audience quality.

Keyword auto-pause: keywords running 7+ days with 0 converted leads -> pause.
"""
from __future__ import annotations

from datetime import date, timedelta

from analysers.campaign_health import audit_campaign_health
from analysers.creative_performance import (
    audit_creative_performance, format_creative_section,
    audit_creative_by_campaign_type, format_creative_by_type_section,
)
from executors.asana import create_task
from config import DAYS_FOR_PAUSE_DECISION, DRILL_DOWN_CPQL, DRILL_DOWN_CPL
from collectors.bq_writer import get_client, PROJECT_ID, DATASET
from logs.activity_logger import log_activity_async

SCALE_PCT = 0.25   # always 25%


def _get_junk_keyword_detail(channel: str, campaign_name: str, days: int) -> str:
    """
    Return a formatted card block showing keyword breakdown for a junk-leads campaign.
    Flags keywords with qual% < 20% as candidates to pause.
    """
    try:
        client = get_client()
        safe_campaign = campaign_name.replace("'", "''")
        sql = f"""
            SELECT
              utm_term        AS keyword,
              utm_audience    AS ad_group,
              ROUND(SUM(spend), 2)                                                 AS spend,
              SUM(leads)                                                           AS leads,
              SUM(leads_qualified)                                                 AS sqls,
              ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1) AS qual_pct
            FROM `{PROJECT_ID}.{DATASET}.v_keyword_performance`
            WHERE channel = '{channel}'
              AND utm_campaign = '{safe_campaign}'
              AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
              AND utm_term IS NOT NULL AND utm_term != ''
            GROUP BY 1, 2
            ORDER BY spend DESC
            LIMIT 20
        """
        rows = list(client.query(sql).result())
        if not rows:
            return ""
        lines = ["Keyword Breakdown (junk source):\n"]
        for r in rows:
            qual  = r.qual_pct if r.qual_pct is not None else 0.0
            flag  = "[PAUSE CANDIDATE]" if qual < 20 else ""
            lines.append(
                f"- `{r.keyword}` | Ad Group: {r.ad_group or '—'} | "
                f"Spend: ${r.spend:.0f} | Leads: {r.leads} | SQLs: {r.sqls} | "
                f"Qual: {qual:.0f}% {flag}"
            )
        return "\n".join(lines) + "\n"
    except Exception as e:
        print(f"[health-tasks] keyword detail error: {e}")
        return ""


def _get_junk_audience_detail(channel: str, campaign_name: str, days: int) -> str:
    """
    Return a formatted card block showing ad-group/ad-set breakdown for a junk-leads campaign.
    Flags the worst audience and suggests a replacement.
    """
    try:
        client = get_client()
        safe_campaign = campaign_name.replace("'", "''")
        sql = f"""
            SELECT
              utm_audience AS ad_group,
              ROUND(SUM(spend), 2)                                                 AS spend,
              SUM(leads)                                                           AS leads,
              SUM(leads_qualified)                                                 AS sqls,
              ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1) AS qual_pct
            FROM `{PROJECT_ID}.{DATASET}.v_adset_performance`
            WHERE channel = '{channel}'
              AND utm_campaign = '{safe_campaign}'
              AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
              AND utm_audience IS NOT NULL AND utm_audience != ''
            GROUP BY 1
            ORDER BY qual_pct ASC
            LIMIT 10
        """
        rows = list(client.query(sql).result())
        if not rows:
            return ""

        lines = ["Audience / Ad-Group Breakdown:\n"]
        for i, r in enumerate(rows):
            qual = r.qual_pct if r.qual_pct is not None else 0.0
            worst_flag = " [WORST]" if i == 0 else ""
            lines.append(
                f"- `{r.ad_group or '—'}` | "
                f"Spend: ${r.spend:.0f} | Leads: {r.leads} | SQLs: {r.sqls} | "
                f"Qual: {qual:.0f}%{worst_flag}"
            )

        # Build a replacement suggestion for the worst audience
        worst = rows[0]
        ag_name = (worst.ad_group or "").lower()
        if "broad" in ag_name:
            suggestion = (
                "Audience `{ag}` is Broad — replace with **Lookalike 1-3%** or "
                "**Interests** (narrow to job title / company size) to improve lead quality."
            ).format(ag=worst.ad_group)
        elif "interest" in ag_name:
            suggestion = (
                "Audience `{ag}` is Interest-based — tighten by adding **age 25-45** "
                "exclusion, **exclude students**, or switch to a **Lookalike** seed "
                "built from qualified leads."
            ).format(ag=worst.ad_group)
        elif "lookalike" in ag_name or "lal" in ag_name:
            suggestion = (
                "Audience `{ag}` is Lookalike — try a tighter seed: use only **SQLs** "
                "(not all leads) to build the lookalike, or shrink to **1%** similarity."
            ).format(ag=worst.ad_group)
        elif "retarget" in ag_name or "remarketing" in ag_name:
            suggestion = (
                "Audience `{ag}` is Retargeting — check recency window (shorten to 14d), "
                "exclude converted users, or split by page visited (pricing page > blog)."
            ).format(ag=worst.ad_group)
        else:
            suggestion = (
                "Audience `{ag}` has the lowest qual rate — review targeting criteria "
                "and consider replacing with a Lookalike built from qualified leads."
            ).format(ag=worst.ad_group)

        lines.append(f"\nReplacement suggestion: {suggestion}")
        return "\n".join(lines) + "\n"
    except Exception as e:
        print(f"[health-tasks] audience detail error: {e}")
        return ""


# ── Budget helpers ─────────────────────────────────────────────────────────────

def _recent_spend_trend(channel: str, campaign_name: str, account_id: str,
                        recent_days: int = 3,
                        window_days: int = DAYS_FOR_PAUSE_DECISION) -> tuple[str | None, float | None, float | None]:
    """
    Compare last-3-day avg spend to the full window average.
    Returns (trend_label, recent_avg, window_avg).

    trend_label values:
      "no_recent_spend"  — zero spend in last 3 days (campaign may be paused/exhausted)
      "declining"        — recent avg < 60% of window avg
      "stable"           — within ±30% of window avg
      "accelerating"     — recent avg > 130% of window avg (budget ramping up)
      None               — insufficient data
    """
    try:
        client    = get_client()
        today     = date.today()
        since_win = (today - timedelta(days=window_days)).isoformat()
        since_rec = (today - timedelta(days=recent_days)).isoformat()
        sql = f"""
            SELECT
              AVG(CASE WHEN date >= '{since_rec}' THEN spend END) AS recent_avg,
              AVG(CASE WHEN date >= '{since_win}' THEN spend END) AS window_avg
            FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
            WHERE channel      = '{channel}'
              AND campaign_name = '{campaign_name.replace("'", "''")}'
              AND account_id    = '{account_id}'
              AND date         >= '{since_win}'
              AND spend         > 0
        """
        rows = list(client.query(sql).result())
        if not rows or rows[0].window_avg is None:
            return None, None, None
        recent = float(rows[0].recent_avg or 0)
        window = float(rows[0].window_avg or 0)
        if window == 0:
            return None, None, None
        ratio = recent / window
        if recent == 0:
            label = "no_recent_spend"
        elif ratio < 0.60:
            label = "declining"
        elif ratio > 1.30:
            label = "accelerating"
        else:
            label = "stable"
        return label, round(recent, 2), round(window, 2)
    except Exception as e:
        print(f"[health-tasks] spend trend error: {e}")
        return None, None, None


def _avg_daily_spend(channel: str, campaign_name: str, account_id: str,
                     days: int = DAYS_FOR_PAUSE_DECISION) -> float | None:
    """Approximate current daily budget from recent average daily spend in BQ."""
    try:
        client = get_client()
        since  = (date.today() - timedelta(days=days)).isoformat()
        sql = f"""
            SELECT AVG(spend) AS avg_daily
            FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
            WHERE channel = '{channel}'
              AND campaign_name = '{campaign_name.replace("'", "''")}'
              AND account_id = '{account_id}'
              AND date >= '{since}'
              AND spend > 0
        """
        rows = list(client.query(sql).result())
        return float(rows[0].avg_daily) if rows and rows[0].avg_daily else None
    except Exception as e:
        print(f"[health-tasks] avg_daily_spend error: {e}")
        return None


def _scale_budget(channel: str, campaign_name: str, account_id: str,
                  campaign_id: str | None) -> str:
    """
    Increase budget by 25%. Uses avg daily spend from BQ as proxy for current budget.
    Returns a status string for the Asana task log.
    """
    avg = _avg_daily_spend(channel, campaign_name, account_id)
    if not avg:
        return f"Could not retrieve current budget for {campaign_name}. Scale manually."

    new_budget = round(avg * (1 + SCALE_PCT), 2)
    try:
        if channel == "google_ads" and campaign_id:
            from executors.google_ads import set_campaign_budget
            set_campaign_budget(campaign_id, new_budget, customer_id=account_id)
        elif channel == "meta" and campaign_id:
            from executors.meta import update_campaign_budget
            update_campaign_budget(campaign_id, new_budget)
        elif channel == "snapchat" and campaign_id:
            from executors.snapchat import set_campaign_budget
            set_campaign_budget(campaign_id, new_budget, account_id=account_id)
        elif channel == "tiktok" and campaign_id:
            from executors.tiktok import set_campaign_budget
            set_campaign_budget(campaign_id, new_budget, advertiser_id=account_id)
        else:
            return (f"No campaign_id in BQ for {campaign_name}. "
                    f"Set budget to ${new_budget:.2f}/day manually.")
        return f"Budget raised from ~${avg:.2f}/day to ${new_budget:.2f}/day (+{SCALE_PCT*100:.0f}%)."
    except Exception as e:
        return f"Scale execution failed: {e}. Set to ${new_budget:.2f}/day manually."


def _pause_campaign_exec(channel: str, campaign_id: str, account_id: str) -> str:
    try:
        if channel == "google_ads":
            from executors.google_ads import pause_campaign
            pause_campaign(campaign_id, customer_id=account_id)
        elif channel == "meta":
            from executors.meta import pause_campaign
            pause_campaign(campaign_id)
        elif channel == "snapchat":
            from executors.snapchat import pause_campaign
            pause_campaign(campaign_id, account_id=account_id)
        elif channel == "tiktok":
            from executors.tiktok import pause_campaign
            pause_campaign(campaign_id, advertiser_id=account_id)
        else:
            return f"Auto-pause not supported for {channel}. Pause manually."
        return "Paused automatically (CPQL > 3x warning threshold)."
    except Exception as e:
        return f"Pause execution failed: {e}. Pause manually."


# ── Card formatter (replaces markdown tables) ──────────────────────────────────

def _campaign_card(findings: list[dict], include_exec: bool = False) -> str:
    """Format each campaign finding as a structured card with metrics table."""
    if not findings:
        return ""
    cards = []
    for i, f in enumerate(findings, 1):
        cpl_s  = f"${f['cpl']:.2f}"  if f.get("cpl")  else "N/A"
        cpql_s = f"${f['cpql']:.2f}" if f.get("cpql") else "N/A"
        roas_s = f"{f['roas']:.2f}x" if f.get("roas") else "—"
        edit_s = f"{f.get('last_updated', '?')} ({f.get('days_since_edit', '?')}d ago)"
        note   = f.get("exec_result", f.get("note", ""))
        date_from = f.get("date_from", "")
        date_to   = f.get("date_to", "")

        flags = []
        if f.get("junk_leads"):    flags.append("JUNK LEADS")
        if f.get("is_awareness"):  flags.append("AWARENESS")
        if f.get("roas_override"): flags.append("ROAS OK")
        if f.get("is_qflavours"):  flags.append("CHECK QFLAVOURS PIPELINE")
        flag_line = f"\n\nFlags: {' | '.join(flags)}" if flags else ""

        # HubSpot verification line so the reviewer can cross-check directly
        hs_verify = ""
        if date_from and date_to:
            hs_verify = (
                f"\n\nVerify in HubSpot: Filter Lead module by "
                f"lead_utm_campaign = {f['campaign']} "
                f"and create date {date_from} to {date_to} to confirm these numbers."
            )

        header = f"**Campaign {i} of {len(findings)}**\n\n" if len(findings) > 1 else ""
        card = (
            f"{header}"
            f"| Metric | Value |\n"
            f"|---|---|\n"
            f"| Channel | {f['channel'].replace('_', ' ').title()} |\n"
            f"| Campaign | `{f['campaign']}` |\n"
            f"| Period | {date_from} to {date_to} |\n"
            f"| Spend | ${f['spend']:.0f} |\n"
            f"| Total Leads | {f['hs_leads']} |\n"
            f"| Qualified Leads (SQL) | {f['sqls']} |\n"
            f"| Qual Rate | {f['qual_rate']:.1f}% |\n"
            f"| CPL | {cpl_s} |\n"
            f"| CPQL | {cpql_s} |\n"
            f"| ROAS | {roas_s} |\n"
            f"| Last Edit | {edit_s} |"
            + flag_line
            + hs_verify
            + (f"\n\n{'Action taken' if include_exec else 'Analysis'}: {note}" if note else "")
        )
        cards.append(card)
    return "\n\n---\n\n".join(cards) + "\n"


# ── Main entry point ───────────────────────────────────────────────────────────

def create_health_tasks(days: int = DAYS_FOR_PAUSE_DECISION,
                        findings: list | None = None) -> list[tuple[str, str | None]]:
    """
    Execute direct actions and create Asana tasks from health findings.
    Pass pre-computed findings to avoid a double BQ query when called from the scheduler.

    Scale:   +25%, force-executed (no approval gate).
    Pause:   force-executed when CPQL > 3x warning.
    Keyword: auto-pause non-converting keywords 7+ days (see audit_nonconverting_keywords).
    """
    if findings is None:
        findings = audit_campaign_health(days=days)

    # ── Pre-publish gate: validate data before creating any tasks or Slack msgs ──
    try:
        from scripts.report_validator import pre_publish_gate
        validation = pre_publish_gate(findings, days=days, post_slack_on_fail=True)
        if not validation.ok:
            print(f"[health-tasks] BLOCKED by validator: {len(validation.errors)} error(s). "
                  f"No tasks or Slack messages will be published.")
            print(validation.summary())
            return [("validation-failed", None)]
        if validation.warnings:
            print(f"[health-tasks] Validator warnings (non-blocking):\n{validation.summary()}")
    except Exception as e:
        # Validator itself crashed — log but don't block the run
        print(f"[health-tasks] Validator error (non-blocking): {e}")

    out: list[tuple[str, str | None]] = []

    scale_f     = [f for f in findings if f["action"] == "scale"]
    pause_f     = [f for f in findings if f["action"] == "pause"]
    optimize_f  = [f for f in findings if f["action"] == "optimize"]
    drilldown_f = [f for f in findings if f["action"] == "drilldown"]
    # Junk leads are a sub-type of pause — merge into pause bucket.
    # Add any junk campaigns not already in pause_f (junk_leads CAN appear in optimize_f too).
    pause_names = {f["campaign"] for f in pause_f}
    junk_extra  = [f for f in findings if f.get("junk_leads") and f["campaign"] not in pause_names]
    pause_f     = pause_f + junk_extra

    # ── 1. Scale candidates — one task per campaign ────────────────────────────
    if scale_f:
        for f in scale_f:
            avg = _avg_daily_spend(f["channel"], f["campaign"], f["account_id"])
            f["avg_spend"]  = avg
            f["new_budget"] = round(avg * (1 + SCALE_PCT), 2) if avg else None

            # ── Scale sanity check — spend trend last 3d vs window avg ───────
            trend, recent_avg, window_avg = _recent_spend_trend(
                f["channel"], f["campaign"], f["account_id"]
            )
            f["spend_trend"]      = trend
            f["spend_trend_recent"] = recent_avg
            f["spend_trend_window"] = window_avg

            if trend == "no_recent_spend":
                sanity_block = (
                    "\n\nScale sanity check - HOLD: No spend recorded in the last 3 days. "
                    "Campaign may be paused, budget-exhausted, or disapproved. "
                    "Confirm campaign is actively spending before raising budget."
                )
            elif trend == "declining":
                sanity_block = (
                    f"\n\nScale sanity check - Caution: Spend declining "
                    f"(${recent_avg:.0f}/day last 3d vs ${window_avg:.0f}/day avg). "
                    f"Budget raise may not help if campaign is already delivery-limited. "
                    f"Check platform for budget exhaustion, ad disapprovals, or audience saturation."
                )
            elif trend == "accelerating":
                sanity_block = (
                    f"\n\nScale sanity check - Strong: Spend accelerating "
                    f"(${recent_avg:.0f}/day last 3d vs ${window_avg:.0f}/day avg). "
                    f"Good delivery momentum — +{SCALE_PCT*100:.0f}% budget raise will compound it."
                )
            else:
                sanity_block = (
                    f"\n\nScale sanity check - Stable: Spend consistent "
                    f"(${recent_avg:.0f}/day last 3d vs ${window_avg:.0f}/day avg). "
                    f"Budget raise expected to increase delivery proportionally."
                    if recent_avg is not None else ""
                )

            if f.get("is_awareness"):
                lost_bud = f.get("is_lost_budget")
                awareness_note = (
                    f"\nAwareness campaign — Lost IS (Budget) = {lost_bud*100:.0f}%. "
                    f"Budget is the bottleneck; raising it will capture more impressions.\n"
                    if lost_bud is not None else
                    "\nAwareness campaign — confirm IS metrics in platform before raising budget.\n"
                )
            else:
                awareness_note = ""

            # Alternatives note from analyser
            alt_block = ""
            if f.get("alt_recommendation"):
                alt_block = f"\n\nAlternatives considered: {f['alt_recommendation']}"

            date_range_str = f"{f['date_from']} to {f['date_to']}"
            body = (
                f"## Scale Candidate — Awaiting Approval\n\n"
                f"**Data sources:** Spend = {f['channel'].replace('_',' ').title()} platform | Leads & SQLs = HubSpot Lead Module | Evaluation = CPQL first\n\n"
                + _campaign_card([f])
                + awareness_note
                + sanity_block
                + alt_block
                + f"\n\nAction required: React with checkmark in #approvals to raise budget +{SCALE_PCT*100:.0f}%."
            )
            gid = create_task(
                title=f"PENDING APPROVAL: Scale — {f['campaign']} +{SCALE_PCT*100:.0f}% ({date_range_str})",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=f.get("channel", "general"),
                asset_level="campaign",
                action="scale",
                campaign_name=f["campaign"],
            )
            out.append((f"scale-pending {f['campaign']}", gid))
            log_activity_async(
                role="performance_audit", action="scale_task_created",
                status="pending_approval",
                channel=f.get("channel"), campaign_name=f.get("campaign"),
                details={"avg_spend": f.get("avg_spend"), "new_budget": f.get("new_budget"),
                         "cpql": f.get("cpql"), "asana_gid": gid},
            )

    # ── 2. Pause candidates (+ junk leads) — one task per campaign ────────────
    if pause_f:
        for f in pause_f:
            if f.get("junk_leads"):
                title = f"PENDING APPROVAL: Pause — {f['campaign']} — Junk Leads ({f['date_from']} to {f['date_to']})"
                reason = (
                    "CPL looks cheap but qual rate is low — leads are not converting to SQLs. "
                    "Do NOT scale on CPL alone. Fix audience, creative, or LP before any budget change."
                )
                # Fetch keyword and audience drill-down for this junk campaign
                kw_detail  = _get_junk_keyword_detail(f["channel"], f["campaign"], days)
                aud_detail = _get_junk_audience_detail(f["channel"], f["campaign"], days)
                junk_drill = ""
                if kw_detail:
                    junk_drill += f"\n\n{kw_detail}"
                if aud_detail:
                    junk_drill += f"\n{aud_detail}"
                if not junk_drill:
                    junk_drill = (
                        "\n\n**Common causes:**\n"
                        "- Wrong audience pulling unqualified traffic\n"
                        "- Broad-match keywords capturing off-intent searches\n"
                        "- Landing page / form not filtering by company size or role\n"
                        "- Creative attracting B2C audience instead of B2B\n"
                    )
            else:
                title = f"PENDING APPROVAL: Pause — {f['campaign']} — CPQL critical ({f['date_from']} to {f['date_to']})"
                reason = "Fix audience/creative/LP before reactivating."
                junk_drill = ""
            # Alternatives-considered block from analyser
            alt_section = ""
            if f.get("alt_budget_cut_pct") is not None:
                cut = f["alt_budget_cut_pct"]
                alt_section = (
                    f"\n\nAlternatives considered before recommending pause:\n"
                    f"- Option A (recommended first): Cut budget -{cut}% and monitor for 7 days. "
                    f"If CPQL improves to under ${f.get('cpql',0)*(1-cut/100):.0f}, keep running at lower spend.\n"
                    f"- Option B (this task): Full pause. {reason} "
                    f"Apply only if Option A does not move CPQL.\n"
                )
            elif f.get("alt_recommendation"):
                alt_section = (
                    f"\n\nAlternatives considered: {f['alt_recommendation']}"
                )

            body = (
                f"## Pause Candidate — Awaiting Approval\n\n"
                f"**Data sources:** Spend = {f['channel'].replace('_',' ').title()} platform | Leads & SQLs = HubSpot Lead Module | Evaluation = CPQL first\n\n"
                + _campaign_card([f])
                + f"\n\nWhy pause: {reason}"
                + alt_section
                + junk_drill
                + "\n\nAction required: React with checkmark in #approvals to pause this campaign."
            )
            gid = create_task(
                title=title,
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=f.get("channel", "general"),
                asset_level="campaign",
                action="pause",
                campaign_name=f["campaign"],
            )
            out.append((f"pause-pending {f['campaign']}", gid))
            log_activity_async(
                role="performance_audit",
                action="junk_leads_task_created" if f.get("junk_leads") else "pause_task_created",
                status="pending_approval",
                channel=f.get("channel"), campaign_name=f.get("campaign"),
                details={"junk_leads": f.get("junk_leads"), "qual_rate": f.get("qual_rate"),
                         "cpql": f.get("cpql"), "asana_gid": gid},
            )

    # ── Nightly approvals digest sent ONCE at the end (after all blocks) ─────
    # Collected here; posted below after review_items are built.

    # ── 3. Drill-down analysis tasks — one task per campaign ──────────────────
    if drilldown_f:
        from analysers.ad_drilldown import get_ad_drilldown_table, get_keyword_drilldown_table

        for f in drilldown_f:
            channel = f["channel"]
            date_from = f.get("date_from", "")
            date_to   = f.get("date_to", "")
            date_range_str = f"{date_from} to {date_to}" if date_from and date_to else f"last {days} days"
            ch_type = f.get("drilldown_channel_type", "social")

            if ch_type == "search":
                hierarchy = (
                    "**Analysis order for Google Ads / Microsoft Ads:**\n"
                    "1. **Keywords** — pause if either rule is met (running ≥14 days):\n"
                    "   - Rule A: spend > $35 AND 0 conversions\n"
                    "   - Rule B: CPL > $80 AND 1+ conversions (low quality)\n"
                    "2. **Ad Groups** — if ≥50% of keywords in a group are flagged → pause group\n"
                    "3. **Campaign** — pause only after confirming all ad groups are underperforming\n"
                )
            else:
                hierarchy = (
                    "**Analysis order for social channels:**\n"
                    "1. **Ads** — identify highest-CPL and zero-lead ads → pause them first\n"
                    "2. **Ad Sets** — if ≥50% of ads in an ad set are bad → pause the ad set\n"
                    "3. **Campaign** — pause only after confirming all ad sets are underperforming\n"
                )

            drill_table = ""
            try:
                if ch_type == "search":
                    drill_table = get_keyword_drilldown_table(channel, f["campaign"], days)
                else:
                    drill_table = get_ad_drilldown_table(channel, f["campaign"], days)
            except Exception as e:
                drill_table = f"\n_(Ad/keyword data not available: {e})_\n"

            creative_section = ""
            try:
                cr = audit_creative_performance(campaign_name=f["campaign"], channel=channel, days=30)
                creative_section = format_creative_section(cr) or ""
            except Exception as e:
                print(f"[health-tasks] creative analysis failed for {f['campaign']}: {e}")

            body = (
                f"## Drill-down Analysis Required\n\n"
                f"**Data sources:** Spend = {channel.replace('_',' ').title()} platform | Leads & SQLs = HubSpot Lead Module\n\n"
                f"CPQL >${DRILL_DOWN_CPQL} AND CPL >${DRILL_DOWN_CPL} for {days} days. "
                f"Do NOT pause at campaign level yet.\n\n"
                + hierarchy + "\n"
                + _campaign_card([f])
                + ("\n\n**Ad / Keyword detail (Campaign > Ad Set > Ad):**\n" + drill_table if drill_table.strip() else "")
                + (f"\n{creative_section}" if creative_section else "")
            )
            gid = create_task(
                title=f"{channel.replace('_',' ').title()} — Drill-down: {f['campaign']} ({date_range_str})",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=channel,
                asset_level="ad" if ch_type == "social" else "keyword",
                action="optimize",
                campaign_name=f["campaign"],
            )
            out.append((f"drilldown {channel} {f['campaign']}", gid))
            log_activity_async(
                role="performance_audit", action="drilldown_task_created",
                status="pending_approval",
                channel=channel, campaign_name=f.get("campaign"),
                details={"cpql": f.get("cpql"), "cpl": f.get("cpl"), "asana_gid": gid},
            )

    # ── 5. Optimize (investigate) — one task per campaign ────────────────────
    #    Includes awareness campaigns routed here (action="optimize") — they get
    #    an IS-review body instead of CPQL investigation.

    if optimize_f:
        for f in optimize_f:
            channel = f["channel"]
            date_from = f.get("date_from", "")
            date_to   = f.get("date_to", "")
            date_range_str = f"{date_from} to {date_to}" if date_from and date_to else f"last {days} days"

            creative_section = ""
            if not f.get("is_awareness"):
                try:
                    cr = audit_creative_performance(campaign_name=f["campaign"], channel=channel, days=30)
                    creative_section = format_creative_section(cr) or ""
                except Exception as e:
                    print(f"[health-tasks] creative analysis failed for {f['campaign']}: {e}")

            if f.get("is_awareness"):
                section_title = f"### {channel} — Awareness / IS Review"
                is_pct     = f"{f['is_share']*100:.0f}%" if f.get("is_share") is not None else "N/A"
                lost_bud   = f"{f['is_lost_budget']*100:.0f}%" if f.get("is_lost_budget") is not None else "N/A"
                lost_rank  = f"{f['is_lost_rank']*100:.0f}%" if f.get("is_lost_rank") is not None else "N/A"
                is_metrics = (
                    f"IS: {is_pct} | Lost (Budget): {lost_bud} | Lost (Rank): {lost_rank}\n\n"
                    if f.get("is_share") is not None else ""
                )
                investigation = (
                    f"**Awareness / traffic campaign — primary KPI is impression share.**\n\n"
                    + is_metrics
                    + "Checklist:\n"
                    "- If Lost IS (Budget) > 20%: raise daily budget\n"
                    "- If Lost IS (Rank) > 30%: improve Quality Score or raise bids\n"
                    "- If IS > 80%: broaden keywords / add new ad groups\n"
                    "- If frequency > 3: go to the Ads level in this campaign, identify the ad(s) with the highest frequency, then: (1) pause that ad, (2) duplicate it inside the same ad set, (3) change the hook or lead visual — do not change audience or budget\n"
                    "- Ensure `utm_source=paid_social&utm_medium=cpm` so brand-lift is tracked\n"
                )
                task_title = f"{channel.replace('_',' ').title()} — IS Review: {f['campaign']} ({date_range_str})"
            else:
                section_title = f"### {channel} — CPQL investigation"
                investigation = (
                    "**Common causes:**\n"
                    "- Poor qual rate: wrong audience or keyword intent\n"
                    "- High CPQL vs CPL: leads entering but not qualifying (LP or ICP mismatch)\n"
                    "- Missing UTM: HubSpot not receiving utm_campaign correctly\n"
                )
                task_title = f"{channel.replace('_',' ').title()} — CPQL investigation: {f['campaign']} ({date_range_str})"

            body = (
                f"## Optimize — Investigation Required\n\n"
                f"**Data sources:** Spend = {channel.replace('_',' ').title()} platform | Leads & SQLs = HubSpot Lead Module\n"
                f"Note: Actions only applied to campaigns last edited >=7 days ago.\n\n"
                + section_title + "\n\n"
                + _campaign_card([f])
                + f"\n\n{investigation}"
                + (f"\n{creative_section}" if creative_section else "")
            )
            gid = create_task(
                title=task_title,
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=channel,
                asset_level="campaign",
                action="optimize",
                campaign_name=f["campaign"],
            )
            out.append((f"optimize {channel} {f['campaign']}", gid))
            log_activity_async(
                role="performance_audit", action="optimize_task_created",
                status="pending_approval",
                channel=channel, campaign_name=f.get("campaign"),
                details={"cpql": f.get("cpql"), "cpl": f.get("cpl"),
                         "is_awareness": f.get("is_awareness"), "asana_gid": gid},
            )

    # ── ONE #approvals message covering everything ────────────────────────────
    review_items: list[dict] = []
    for f in drilldown_f + optimize_f + junk_extra:
        if f not in review_items:
            review_items.append(f)
    _send_nightly_digest(scale_f, pause_f, review_items)

    return out


def _send_nightly_digest(scale_findings: list, pause_findings: list, review_findings: list) -> None:
    """
    Post THE ONE #approvals message for the night.
    Covers scale + pause (executable on ✅) + optimize/junk/drilldown (review summary).
    """
    if not scale_findings and not pause_findings and not review_findings:
        return
    try:
        from notifications.slack import post_nightly_approvals_digest
        ts = post_nightly_approvals_digest(scale_findings, pause_findings, review_findings)
        print(f"[health-tasks] nightly digest posted "
              f"(scale={len(scale_findings)}, pause={len(pause_findings)}, "
              f"review={len(review_findings)}, ts={ts})")
        log_activity_async(
            role="daily_digest", action="posted_approvals_digest",
            status="success",
            details={"scale": len(scale_findings), "pause": len(pause_findings),
                     "review": len(review_findings), "slack_ts": ts},
        )
    except Exception as e:
        print(f"[health-tasks] nightly digest failed: {e}")


if __name__ == "__main__":
    created = create_health_tasks()
    print(f"\nCreated/executed {len(created)} task(s):")
    for label, gid in created:
        print(f"  gid={gid}  {label}")
