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
    # Lag-aware CPQL: exclude days where open_leads/leads_total > 30% (SDR
    # backlog). Volume metrics (spend, leads) still use the full window;
    # only CPQL math is suppressed on lag-affected days.
    from analysers.lag_aware import lag_clean_filter_sql, lag_excluded_days_sql
    LAG_OK = lag_clean_filter_sql(open_col="leads_open", leads_col="leads_total")
    LAG_EXC = lag_excluded_days_sql(open_col="leads_open", leads_col="leads_total")
    q = f"""
      WITH base AS (
        SELECT *
        FROM `{PROJECT_ID}.{DATASET}.wide_ads`
        WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
          AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
      ),
      per_channel AS (
        SELECT channel,
          ROUND(SUM(spend), 0) AS spend,
          SUM(leads_total) AS leads,
          SUM(leads_qualified)   AS qual,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)), 0) AS cpl,
          ROUND(SAFE_DIVIDE(
            SUM(IF({LAG_OK}, spend, 0)),
            NULLIF(SUM(IF({LAG_OK}, leads_qualified, 0)), 0)
          ), 0) AS cpql,
          {LAG_EXC} AS lag_excluded_days
        FROM base
        GROUP BY channel
      ),
      total AS (
        SELECT
          ROUND(SUM(spend), 0)   AS spend,
          SUM(leads_total)       AS leads,
          SUM(leads_qualified)   AS qual,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_total), 0)), 0) AS cpl,
          ROUND(SAFE_DIVIDE(
            SUM(IF({LAG_OK}, spend, 0)),
            NULLIF(SUM(IF({LAG_OK}, leads_qualified, 0)), 0)
          ), 0) AS cpql,
          {LAG_EXC} AS lag_excluded_days
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
                "lag_excluded_days": int(t.get("lag_excluded_days") or 0),
            },
            "channels": [
                {
                    "channel": c["channel"],
                    "spend":   int(c["spend"] or 0),
                    "leads":   int(c["leads"] or 0),
                    "qual":    int(c["qual"]  or 0),
                    "cpl":     int(c["cpl"])  if c["cpl"]  is not None else 0,
                    "cpql":    int(c["cpql"]) if c["cpql"] is not None else 0,
                    "lag_excluded_days": int(c.get("lag_excluded_days") or 0),
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


def _overdue_task_count() -> int:
    """Return count of incomplete Asana tasks whose due date has passed."""
    try:
        import asana
        from executors.asana_maintenance import _get_client, _all_project_ids
        from datetime import date as _date
        client = _get_client()
        today  = _date.today()
        count  = 0
        for pid in _all_project_ids():
            try:
                api   = asana.TasksApi(client)
                tasks = api.get_tasks_for_project(
                    pid,
                    {"completed_since": "now", "opt_fields": "due_on,completed", "limit": 100},
                )
                for t in tasks:
                    due = t.get("due_on")
                    if due and not t.get("completed"):
                        try:
                            if _date.fromisoformat(due) < today:
                                count += 1
                        except ValueError:
                            pass
            except Exception:
                pass
        return count
    except Exception:
        return 0


def _agent_actions_lines(audit_tasks: list, health_tasks: list) -> list[str]:
    """
    What was sent to #approvals tonight — category × count only, no campaign names.
    Counts use len() directly since tasks are now one-per-campaign.
    """
    parts = []

    scale     = sum(1 for t in health_tasks if str(t[0]).startswith("scale-pending"))
    pause     = sum(1 for t in health_tasks if str(t[0]).startswith("pause-pending"))
    junk      = sum(1 for t in health_tasks if "junk-leads" in str(t[0]))
    optimize  = sum(1 for t in health_tasks if str(t[0]).startswith("optimize"))
    drilldown = sum(1 for t in health_tasks if str(t[0]).startswith("drilldown"))

    if scale:     parts.append(f"Scale ×{scale}")
    if pause:     parts.append(f"Pause ×{pause}")
    if junk:      parts.append(f"Junk ×{junk}")
    if optimize:  parts.append(f"Optimize ×{optimize}")
    if drilldown: parts.append(f"Drill-down ×{drilldown}")

    kw_paused = sum(1 for t in audit_tasks if "kw-auto-paused" in str(t[0]))
    negatives = sum(1 for t in audit_tasks if str(t[0]).startswith("negatives"))
    is_audit  = sum(1 for t in audit_tasks if str(t[0]).startswith("IS audit"))
    qs_audit  = sum(1 for t in audit_tasks if str(t[0]).startswith("QS audit"))
    kw_expand = sum(1 for t in audit_tasks if str(t[0]).startswith("keyword expansion"))

    if kw_paused: parts.append(f"KW pause ×{kw_paused}")
    if negatives: parts.append(f"Negatives ×{negatives}")
    if is_audit:  parts.append(f"IS ×{is_audit}")
    if qs_audit:  parts.append(f"QS ×{qs_audit}")
    if kw_expand: parts.append(f"KW expand ×{kw_expand}")

    return ["  " + "  ·  ".join(parts)] if parts else []


def _peak_numbers_lines() -> list[str]:
    """Channel-level spend / leads / CPQL for last 7 days. No campaign names."""
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    except Exception:
        return []
    try:
        from analysers.lag_aware import lag_clean_filter_sql
        # Filter applies to the HubSpot leads side, so column names are leads / open_
        LAG_OK_HS  = lag_clean_filter_sql(open_col="hs.open_", leads_col="hs.leads")
        # Count DISTINCT lag-affected calendar days (not campaign-day pairs)
        # so the displayed "Nd excl" matches user intuition.
        LAG_EXC_HS = (
            f"COUNT(DISTINCT IF(SAFE_DIVIDE(COALESCE(hs.open_, 0), NULLIF(hs.leads, 0)) > 0.30, c.date, NULL))"
        )
        client = get_client()
        rows = list(client.query(f"""
            -- Pre-aggregate campaigns_daily to ONE row per (date, channel, campaign_name).
            -- Without this, multi-account setups (2 Google Ads accounts with the same
            -- campaign_name on the same date) would fan-out HubSpot lead rows and inflate
            -- leads / deflate CPQL in the Slack summary.
            WITH cd AS (
              SELECT date, channel, campaign_name, SUM(spend) AS spend
              FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
              WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
                AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
                AND spend > 0
              GROUP BY date, channel, campaign_name
            ),
            hs AS (
              SELECT date, lead_utm_campaign,
                     SUM(leads_total)     AS leads,
                     SUM(leads_qualified) AS sqls,
                     SUM(leads_open)      AS open_
              FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
              GROUP BY date, lead_utm_campaign
            )
            SELECT
              COALESCE(m.display_name, c.channel)                                   AS channel,
              ROUND(SUM(c.spend), 0)                                                AS spend,
              COALESCE(SUM(hs.leads), 0)                                            AS leads,
              COALESCE(SUM(hs.sqls), 0)                                             AS sqls,
              ROUND(SAFE_DIVIDE(
                SUM(IF({LAG_OK_HS}, c.spend, 0)),
                NULLIF(SUM(IF({LAG_OK_HS}, hs.sqls, 0)), 0)
              ), 0) AS cpql,
              {LAG_EXC_HS} AS lag_excluded_days
            FROM cd c
            LEFT JOIN hs ON c.date = hs.date
                        AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
            LEFT JOIN `{PROJECT_ID}.{DATASET}.v_channel_key_map` m
                   ON c.channel = m.paid_channel
            GROUP BY 1
            ORDER BY spend DESC
        """).result())
    except Exception as e:
        print(f"[daily-summary] peak_numbers BQ query failed: {e}")
        return []

    # channel totals — no campaign names
    from analysers.lag_aware import format_cpql_with_lag
    lines = []
    for r in rows:
        spend_s = f"${int(r.spend):,}"
        leads_s = str(int(r.leads)) if r.leads else "0"
        cpql_val = int(r.cpql) if r.cpql else None
        lag_d    = int(getattr(r, "lag_excluded_days", 0) or 0)
        cpql_s   = "CPQL " + format_cpql_with_lag(cpql_val, lag_d) if (cpql_val or lag_d) else "no SQLs"
        lines.append(f"  *{r.channel}*  {spend_s}  ·  {leads_s} leads  ·  {cpql_s}")
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
    """Clean, human-readable daily summary for #notify."""
    riyadh    = timezone(timedelta(hours=3))
    today_str = datetime.now(riyadh).strftime("%d %b %Y")
    # Dashboard URLs — must be set in .env / Railway secrets
    url          = os.getenv("DASHBOARD_URL") or "https://app.hex.tech"
    activity_url = os.getenv("ACTIVITY_DASHBOARD_URL") or "https://app.hex.tech"

    counts       = _asana_task_counts()
    action_lines = _agent_actions_lines(audit_tasks or [], health_tasks or [])
    peak_lines   = _peak_numbers_lines()
    spike_lines  = _spike_lines(spikes or [])
    overdue      = _overdue_task_count()

    lines = [f"*{today_str}  ·  <{url}|Dashboard>  ·  <{activity_url}|Activity>*", ""]

    # ── Performance — channel totals, no campaign names ───────────────────────
    if peak_lines:
        lines.append("*7d Performance*")
        lines.extend(peak_lines)
        lines.append("")

    # ── Alerts ───────────────────────────────────────────────────────────────
    if spike_lines:
        lines.append("*Alerts*")
        lines.extend(spike_lines)
        lines.append("")

    # ── What was sent to approvals — category × count only ───────────────────
    if action_lines:
        lines.append("*→ #approvals*  " + action_lines[0].strip())
        lines.append("")

    # ── Asana one-liner ───────────────────────────────────────────────────────
    new_tasks     = counts.get("created_today", 0)
    total_pending = sum(n for _, n in counts.get("pending_by_project", []))
    asana_line    = f"*Asana:*  {new_tasks} new  ·  {total_pending} pending"
    if overdue:
        asana_line += f"  ·  {overdue} overdue"
    lines.append(asana_line)

    return "\n".join(lines)


def build_recommendations_text(findings: list) -> str:
    """
    Second Slack message: live task category summary from Asana.

    Format per category:
        <icon> *Category*   X done  /  Y pending

    Data range and edit-guard note included at the top.
    Falls back to findings-only counts if Asana query fails.
    """
    # Date range from current findings
    date_from  = next((f.get("date_from") for f in findings if f.get("date_from")), "")
    date_to    = next((f.get("date_to")   for f in findings if f.get("date_to")),   "")
    date_range = f"{date_from} to {date_to}" if date_from and date_to else ""
    held_n     = sum(1 for f in findings if "HOLD" in (f.get("note") or ""))

    # ── Pull live counts from Asana ───────────────────────────────────────────
    try:
        from executors.asana_maintenance import (
            get_task_category_summary, _CATEGORY_ORDER, _CATEGORY_ICON,
        )
        summary = get_task_category_summary(since_days=7)
    except Exception as e:
        print(f"[daily_summary] Asana category query failed, falling back: {e}")
        summary = None

    # Build compact category chips: icon+name  X done / Y pending
    def _chip(icon: str, label: str, done: int, pending: int) -> str:
        parts = []
        if done:    parts.append(f"{done} done")
        if pending: parts.append(f"{pending} pending")
        return f"{icon} {label}: " + "  /  ".join(parts) if parts else ""

    chips: list[str] = []
    if summary:
        for cat in _CATEGORY_ORDER:
            if cat not in summary:
                continue
            counts  = summary[cat]
            done    = counts.get("done", 0)
            pending = counts.get("pending", 0)
            if done == 0 and pending == 0:
                continue
            icon = _CATEGORY_ICON.get(cat, ":clipboard:")
            chips.append(_chip(icon, cat, done, pending))
    else:
        from executors.asana_maintenance import _CATEGORY_ICON
        for cat, action_key, flag_key in [
            ("Scale",      "scale",     None),
            ("Pause",      "pause",     None),
            ("Drill-down", "drilldown", None),
            ("Optimize",   "optimize",  None),
            ("Junk Leads", None,        "junk_leads"),
            ("Awareness",  None,        "is_awareness"),
        ]:
            n = sum(1 for f in findings if (
                (action_key and f.get("action") == action_key) or
                (flag_key   and f.get(flag_key))
            ))
            if n:
                icon = _CATEGORY_ICON.get(cat, ":clipboard:")
                chips.append(_chip(icon, cat, 0, n))

    if not chips:
        return ""

    # Line 1: header + date range
    header = f"*Tasks (7d)*"
    if date_range:
        header += f"  _{date_range}_"
    if held_n:
        header += f"  :hourglass: {held_n} on hold"

    # Line 2: all chips on one line, pipe-separated
    chips_line = "  |  ".join(c for c in chips if c)

    lines = [header, chips_line, "_Asana · #approvals_"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_daily_summary_text())
