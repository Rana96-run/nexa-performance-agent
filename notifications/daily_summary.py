"""
notifications/daily_summary.py
==============================
Builds the ONE Slack message posted at the end of the nightly cycle.

Design rules (per Amar):
- Short. Under 12 lines.
- No emoji spam. Up to 2 inline icons total.
- Headline numbers first (spend / leads / qual / CPL).
- Tasks created today + pending per project (top 5).
- Dashboard URL.
- Spike alerts merged inline if any.

The message goes to SLACK_CHANNEL_NOTIFY only.  Approval requests still
go to SLACK_CHANNEL_APPROVAL separately (different urgency, different
audience).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

# ─── Asana task counts ────────────────────────────────────────────────────────

def _asana_task_counts() -> dict:
    """
    Return {
        "created_today": int,
        "pending_by_project": [(project_name, n_pending), ...]   # top 5 by count
    }
    Pulled live from Asana.
    """
    import requests
    token = os.getenv("ASANA_ACCESS_TOKEN")
    if not token:
        return {"created_today": 0, "pending_by_project": []}
    H = {"Authorization": f"Bearer {token}"}

    # Project IDs we care about (stay in sync with config.ASANA_*_PROJECTS)
    PROJECTS = {
        "Daily Performance Review":      "1214135581886045",
        "Budget Pacing & Alerts":        "1214135615047733",
        "Creative Refresh & QA":         "1214135615054862",
        "Keyword & Placement Audit":     "1214135581961690",
        "Conversion Tracking & CRM Sync": "1214135615075674",
        "Competitive & Market Monitoring": "1214135604475705",
        "Google Ads Optimization":       "1213239419217795",
        "Meta Ads (Recovery)":           "1213280413868927",
        "Snapchat Ads Optimization":     "1214135546324721",
        "TikTok Ads Optimization":       "1214135614950965",
        "LinkedIn Ads Optimization":     "1214135614968862",
        "YouTube Ads Optimization":      "1214135614991277",
        "Bing Ads Scaling":              "1213294555250809",
    }

    # "Today" = since yesterday midnight Riyadh in ISO
    riyadh = timezone(timedelta(hours=3))
    cutoff = (datetime.now(riyadh) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    created_today = 0
    pending_counts: list[tuple[str, int]] = []
    for name, pid in PROJECTS.items():
        try:
            r = requests.get(
                f"https://app.asana.com/api/1.0/projects/{pid}/tasks",
                params={
                    "opt_fields": "name,created_at,completed",
                    "limit":      100,
                },
                headers=H, timeout=10,
            )
            tasks = r.json().get("data", [])
        except Exception:
            continue

        n_pending = sum(1 for t in tasks if not t.get("completed"))
        n_today = sum(1 for t in tasks
                      if (t.get("created_at") or "") >= cutoff)
        created_today += n_today
        if n_pending > 0:
            pending_counts.append((name, n_pending))

    pending_counts.sort(key=lambda x: -x[1])
    return {"created_today": created_today,
            "pending_by_project": pending_counts[:5]}


# ─── BQ headline numbers (from the unified view) ─────────────────────────────

def _headline_numbers() -> Optional[dict]:
    """Last 7d ending yesterday — totals AND per-channel breakdown."""
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    except Exception:
        return None
    client = get_client()
    q = f"""
      WITH base AS (
        SELECT *
        FROM `{PROJECT_ID}.{DATASET}.paid_channel_daily`
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
          AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
      ),
      per_channel AS (
        SELECT channel,
          ROUND(SUM(spend), 0) AS spend,
          SUM(leads)    AS leads,
          SUM(qualified) AS qual,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)),     0) AS cpl,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)), 0) AS cpql
        FROM base
        GROUP BY channel
      ),
      total AS (
        SELECT
          ROUND(SUM(spend), 0)  AS spend,
          SUM(leads)            AS leads,
          SUM(qualified)        AS qual,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)),     0) AS cpl,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)), 0) AS cpql
        FROM base
      )
      SELECT
        (SELECT AS STRUCT * FROM total)         AS total,
        ARRAY(
          SELECT AS STRUCT * FROM per_channel
          WHERE spend > 0
          ORDER BY spend DESC
        ) AS channels
    """
    try:
        rows = list(client.query(q).result())
        if not rows:
            return None
        r = rows[0]
        t = dict(r["total"])
        return {
            "total": {
                "spend": int(t.get("spend") or 0),
                "leads": int(t.get("leads") or 0),
                "qual":  int(t.get("qual") or 0),
                "cpl":   int(t.get("cpl"))  if t.get("cpl")  is not None else 0,
                "cpql":  int(t.get("cpql")) if t.get("cpql") is not None else 0,
            },
            "channels": [
                {
                    "channel": c["channel"],
                    "spend":   int(c["spend"] or 0),
                    "leads":   int(c["leads"] or 0),
                    "qual":    int(c["qual"]  or 0),
                    "cpl":     int(c["cpl"])  if c["cpl"]  is not None else 0,
                    "cpql":    int(c["cpql"]) if c["cpql"] is not None else 0,
                }
                for c in r["channels"]
            ],
        }
    except Exception as e:
        print(f"[daily-summary] BQ headline fetch failed: {e}")
        return None


# ─── The message itself ──────────────────────────────────────────────────────

def _extract_n(label: str) -> str:
    """Pull the number from 'scale-executed (3)' -> '3'. Returns '' if not found."""
    if "(" in label and ")" in label:
        return label.split("(")[1].split(")")[0].strip()
    return ""


def _agent_actions_lines(audit_tasks: list, health_tasks: list) -> list[str]:
    """
    Summarise what the agent actually did tonight in 1–6 bullet lines.
    Both lists are [(label, gid), ...].  Action type is inferred from label.
    """
    lines = []

    # ── Campaign health (all channels) ────────────────────────────────────────
    scaled   = [t for t in health_tasks if str(t[0]).startswith("scale-executed")]
    paused   = [t for t in health_tasks if str(t[0]).startswith("pause-executed")]
    junk     = [t for t in health_tasks if "junk-leads" in str(t[0])]
    optimize = [t for t in health_tasks if str(t[0]).startswith("optimize")]

    if scaled:
        n = _extract_n(scaled[0][0])
        lines.append(f"  • Scaled {n} campaign(s) +25% (CPQL + CPL both in scale zone) — executed")
    if paused:
        n = _extract_n(paused[0][0])
        lines.append(f"  • Paused {n} campaign(s) (CPQL critical) — executed")
    if junk:
        n = _extract_n(junk[0][0])
        lines.append(f"  • {n} junk-leads alert(s) — low qual rate despite cheap CPL")
    if optimize:
        lines.append(f"  • {len(optimize)} channel(s) have optimization recommendations in Asana")

    # ── Google Ads audit ──────────────────────────────────────────────────────
    kw_paused = [t for t in audit_tasks if "kw-auto-paused" in str(t[0])]
    negatives = [t for t in audit_tasks if str(t[0]).startswith("negatives")]
    is_audit  = [t for t in audit_tasks if str(t[0]).startswith("IS audit")]
    qs_audit  = [t for t in audit_tasks if str(t[0]).startswith("QS audit")]
    kw_expand = [t for t in audit_tasks if str(t[0]).startswith("keyword expansion")]

    gads_parts = []
    if is_audit:  gads_parts.append(f"Impression Share flagged {_extract_n(is_audit[0][0])} campaigns")
    if qs_audit:  gads_parts.append(f"Quality Score flagged {_extract_n(qs_audit[0][0])} keywords")
    if kw_expand: gads_parts.append(f"{_extract_n(kw_expand[0][0])} search terms ready to add as keywords")
    if negatives: gads_parts.append(f"{_extract_n(negatives[0][0])} negative keywords to add")
    if kw_paused: gads_parts.append(f"{_extract_n(kw_paused[0][0])} non-converting keywords auto-paused — executed")
    if gads_parts:
        for part in gads_parts:
            lines.append(f"  • Google Ads: {part}")

    return lines


def _peak_numbers_lines() -> list[str]:
    """
    For each active channel, show the best campaign (lowest CPQL) and
    worst campaign (highest CPQL) over the last 7 days.
    Campaigns with no SQLs are excluded from best; worst shows N/A CPQL if no SQLs.
    """
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    except Exception:
        return []
    try:
        client = get_client()
        # Per-campaign CPQL over last 7d, pre-aggregating HubSpot to avoid fan-out
        rows = list(client.query(f"""
            WITH hs AS (
              SELECT date, lead_utm_campaign,
                     SUM(leads_qualified) AS sqls
              FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
              GROUP BY date, lead_utm_campaign
            ),
            camp AS (
              SELECT
                c.channel,
                c.campaign_name,
                SUM(c.spend) AS spend,
                SUM(hs.sqls) AS sqls,
                SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0)) AS cpql
              FROM `{PROJECT_ID}.{DATASET}.campaigns_daily` c
              LEFT JOIN hs
                ON c.date = hs.date
               AND LOWER(CASE WHEN c.channel = 'linkedin'
                              THEN IFNULL(c.campaign_group_name, c.campaign_name)
                              ELSE c.campaign_name END) = LOWER(hs.lead_utm_campaign)
              WHERE c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                AND c.date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
              GROUP BY c.channel, c.campaign_name
              HAVING SUM(c.spend) >= 20
            ),
            ranked AS (
              SELECT *,
                ROW_NUMBER() OVER (PARTITION BY channel ORDER BY cpql ASC NULLS LAST)  AS rn_best,
                ROW_NUMBER() OVER (PARTITION BY channel ORDER BY cpql DESC NULLS FIRST) AS rn_worst
              FROM camp
            )
            SELECT channel, campaign_name, spend, sqls, cpql,
                   rn_best, rn_worst
            FROM ranked
            WHERE rn_best = 1 OR rn_worst = 1
            ORDER BY channel, rn_best
        """).result())
    except Exception as e:
        err = str(e)
        if "campaign_group_name not found" in err:
            # Column added recently — retry without LinkedIn-specific join
            try:
                rows = list(client.query(f"""
                    WITH hs AS (
                      SELECT date, lead_utm_campaign, SUM(leads_qualified) AS sqls
                      FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
                      GROUP BY date, lead_utm_campaign
                    ),
                    camp AS (
                      SELECT c.channel, c.campaign_name,
                             SUM(c.spend) AS spend, SUM(hs.sqls) AS sqls,
                             SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.sqls), 0)) AS cpql
                      FROM `{PROJECT_ID}.{DATASET}.campaigns_daily` c
                      LEFT JOIN hs ON c.date = hs.date
                                  AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
                      WHERE c.date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                        AND c.date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
                      GROUP BY c.channel, c.campaign_name HAVING SUM(c.spend) >= 20
                    ),
                    ranked AS (
                      SELECT *, ROW_NUMBER() OVER (PARTITION BY channel ORDER BY cpql ASC NULLS LAST) AS rn_best,
                                ROW_NUMBER() OVER (PARTITION BY channel ORDER BY cpql DESC NULLS FIRST) AS rn_worst
                      FROM camp
                    )
                    SELECT channel, campaign_name, spend, sqls, cpql, rn_best, rn_worst
                    FROM ranked WHERE rn_best = 1 OR rn_worst = 1 ORDER BY channel
                """).result())
            except Exception as e2:
                print(f"[daily-summary] peak_numbers fallback also failed: {e2}")
                return []
        else:
            print(f"[daily-summary] peak_numbers BQ query failed: {e}")
            return []

    # Group into {channel: {best, worst}}
    from collections import defaultdict
    by_channel: dict = defaultdict(dict)
    for r in rows:
        name  = r.campaign_name or ""
        cpql  = f"${r.cpql:.0f}" if r.cpql else "no SQLs"
        label = f"{name} · CPQL {cpql}"
        if r.rn_best == 1:
            by_channel[r.channel]["best"] = label
        if r.rn_worst == 1:
            by_channel[r.channel]["worst"] = label

    lines = []
    for channel in sorted(by_channel):
        d = by_channel[channel]
        best  = d.get("best",  "—")
        worst = d.get("worst", "—")
        lines.append(f"  *{channel}*")
        lines.append(f"    top:   {best}")
        if best != worst:
            lines.append(f"    worst: {worst}")
    return lines


def _spike_lines(spikes: list) -> list[str]:
    """Format spike detector results into readable one-liners."""
    lines = []
    for s in spikes:
        ch  = s.get("channel", "?")
        m   = s.get("metric", "?")
        dir_ = s.get("direction", "")
        arrow = "(+)" if dir_ == "up" else "(-)"
        if m == "spend":
            pct = s.get("pct", 0)
            lines.append(f"  • {ch}: spend {arrow}{abs(pct):.0f}% vs 7d avg "
                         f"(${s.get('yesterday', 0):.0f} vs ${s.get('baseline', 0):.0f} avg)")
        elif m == "leads":
            pct = s.get("pct", 0)
            lines.append(f"  • {ch}: leads {arrow}{abs(pct):.0f}% vs 7d avg "
                         f"({s.get('yesterday', 0)} vs {s.get('baseline', 0):.1f} avg)")
        elif m == "qualified_rate":
            pp = s.get("pp", 0)
            lines.append(f"  • {ch}: qual rate {arrow}{abs(pp):.0f}pp "
                         f"({s.get('yesterday_pct', 0):.0f}% vs {s.get('baseline_pct', 0):.0f}% avg)")
        elif m == "disqualified_rate":
            pp = s.get("pp", 0)
            lines.append(f"  • {ch}: disqual rate {arrow}{abs(pp):.0f}pp "
                         f"({s.get('yesterday_pct', 0):.0f}% vs {s.get('baseline_pct', 0):.0f}% avg)")
    return lines


def build_daily_summary_text(spikes: list | None = None,
                              audit_tasks: list | None = None,
                              health_tasks: list | None = None) -> str:
    """One short Slack message string. Markdown."""
    riyadh = timezone(timedelta(hours=3))
    today_str = datetime.now(riyadh).strftime("%d %b %Y")
    domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN")
              or "nexa-web-production-c859.up.railway.app")
    url = f"https://{domain}/paid-performance/latest"

    counts = _asana_task_counts()
    action_lines = _agent_actions_lines(audit_tasks or [], health_tasks or [])
    peak_lines   = _peak_numbers_lines()
    spike_lines  = _spike_lines(spikes or [])

    # Dashboard URL always visible as plain text
    lines = [
        f"*Daily Report — {today_str}*",
        f"Dashboard: {url}",
    ]

    if peak_lines:
        lines.append("*Peak numbers (7d CPQL):*")
        lines.extend(peak_lines)

    if action_lines:
        lines.append("*Agent actions:*")
        lines.extend(action_lines)

    if spike_lines:
        lines.append("*Performance alerts vs 7d avg:*")
        lines.extend(spike_lines)

    lines.append(f"Asana tasks created today: {counts['created_today']}")
    if counts["pending_by_project"]:
        for proj, n in counts["pending_by_project"]:
            lines.append(f"  • {proj}: {n} pending")

    return "\n".join(lines)


def build_recommendations_text(findings: list) -> str:
    """
    Second Slack message: task count summary only (no campaign-by-campaign list).
    Full details are in Asana. Approval requests go to #approvals separately.

    Shows:
      - Date range the data covers
      - Last edit cutoff note (actions only taken if edit ≥ 7 days ago)
      - Count breakdown by action type
    """
    if not findings:
        return ""

    actionable = [f for f in findings
                  if f.get("action") not in ("monitor", "scale", "review_impression_share")]
    if not actionable:
        return ""

    pause_n    = sum(1 for f in actionable if f.get("action") == "pause")
    optimize_n = sum(1 for f in actionable if f.get("action") == "optimize")
    drill_n    = sum(1 for f in actionable if f.get("action") == "drilldown")
    junk_n     = sum(1 for f in actionable if f.get("junk_leads"))
    aware_n    = sum(1 for f in findings   if f.get("is_awareness"))
    held_n     = sum(1 for f in findings   if "HOLD" in (f.get("note") or ""))

    # Date range from findings
    date_from = next((f.get("date_from") for f in findings if f.get("date_from")), "")
    date_to   = next((f.get("date_to")   for f in findings if f.get("date_to")),   "")
    date_range = f"{date_from} to {date_to}" if date_from and date_to else ""

    lines = ["*Recommended actions* — full details in Asana, approval requests in #approvals"]
    if date_range:
        lines.append(f"  Data: {date_range}  |  Only acting on campaigns edited ≥7 days ago")
    if pause_n:
        lines.append(f"  :octagonal_sign: *{pause_n}* campaign(s) flagged for pause")
    if drill_n:
        lines.append(f"  :microscope: *{drill_n}* campaign(s) need ad/keyword drill-down first")
    if junk_n:
        lines.append(f"  :warning: *{junk_n}* campaign(s) with junk-leads pattern")
    if optimize_n:
        lines.append(f"  :mag: *{optimize_n}* campaign(s) need optimization review")
    if aware_n:
        lines.append(f"  :eyes: *{aware_n}* awareness/traffic campaign(s) — check impression share")
    if held_n:
        lines.append(f"  :hourglass: *{held_n}* campaign(s) on hold (edited < 7 days ago — recheck later)")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_daily_summary_text())
