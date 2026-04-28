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
)


def _bq_client():
    project  = os.getenv("BQ_PROJECT_ID")
    dataset  = os.getenv("BQ_DATASET", "qoyod_marketing")
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
    creds    = service_account.Credentials.from_service_account_file(key_path)
    return bigquery.Client(project=project, credentials=creds), project, dataset


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

    since = (date.today() - timedelta(days=days)).isoformat()
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
        )
        SELECT
          c.channel,
          c.campaign_name,
          c.account_id,
          c.status,
          SUM(c.spend)                                                    AS spend,
          SUM(hs.leads)                                                   AS hs_leads,
          SUM(hs.sqls)                                                    AS sqls,
          SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.leads), 0))             AS cpl,
          SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls),  0))             AS cpql,
          SAFE_DIVIDE(SUM(hs.sqls), NULLIF(SUM(hs.leads), 0))             AS qual_rate
        FROM `{project}.{dataset}.campaigns_daily` c
        LEFT JOIN hs
          ON  c.date = hs.date
          -- LinkedIn: utm_campaign maps to campaign GROUP name, not campaign name
         AND  LOWER(CASE WHEN c.channel = 'linkedin'
                         THEN c.campaign_group_name
                         ELSE c.campaign_name END) = LOWER(hs.lead_utm_campaign)
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

        # Junk-leads flag: low CPL looks like scale but CPQL says pause/warning.
        # Low CPL = cheap leads; low qual rate = most leads are junk.
        # Never scale on CPL alone — CPQL is the real signal.
        junk_leads = (
            cpl_z in ("scale", "ok")
            and cpql_z in ("pause", "warning")
            and qr < QUAL_RATE_TARGET * 100
        )

        # Action recommendation — CPQL-first, then CPL
        if cpql_z == "scale" and cpl_z == "scale":
            action = "scale"
            note   = f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} both in scale zone. Raise budget 25%."
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
                note   = f"No SQLs yet. CPL ${r.cpl:.2f} is in pause zone — check HubSpot attribution."
            else:
                action = "monitor"
                note   = "No SQLs yet — check HubSpot UTM attribution for this campaign."
        else:
            action = "monitor"
            note   = f"CPQL {cpql_z}, CPL {cpl_z}."

        if junk_leads:
            note += (f" WARNING: CPL ${r.cpl:.2f} looks like scale but qual rate is only "
                     f"{qr:.1f}% — leads are junk. Do not scale on CPL alone.")

        findings.append({
            "channel":       r.channel,
            "campaign":      r.campaign_name,
            "account_id":    r.account_id,
            "status":        r.status,
            "days":          days,
            "spend":         round(r.spend or 0, 2),
            "hs_leads":      int(r.hs_leads or 0),
            "sqls":          int(r.sqls or 0),
            "cpl":           round(r.cpl, 2) if r.cpl else None,
            "cpql":          round(r.cpql, 2) if r.cpql else None,
            "qual_rate":     round(qr, 1),
            "cpql_zone":     cpql_z,
            "cpl_zone":      cpl_z,
            "junk_leads":    junk_leads,
            "action":        action,
            "note":          note,
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
