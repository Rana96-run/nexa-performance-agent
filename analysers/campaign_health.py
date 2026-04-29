"""
analysers/campaign_health.py
=============================
Cross-channel CPQL/CPL health check — the primary analyst investigation.

Measurement rules (from CLAUDE.md):
  - Cost:  campaigns_daily.spend  (channel source, always USD)
  - Leads: hubspot_leads_module_daily  (Lead Module, NOT contact lifecycle)
  - Evaluation order: CPQL first, then CPL
  - Minimum window: 14 days (DAYS_FOR_PAUSE_DECISION)
  - HubSpot pre-aggregated by CTE before joining to avoid spend fan-out

Called from:
  - analysers/campaign_health_tasks.py  (creates Asana tasks + executes actions)
  - main.py daily loop
  - Manual: python -m analysers.campaign_health
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv(override=True)

from config import (
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
    QUAL_RATE_TARGET, DAYS_FOR_PAUSE_DECISION,
    ROAS_GOOD, AWARENESS_PATTERNS,
    CHANNEL_CPQL_ACCEPTABLE, MIN_DAYS_SINCE_EDIT, QFLAVOURS_PIPELINE_CHECK,
    SCALE_REQUIRES_ROAS, DRILL_DOWN_CPQL, DRILL_DOWN_CPL, DRILL_DOWN_DAYS,
    SOCIAL_CHANNELS, SEARCH_CHANNELS,
)


def _bq_client():
    project  = os.getenv("BQ_PROJECT_ID")
    dataset  = os.getenv("BQ_DATASET", "qoyod_marketing")
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
    creds    = service_account.Credentials.from_service_account_file(key_path)
    return bigquery.Client(project=project, credentials=creds), project, dataset


def _is_awareness(campaign_name: str) -> bool:
    """
    Returns True if the campaign is an awareness/traffic/reach campaign.
    These are evaluated on impression share (IS ≥ 25% = healthy), NOT on leads.
    """
    name_lower = campaign_name.lower().replace("-", "").replace(" ", "")
    return any(p in name_lower for p in AWARENESS_PATTERNS)


def _cpql_zone(val: float | None) -> str:
    if val is None:        return "no_data"
    if val < CPQL_SCALE:   return "scale"
    if val <= CPQL_ACCEPTABLE: return "ok"
    if val <= CPQL_WARNING:    return "warning"
    return "pause"


def _cpl_zone(val: float | None) -> str:
    if val is None:       return "no_data"
    if val < CPL_SCALE:   return "scale"
    if val <= CPL_ACCEPTABLE: return "ok"
    if val <= CPL_WARNING:    return "warning"
    return "pause"


def audit_campaign_health(
    days: int = DAYS_FOR_PAUSE_DECISION,
    min_spend: float = 50.0,
    channels: list[str] | None = None,
) -> list[dict]:
    """
    Return one health record per campaign with CPQL zone, CPL zone, and
    a recommended action.

    Measurement:
      - Cost from campaigns_daily (channel source)
      - Leads/SQLs from hubspot_leads_module_daily (Lead Module)
      - HubSpot pre-aggregated by CTE to prevent spend fan-out
    """
    client, project, dataset = _bq_client()

    today = date.today()
    since = (today - timedelta(days=days)).isoformat()
    channel_filter = ""
    if channels:
        ch_list = ", ".join(f"'{c}'" for c in channels)
        channel_filter = f"AND c.channel IN ({ch_list})"

    sql = f"""
        WITH hs AS (
          SELECT
            date,
            lead_utm_campaign,
            SUM(leads_total)     AS leads,
            SUM(leads_qualified) AS sqls
          FROM `{project}.{dataset}.hubspot_leads_module_daily`
          GROUP BY date, lead_utm_campaign
        ),
        deals AS (
          -- Campaign-level revenue from won deals (for ROAS override check)
          SELECT
            deal_utm_campaign,
            SUM(amount_won) AS revenue_won
          FROM `{project}.{dataset}.hubspot_deals_daily`
          WHERE date >= '{since}'
          GROUP BY deal_utm_campaign
        )
        SELECT
          c.channel,
          c.campaign_name,
          c.account_id,
          c.status,
          SUM(c.spend)                                                         AS spend,
          SUM(hs.leads)                                                        AS hs_leads,
          SUM(hs.sqls)                                                         AS sqls,
          SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.leads), 0))                  AS cpl,
          SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls),  0))                  AS cpql,
          SAFE_DIVIDE(SUM(hs.sqls), NULLIF(SUM(hs.leads), 0))                  AS qual_rate,
          MAX(d.revenue_won)                                                    AS revenue_won,
          SAFE_DIVIDE(MAX(d.revenue_won), NULLIF(SUM(c.spend), 0))             AS roas,
          MAX(c.updated_at)                                                     AS last_updated
        FROM `{project}.{dataset}.campaigns_daily` c
        LEFT JOIN hs
          ON  c.date = hs.date
          AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
        LEFT JOIN deals d
          ON  LOWER(c.campaign_name) = LOWER(d.deal_utm_campaign)
        WHERE c.date >= '{since}'
          {channel_filter}
        GROUP BY c.channel, c.campaign_name, c.account_id, c.status
        HAVING SUM(c.spend) >= {min_spend}
        ORDER BY cpql ASC NULLS LAST
    """

    rows = list(client.query(sql).result())
    findings = []
    for r in rows:
        cpql_z = _cpql_zone(r.cpql)
        cpl_z  = _cpl_zone(r.cpl)
        qr     = (r.qual_rate or 0) * 100
        roas   = float(r.roas or 0)
        is_awareness = _is_awareness(r.campaign_name)

        # Days since last campaign edit
        last_updated = r.last_updated
        if last_updated:
            # last_updated is a datetime (UTC) from BQ
            if hasattr(last_updated, "date"):
                last_updated_date = last_updated.date()
            else:
                last_updated_date = last_updated
            days_since_edit = (today - last_updated_date).days
        else:
            days_since_edit = 999  # unknown → treat as stale, allow action

        # Channel-specific CPQL acceptable threshold override
        ch_cpql_ok = CHANNEL_CPQL_ACCEPTABLE.get(r.channel, CPQL_ACCEPTABLE)
        if r.cpql and r.cpql <= ch_cpql_ok and cpql_z in ("warning",):
            cpql_z = "ok"  # downgrade: within channel-specific acceptable range

        # Qflavours flag — needs HubSpot pipeline verification
        is_qflavours = "qflavours" in r.campaign_name.lower()

        # ── Awareness / traffic / reach campaigns ─────────────────────────────
        # Primary KPI: impression share (≥ 25% = healthy).
        # Leads are not expected — do NOT evaluate CPQL/CPL for these.
        if is_awareness:
            action = "review_impression_share"
            note   = (
                "Awareness/traffic campaign — leads not the primary KPI. "
                "Check impression share in platform (target ≥ 25%). "
                "Optimize for reach, frequency, and brand recall. "
                "If impression share < 25%, raise budget or widen targeting."
            )
            findings.append({
                "channel":        r.channel,
                "campaign":       r.campaign_name,
                "account_id":     r.account_id,
                "status":         r.status,
                "days":           days,
                "date_from":      since,
                "date_to":        today.isoformat(),
                "last_updated":   "awareness",
                "days_since_edit": 999,
                "spend":          round(r.spend or 0, 2),
                "hs_leads":       int(r.hs_leads or 0),
                "sqls":           int(r.sqls or 0),
                "cpl":            None,
                "cpql":           None,
                "qual_rate":      0.0,
                "roas":           round(roas, 2),
                "cpql_zone":      "awareness",
                "cpl_zone":       "awareness",
                "junk_leads":     False,
                "is_awareness":   True,
                "is_qflavours":   False,
                "roas_override":  False,
                "action":         action,
                "note":           note,
            })
            continue

        # ── ROAS override ─────────────────────────────────────────────────────
        roas_override = roas >= ROAS_GOOD and roas > 0

        # ── Drill-down trigger ─────────────────────────────────────────────────
        # CPQL > $130 AND CPL > $32 for >= 10 days
        needs_drilldown = (
            (r.cpql or 0) > DRILL_DOWN_CPQL
            and (r.cpl  or 0) > DRILL_DOWN_CPL
            and days >= DRILL_DOWN_DAYS
        )
        drilldown_channel_type = (
            "search" if r.channel in SEARCH_CHANNELS else
            "social" if r.channel in SOCIAL_CHANNELS else
            "unknown"
        )

        # Junk-leads flag: low CPL looks like scale but CPQL says pause/warning.
        junk_leads = (
            cpl_z in ("scale", "ok")
            and cpql_z in ("pause", "warning")
            and qr < QUAL_RATE_TARGET * 100
            and not roas_override
        )

        # ── Action recommendation — CPQL-first, then CPL ──────────────────────
        if needs_drilldown:
            action = "drilldown"
            if drilldown_channel_type == "search":
                note = (
                    f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} above threshold for {days} days. "
                    f"Google Ads drill-down order: "
                    f"1) Keywords — pause if: spend >$35 + 0 conv (14d), OR CPL >$80 + 1+ conv (14d). "
                    f"2) Ad Groups — if >=50% of keywords flagged, pause the group. "
                    f"3) Campaign — pause only if all ad groups are underperforming."
                )
            elif drilldown_channel_type == "social":
                note = (
                    f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} above threshold for {days} days. "
                    f"Social drill-down order: "
                    f"1) Ads — identify highest-CPL / zero-lead ads and pause them. "
                    f"2) Ad Sets — if majority of ads in an ad set are bad, pause the ad set. "
                    f"3) Campaign — pause only if all ad sets are underperforming."
                )
            else:
                note = (
                    f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} above threshold for {days} days. "
                    f"Analyse at ad/placement level before touching campaign."
                )

        elif roas_override and cpql_z in ("warning", "pause"):
            action = "optimize"
            note   = (f"ROAS {roas:.2f} >= {ROAS_GOOD} — revenue covering spend. "
                      f"CPQL ${r.cpql:.2f} above target but justified. "
                      f"Optimize qual rate to improve further.")

        elif cpql_z in ("scale", "ok") and cpl_z in ("scale", "ok"):
            # Scale: CPQL ≤ $95 AND ROAS > 0.8 (both required)
            if SCALE_REQUIRES_ROAS and roas == 0:
                action = "monitor"
                note   = (f"CPQL ${r.cpql:.2f} acceptable but no deal revenue attributed yet. "
                          f"Scale once ROAS > {ROAS_GOOD} is confirmed.")
            elif SCALE_REQUIRES_ROAS and not roas_override:
                action = "monitor"
                note   = (f"CPQL ${r.cpql:.2f} acceptable but ROAS {roas:.2f} < {ROAS_GOOD}. "
                          f"Do not scale until revenue covers spend.")
            else:
                action = "scale"
                note   = (f"CPQL ${r.cpql:.2f} <= $95 and ROAS {roas:.2f} > {ROAS_GOOD}. "
                          f"Scale: raise budget 25%.")

        elif cpql_z in ("scale", "ok") and cpl_z in ("scale", "ok", "warning"):
            action = "monitor"
            note   = f"CPQL ${r.cpql:.2f} acceptable. Monitor CPL ${r.cpl:.2f}."

        elif cpql_z == "warning":
            action = "optimize"
            note   = (f"CPQL ${r.cpql:.2f} in warning zone (>${CPQL_ACCEPTABLE}). "
                      f"Qual rate {qr:.1f}% (target {QUAL_RATE_TARGET*100:.0f}%). "
                      f"Investigate audience/keyword quality before scaling.")

        elif cpql_z == "pause":
            if r.cpql and r.cpql > CPQL_WARNING * 3:
                action = "pause"
                note   = (f"CPQL ${r.cpql:.2f} is {r.cpql/CPQL_WARNING:.1f}x the warning threshold. "
                          f"Qual rate {qr:.1f}%. Pause and investigate.")
            else:
                action = "optimize"
                note   = (f"CPQL ${r.cpql:.2f} in pause zone. Qual rate {qr:.1f}%. "
                          f"Review audience, creatives, and landing page before pausing.")

        elif cpql_z == "no_data":
            if cpl_z == "pause":
                action = "optimize"
                note   = f"No qualified leads yet. CPL ${r.cpl:.2f} in pause zone — check HubSpot attribution."
            else:
                action = "monitor"
                note   = "No qualified leads yet — check HubSpot UTM attribution for this campaign."
        else:
            action = "monitor"
            note   = f"CPQL {cpql_z}, CPL {cpl_z}."

        if junk_leads:
            note += (f" WARNING: CPL ${r.cpl:.2f} looks like scale but qual rate is only "
                     f"{qr:.1f}% — leads are junk. Do not scale on CPL alone.")

        if roas_override:
            note += f" (ROAS {roas:.2f} — revenue covering spend)"

        # Edit-age guard: if last edit < MIN_DAYS_SINCE_EDIT, too early to act
        if action in ("optimize", "pause") and days_since_edit < MIN_DAYS_SINCE_EDIT:
            note = (f"[HOLD — edited {days_since_edit}d ago, need ≥{MIN_DAYS_SINCE_EDIT}d] " + note)
            action = "monitor"  # downgrade; recheck once edit has had time to show results

        # Qflavours note
        if is_qflavours and QFLAVOURS_PIPELINE_CHECK:
            note += " ⚠️ Verify Qflavours leads pipeline in HubSpot has data for this campaign."

        findings.append({
            "channel":        r.channel,
            "campaign":       r.campaign_name,
            "account_id":     r.account_id,
            "status":         r.status,
            "days":           days,
            "date_from":      since,
            "date_to":        today.isoformat(),
            "last_updated":   last_updated_date.isoformat() if last_updated else "unknown",
            "days_since_edit": days_since_edit,
            "spend":          round(r.spend or 0, 2),
            "hs_leads":       int(r.hs_leads or 0),
            "sqls":           int(r.sqls or 0),
            "cpl":            round(r.cpl, 2) if r.cpl else None,
            "cpql":           round(r.cpql, 2) if r.cpql else None,
            "qual_rate":      round(qr, 1),
            "roas":           round(roas, 2),
            "cpql_zone":      cpql_z,
            "cpl_zone":       cpl_z,
            "junk_leads":           junk_leads,
            "is_awareness":         False,
            "is_qflavours":         is_qflavours,
            "roas_override":        roas_override,
            "needs_drilldown":      needs_drilldown,
            "drilldown_channel_type": drilldown_channel_type,
            "action":               action,
            "note":                 note,
        })

    return findings


def print_health_report(findings: list[dict]) -> None:
    """Pretty-print a health report to stdout."""
    ZONE_ICON   = {"scale": "[SCALE]", "ok": "[OK]", "warning": "[WARN]",
                   "pause": "[PAUSE]", "no_data": "[N/A]"}
    ACTION_ICON = {"scale": "^", "monitor": "~", "optimize": "!", "pause": "X"}
    for f in findings:
        cpql_s = f"${f['cpql']:.2f}" if f["cpql"] else "N/A"
        cpl_s  = f"${f['cpl']:.2f}"  if f["cpl"]  else "N/A"
        print(
            f"{ACTION_ICON.get(f['action'], '?')} [{f['action'].upper():8s}] "
            f"{f['channel']:<12} | {f['campaign'][:45]:<45} | "
            f"spend=${f['spend']:>8.0f} | leads={f['hs_leads']:>4} sqls={f['sqls']:>3} | "
            f"CPQL={cpql_s:>8} {ZONE_ICON.get(f['cpql_zone'],''):8s} | "
            f"CPL={cpl_s:>7} {ZONE_ICON.get(f['cpl_zone'],''):8s} | "
            f"qual={f['qual_rate']:>5.1f}%"
        )


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else DAYS_FOR_PAUSE_DECISION
    findings = audit_campaign_health(days=days)
    print(f"\nCampaign health — last {days} days "
          f"(cost: channel | leads: HubSpot Lead Module)\n{'='*120}")
    print_health_report(findings)
    print(f"\n{len(findings)} campaigns evaluated.")
    scale   = [f for f in findings if f["action"] == "scale"]
    pause   = [f for f in findings if f["action"] == "pause"]
    opt     = [f for f in findings if f["action"] == "optimize"]
    print(f"  Scale: {len(scale)}  |  Optimize: {len(opt)}  |  Pause: {len(pause)}")
