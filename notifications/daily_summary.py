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
    """Last 7d ending yesterday — single source of truth via paid_channel_daily."""
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
      )
      SELECT
        ROUND(SUM(spend), 0)              AS spend,
        SUM(leads)                        AS leads,
        SUM(qualified)                    AS qual,
        SUM(open_leads)                   AS open_l,
        ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)),     0) AS cpl,
        ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(qualified), 0)), 0) AS cpql
      FROM base
    """
    try:
        rows = list(client.query(q).result())
        if not rows:
            return None
        r = rows[0]
        return {
            "spend": int(r.spend or 0),
            "leads": int(r.leads or 0),
            "qual":  int(r.qual or 0),
            "open":  int(r.open_l or 0),
            "cpl":   int(r.cpl)  if r.cpl  is not None else 0,
            "cpql":  int(r.cpql) if r.cpql is not None else 0,
        }
    except Exception as e:
        print(f"[daily-summary] BQ headline fetch failed: {e}")
        return None


# ─── The message itself ──────────────────────────────────────────────────────

def build_daily_summary_text(spike_count: int = 0) -> str:
    """One short Slack message string. Markdown.  No more than 12 lines."""
    riyadh = timezone(timedelta(hours=3))
    yesterday = (datetime.now(riyadh) - timedelta(days=1)).strftime("%d %b")
    domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN")
              or "nexa-web-production-c859.up.railway.app")
    url = f"https://{domain}/reports/latest"

    h = _headline_numbers()
    counts = _asana_task_counts()

    lines = [f"*Daily Report — {yesterday}*  <{url}|open dashboard>"]
    if h:
        lines.append(
            f"7d: ${h['spend']:,} spent · {h['leads']:,} leads · "
            f"{h['qual']:,} qual · CPL ${h['cpl']} · CPQL ${h['cpql']}"
        )
    lines.append(f"Tasks created today: {counts['created_today']}")
    if counts["pending_by_project"]:
        for proj, n in counts["pending_by_project"]:
            lines.append(f"  • {proj}: {n} pending")
    if spike_count > 0:
        lines.append(f"Anomalies detected: {spike_count} (see dashboard)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_daily_summary_text())
