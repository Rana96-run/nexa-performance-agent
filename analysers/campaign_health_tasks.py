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

    scale_f      = [f for f in findings if f["action"] == "scale"]
    pause_f      = [f for f in findings if f["action"] == "pause"]
    optimize_f   = [f for f in findings if f["action"] == "optimize"]
    drilldown_f  = [f for f in findings if f["action"] == "drilldown"]
    junk_f       = [f for f in findings if f.get("junk_leads")]
    awareness_f  = [f for f in findings if f.get("is_awareness")]

    # ── 1. Execute scale (+25%) ────────────────────────────────────────────────
    if scale_f:
        for f in scale_f:
            result = _scale_budget(f["channel"], f["campaign"],
                                   f["account_id"], f.get("campaign_id"))
            f["exec_result"] = result
            print(f"[health-tasks] SCALE {f['campaign']}: {result}")

        body = (
            f"Campaign health audit — last {days} days. "
            f"**EXECUTED: budget +{SCALE_PCT*100:.0f}%**\n"
            f"Cost: channel source | Leads: HubSpot Lead Module | "
            f"Evaluation: CPQL first\n\n"
            f"### Scaled campaigns ({len(scale_f)})\n"
            + _campaign_table(scale_f, include_exec=True)
        )
        gid = create_task(
            title=f"EXECUTED: Scaled {len(scale_f)} campaign(s) +{SCALE_PCT*100:.0f}% ({days}d)",
            description=body,
            project_key="optimization",
            task_type="Direct Log",
            channel="general",
            asset_level="campaign",
            action="scale",
        )
        out.append((f"scale-executed ({len(scale_f)})", gid))

    # ── 2. Execute pause ───────────────────────────────────────────────────────
    if pause_f:
        for f in pause_f:
            cid = f.get("campaign_id")
            if cid:
                result = _pause_campaign_exec(f["channel"], cid, f["account_id"])
            else:
                result = "No campaign_id in BQ — pause manually."
            f["exec_result"] = result
            print(f"[health-tasks] PAUSE {f['campaign']}: {result}")

        body = (
            f"Campaign health audit — last {days} days. "
            f"**EXECUTED: campaigns paused (CPQL critical)**\n"
            f"Cost: channel source | Leads: HubSpot Lead Module | "
            f"Evaluation: CPQL first\n\n"
            f"### Paused campaigns ({len(pause_f)})\n"
            + _campaign_table(pause_f, include_exec=True)
            + "\nReview these campaigns — fix audience/creative/LP before reactivating."
        )
        gid = create_task(
            title=f"EXECUTED: Paused {len(pause_f)} campaign(s) — CPQL critical ({days}d)",
            description=body,
            project_key="optimization",
            task_type="Direct Log",
            channel="general",
            asset_level="campaign",
            action="pause",
        )
        out.append((f"pause-executed ({len(pause_f)})", gid))

    # ── 3. Junk-leads alert ────────────────────────────────────────────────────
    if junk_f:
        # Creative analysis: junk leads are often a creative-level problem
        junk_creative_sections = []
        for f in junk_f:
            try:
                cr = audit_creative_performance(campaign_name=f["campaign"], channel=f.get("channel"), days=30)
                section = format_creative_section(cr)
                if section:
                    junk_creative_sections.append(section)
            except Exception as e:
                print(f"[health-tasks] creative analysis failed for {f['campaign']}: {e}")

        body = (
            f"**Junk-Leads Alert** — {len(junk_f)} campaign(s) with misleading low CPL.\n\n"
            f"These campaigns show a CPL in the scale zone but their CPQL and qual rate "
            f"are in the pause/warning zone. This means: leads are cheap but most don't "
            f"qualify. **Do not scale on CPL alone.**\n\n"
            f"Root causes to investigate:\n"
            f"- Wrong audience pulling unqualified traffic\n"
            f"- Keyword intent mismatch (informational vs transactional)\n"
            f"- Landing page / form attracting non-ICP visitors\n"
            f"- UTM attribution gaps (leads attributed to wrong campaign)\n\n"
            + _campaign_table(junk_f)
            + ("\n" + "\n".join(junk_creative_sections) if junk_creative_sections else "")
        )
        gid = create_task(
            title=f"Junk-Leads Alert: {len(junk_f)} campaign(s) with low CPL but poor CPQL",
            description=body,
            project_key="optimization",
            task_type="Recommendation",
            channel="general",
            asset_level="campaign",
            action="optimize",
        )
        out.append((f"junk-leads-alert ({len(junk_f)})", gid))

    # ── 4. Drill-down analysis tasks ──────────────────────────────────────────
    if drilldown_f:
        from analysers.ad_drilldown import get_ad_drilldown_table, get_keyword_drilldown_table

        by_channel: dict[str, list[dict]] = {}
        for f in drilldown_f:
            by_channel.setdefault(f["channel"], []).append(f)

        for channel, ch_findings in by_channel.items():
            date_from = ch_findings[0].get("date_from", "")
            date_to   = ch_findings[0].get("date_to", "")
            date_range_str = f"{date_from} to {date_to}" if date_from and date_to else f"last {days} days"
            ch_type = ch_findings[0].get("drilldown_channel_type", "social")

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

            # Pull actual ad/keyword data from BQ if available
            drill_table = ""
            for f in ch_findings:
                campaign_name = f.get("campaign", "")
                try:
                    if ch_type == "search":
                        drill_table += get_keyword_drilldown_table(channel, campaign_name, days)
                    else:
                        drill_table += get_ad_drilldown_table(channel, campaign_name, days)
                except Exception as e:
                    drill_table += f"\n_(Ad/keyword data not available yet for {campaign_name}: {e})_\n"

            # Creative analysis per campaign in this drilldown group
            drill_creative_sections = []
            for f in ch_findings:
                try:
                    cr = audit_creative_performance(campaign_name=f["campaign"], channel=f.get("channel"), days=30)
                    section = format_creative_section(cr)
                    if section:
                        drill_creative_sections.append(section)
                except Exception as e:
                    print(f"[health-tasks] creative analysis failed for {f['campaign']}: {e}")

            body = (
                f"**Drill-down Analysis Required — {channel} — {date_range_str}**\n\n"
                f"These campaigns have CPQL >${DRILL_DOWN_CPQL} AND CPL >${DRILL_DOWN_CPL} "
                f"for {days} days. Do NOT pause at campaign level yet.\n\n"
                + hierarchy + "\n"
                + _campaign_table(ch_findings)
                + ("\n\n**Ad / Keyword detail:**\n" + drill_table if drill_table.strip() else "")
                + ("\n" + "\n".join(drill_creative_sections) if drill_creative_sections else "")
            )
            gid = create_task(
                title=f"{channel.replace('_',' ').title()} — Drill-down: {len(ch_findings)} campaign(s) ({date_range_str})",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=channel,
                asset_level="ad" if ch_type == "social" else "keyword",
                action="optimize",
            )
            out.append((f"drilldown {channel} ({len(ch_findings)})", gid))
        _send_approval_requests(drilldown_f)

    # ── 5. Optimize (investigate) + send approval request to Slack ────────────
    if optimize_f or junk_f:
        # Send one approval request per finding that needs human review
        approval_items = optimize_f + [f for f in junk_f if f not in optimize_f]
        _send_approval_requests(approval_items)

    if optimize_f:
        by_channel: dict[str, list[dict]] = {}
        for f in optimize_f:
            by_channel.setdefault(f["channel"], []).append(f)

        for channel, ch_findings in by_channel.items():
            # Date range from first finding
            date_from = ch_findings[0].get("date_from", "")
            date_to   = ch_findings[0].get("date_to", "")
            date_range_str = f"{date_from} to {date_to}" if date_from and date_to else f"last {days} days"

            # Creative analysis: one call per campaign, append sections
            opt_creative_sections = []
            for f in ch_findings:
                try:
                    cr = audit_creative_performance(campaign_name=f["campaign"], channel=f.get("channel"), days=30)
                    section = format_creative_section(cr)
                    if section:
                        opt_creative_sections.append(section)
                except Exception as e:
                    print(f"[health-tasks] creative analysis failed for {f['campaign']}: {e}")

            body = (
                f"Campaign health audit — **{date_range_str}**\n"
                f"Cost: channel source | Leads: HubSpot Lead Module\n"
                f"⚠️ Actions only applied to campaigns last edited ≥7 days ago.\n\n"
                f"### {channel} — {len(ch_findings)} campaigns need CPQL investigation\n"
                + _campaign_table(ch_findings)
                + "\n**Common causes:**\n"
                "- Poor qual rate: wrong audience or keyword intent\n"
                "- High CPQL vs CPL: leads entering but not qualifying (LP or ICP mismatch)\n"
                "- Missing UTM: HubSpot not receiving utm_campaign correctly\n"
                + ("\n" + "\n".join(opt_creative_sections) if opt_creative_sections else "")
            )
            # Append cross-type creative breakdown once per channel group
            try:
                by_type_result = audit_creative_by_campaign_type(days=30)
                by_type_section = format_creative_by_type_section(by_type_result)
                if by_type_section:
                    body += by_type_section
            except Exception as e:
                print(f"[health-tasks] creative by-type analysis failed: {e}")
            gid = create_task(
                title=f"{channel.replace('_',' ').title()} — {len(ch_findings)} campaigns: CPQL investigation ({days}d)",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=channel,
                asset_level="campaign",
                action="optimize",
            )
            out.append((f"optimize {channel} ({len(ch_findings)})", gid))

    # ── 6. Awareness / traffic / reach campaigns ──────────────────────────────
    if awareness_f:
        by_channel: dict[str, list[dict]] = {}
        for f in awareness_f:
            by_channel.setdefault(f["channel"], []).append(f)

        for channel, ch_findings in by_channel.items():
            rows = ""
            for f in ch_findings:
                rows += (f"| {f['campaign']} | ${f['spend']:.0f} | "
                         f"{f['hs_leads']} | {f.get('status','')} | "
                         f"Check impression share ≥ 25% in platform |\n")

            body = (
                f"**Awareness / Traffic Campaign Review — last {days} days**\n\n"
                f"These campaigns are NOT evaluated on leads. "
                f"Primary KPI: **impression share ≥ 25%**.\n\n"
                f"| Campaign | Spend | Impressions (leads) | Status | Action |\n"
                f"|---|---|---|---|---|\n"
                + rows
                + "\n**Optimization checklist:**\n"
                "- Check impression share in platform — target ≥ 25%\n"
                "- If IS < 25%: raise daily budget or broaden targeting\n"
                "- If frequency > 3: refresh creatives to avoid ad fatigue\n"
                "- If CTR < 0.5%: test new creatives / headlines\n"
                "- Review audience overlap with performance campaigns\n"
                "- Ensure UTM source/medium are set (`utm_source=paid_social&utm_medium=cpm`) "
                "so brand-lift can be tracked in HubSpot\n"
            )
            gid = create_task(
                title=f"{channel.replace('_',' ').title()} — Impression Share & Traffic Review ({days}d)",
                description=body,
                project_key="optimization",
                task_type="Recommendation",
                channel=channel,
                asset_level="campaign",
                action="optimize",
            )
            out.append((f"awareness-review {channel} ({len(ch_findings)})", gid))

    return out


def _send_approval_requests(findings: list) -> None:
    """
    Post ONE digest approval message for all findings to #approvals.
    Findings with no SQL data (CPQL=N/A, qual_rate=0, no junk flag) are silently
    dropped — no basis for a decision.
    """
    try:
        from notifications.slack import post_approval_digest
    except Exception as e:
        print(f"[health-tasks] approval import failed: {e}")
        return

    # Filter out no-SQL findings
    actionable = [
        f for f in findings
        if f.get("cpql") or f.get("qual_rate", 0) > 0 or f.get("junk_leads")
    ]
    skipped = len(findings) - len(actionable)
    if skipped:
        print(f"[health-tasks] {skipped} finding(s) skipped (no SQL data)")
    if not actionable:
        print("[health-tasks] no actionable findings — skipping approval digest")
        return

    try:
        ts = post_approval_digest(actionable)
        print(f"[health-tasks] approval digest posted ({len(actionable)} findings, ts={ts})")
    except Exception as e:
        print(f"[health-tasks] approval digest failed: {e}")


if __name__ == "__main__":
    created = create_health_tasks()
    print(f"\nCreated/executed {len(created)} task(s):")
    for label, gid in created:
        print(f"  gid={gid}  {label}")
