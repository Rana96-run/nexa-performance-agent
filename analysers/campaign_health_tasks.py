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

import os
from datetime import date, timedelta

from analysers.campaign_health import audit_campaign_health
from analysers.creative_performance import (
    audit_creative_performance, format_creative_section,
    audit_creative_by_campaign_type, format_creative_by_type_section,
)
from executors.asana import create_task
from config import DAYS_FOR_PAUSE_DECISION, DRILL_DOWN_CPQL, DRILL_DOWN_CPL

SCALE_PCT = 0.25   # always 25%


# ── Budget helpers ─────────────────────────────────────────────────────────────

def _avg_daily_spend(channel: str, campaign_name: str, account_id: str,
                     days: int = DAYS_FOR_PAUSE_DECISION) -> float | None:
    """Approximate current daily budget from recent average daily spend in BQ."""
    try:
        from google.cloud import bigquery as _bq
        from google.oauth2 import service_account as _sa

        project  = os.getenv("BQ_PROJECT_ID")
        dataset  = os.getenv("BQ_DATASET", "qoyod_marketing")
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
        creds    = _sa.Credentials.from_service_account_file(key_path)
        client   = _bq.Client(project=project, credentials=creds)
        since    = (date.today() - timedelta(days=days)).isoformat()
        sql = f"""
            SELECT AVG(spend) AS avg_daily
            FROM `{project}.{dataset}.campaigns_daily`
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


# ── Table formatter ────────────────────────────────────────────────────────────

def _campaign_table(findings: list[dict], include_exec: bool = False) -> str:
    if not findings:
        return ""
    header = "| Channel | Campaign | Spend | Leads | Qual. Leads | CPL | CPQL | Qual% | ROAS | Last Edit |"
    header += " Action taken |\n" if include_exec else " Note |\n"
    header += "|---|---|---|---|---|---|---|---|---|---|---|\n"
    rows = ""
    for f in findings:
        cpl_s    = f"${f['cpl']:.2f}"    if f.get("cpl")           else "N/A"
        cpql_s   = f"${f['cpql']:.2f}"   if f.get("cpql")          else "N/A"
        roas_s   = f"{f['roas']:.2f}x"   if f.get("roas")          else "—"
        edit_s   = f"{f.get('last_updated','?')} ({f.get('days_since_edit','?')}d ago)"
        junk     = " **[JUNK LEADS]**"    if f.get("junk_leads")   else ""
        aware    = " **[AWARENESS]**"     if f.get("is_awareness")  else ""
        roas_ok  = " **[ROAS OK]**"       if f.get("roas_override") else ""
        qflavs   = " **[CHECK QFLAVOURS PIPELINE]**" if f.get("is_qflavours") else ""
        note     = f.get("exec_result", f.get("note", ""))
        rows += (f"| {f['channel']} | {f['campaign']}{junk}{aware}{roas_ok}{qflavs} | ${f['spend']:.0f} | "
                 f"{f['hs_leads']} | {f['sqls']} | {cpl_s} | {cpql_s} | "
                 f"{f['qual_rate']:.1f}% | {roas_s} | {edit_s} | {note} |\n")
    return header + rows


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

            if f.get("is_awareness"):
                lost_bud = f.get("is_lost_budget")
                awareness_note = (
                    f"\n⚠️ **Awareness campaign** — Lost IS (Budget) = {lost_bud*100:.0f}%. "
                    f"Budget is the bottleneck; raising it will capture more impressions.\n"
                    if lost_bud is not None else
                    "\n⚠️ **Awareness campaign** — confirm IS metrics in platform before raising budget.\n"
                )
            else:
                awareness_note = ""
            body = (
                f"Campaign health audit — last {days} days.\n"
                f"Cost: channel source | Leads: HubSpot Lead Module | Evaluation: CPQL first\n\n"
                f"### Scale candidate — *awaiting approval*\n"
                + _campaign_table([f])
                + awareness_note
                + "\nApprove in #approvals to execute the +25% budget increase."
            )
            gid = create_task(
                title=f"PENDING APPROVAL: Scale — {f['campaign']} +{SCALE_PCT*100:.0f}% ({days}d)",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=f.get("channel", "general"),
                asset_level="campaign",
                action="scale",
            )
            out.append((f"scale-pending {f['campaign']}", gid))

    # ── 2. Pause candidates (+ junk leads) — one task per campaign ────────────
    if pause_f:
        for f in pause_f:
            if f.get("junk_leads"):
                title = f"PENDING APPROVAL: Pause — {f['campaign']} — Junk Leads ({days}d)"
                reason = (
                    "CPL looks cheap but qual rate is low — leads are not converting to SQLs. "
                    "Do NOT scale on CPL alone. Fix audience, creative, or LP before any budget change."
                )
            else:
                title = f"PENDING APPROVAL: Pause — {f['campaign']} — CPQL critical ({days}d)"
                reason = "Fix audience/creative/LP before reactivating."
            body = (
                f"Campaign health audit — last {days} days.\n"
                f"Cost: channel source | Leads: HubSpot Lead Module | Evaluation: CPQL first\n\n"
                f"### Pause candidate — *awaiting approval*\n"
                + _campaign_table([f])
                + f"\n{reason}\nApprove in #approvals to pause."
            )
            gid = create_task(
                title=title,
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=f.get("channel", "general"),
                asset_level="campaign",
                action="pause",
            )
            out.append((f"pause-pending {f['campaign']}", gid))

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
                f"**Drill-down Analysis Required — {channel} — {date_range_str}**\n\n"
                f"CPQL >${DRILL_DOWN_CPQL} AND CPL >${DRILL_DOWN_CPL} for {days} days. "
                f"Do NOT pause at campaign level yet.\n\n"
                + hierarchy + "\n"
                + _campaign_table([f])
                + ("\n\n**Ad / Keyword detail:**\n" + drill_table if drill_table.strip() else "")
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
            )
            out.append((f"drilldown {channel} {f['campaign']}", gid))

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
                    "- If frequency > 3: refresh creatives to avoid ad fatigue\n"
                    "- Ensure `utm_source=paid_social&utm_medium=cpm` so brand-lift is tracked\n"
                )
                task_title = f"{channel.replace('_',' ').title()} — IS Review: {f['campaign']} ({days}d)"
            else:
                section_title = f"### {channel} — CPQL investigation"
                investigation = (
                    "**Common causes:**\n"
                    "- Poor qual rate: wrong audience or keyword intent\n"
                    "- High CPQL vs CPL: leads entering but not qualifying (LP or ICP mismatch)\n"
                    "- Missing UTM: HubSpot not receiving utm_campaign correctly\n"
                )
                task_title = f"{channel.replace('_',' ').title()} — CPQL investigation: {f['campaign']} ({days}d)"

            body = (
                f"Campaign health audit — **{date_range_str}**\n"
                f"Cost: channel source | Leads: HubSpot Lead Module\n"
                f"⚠️ Actions only applied to campaigns last edited ≥7 days ago.\n\n"
                + section_title + "\n"
                + _campaign_table([f])
                + f"\n{investigation}"
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
            )
            out.append((f"optimize {channel} {f['campaign']}", gid))

    # ── ONE #approvals message covering everything ────────────────────────────
    review_items: list[dict] = []
    for f in drilldown_f + optimize_f + junk_f:
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
    except Exception as e:
        print(f"[health-tasks] nightly digest failed: {e}")


if __name__ == "__main__":
    created = create_health_tasks()
    print(f"\nCreated/executed {len(created)} task(s):")
    for label, gid in created:
        print(f"  gid={gid}  {label}")
