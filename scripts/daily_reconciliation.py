"""
Daily BQ ↔ HubSpot reconciliation alarm
========================================
Runs every morning at 08:00 Riyadh. Compares the last 7 days of paid leads in
BQ (`hubspot_leads_module_daily`) vs HubSpot's Leads object (0-136) pulled
live via API. If any day drifts more than 5% AND more than 5 leads in absolute
terms, posts a #approvals Slack alert with the table of deltas.

Why: this catches every class of silent failure within 24h:
  - collector crashes (kwargs mismatch, API down, token expired)
  - parallel sync duplications
  - stale materialized views
  - HubSpot workflow changes that shift lead_qoyod_source distribution

Established 2026-05-13 after the leads collector silently failed for 36h.
Run: `railway run python scripts/daily_reconciliation.py`
"""
import os
import sys
import requests
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")

PAID_SOURCES = (
    "Google Ads",
    "Meta Ads",
    "Snapchat Ads",
    "Tiktok Ads",
    "Microsoft Ads",
)

# Drift thresholds — both must be exceeded to alert
DRIFT_PCT_THRESHOLD = 5.0   # % drift
DRIFT_ABS_THRESHOLD = 5     # absolute lead count drift


def _bq_paid_leads_per_day(client, project_id: str, dataset: str,
                            start: date, end: date) -> dict[str, int]:
    """Return {date_str: leads_total} for paid channels in BQ."""
    sources = ",".join(f"'{s}'" for s in PAID_SOURCES)
    sql = f"""
    SELECT date, SUM(leads_total) AS leads
    FROM `{project_id}.{dataset}.hubspot_leads_module_daily`
    WHERE date BETWEEN '{start}' AND '{end}'
      AND qoyod_source IN ({sources})
    GROUP BY date
    """
    return {str(r.date): r.leads for r in client.query(sql).result()}


def _hubspot_paid_leads_per_day(token: str, start: date, end: date) -> dict[str, int]:
    """Pull paid leads (lead_qoyod_source IN paid set) from HubSpot Leads
    object (0-136), bucketed by RIYADH date (UTC+3)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # Riyadh date range → UTC ms timestamps (Riyadh = UTC+3, so subtract 3h)
    riyadh_start_utc = datetime(start.year, start.month, start.day, 0, 0) - timedelta(hours=3)
    riyadh_end_utc = datetime(end.year, end.month, end.day, 0, 0) + timedelta(days=1) - timedelta(hours=3)
    since_ms = int(riyadh_start_utc.timestamp() * 1000)
    until_ms = int(riyadh_end_utc.timestamp() * 1000)

    per_day: dict[str, int] = defaultdict(int)
    after = None
    paid_set = set(PAID_SOURCES)
    while True:
        body = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "hs_createdate", "operator": "GTE", "value": str(since_ms)},
                        {"propertyName": "hs_createdate", "operator": "LT",  "value": str(until_ms)},
                    ]
                }
            ],
            "properties": ["hs_createdate", "lead_qoyod_source"],
            "limit": 100,
            "sorts": [{"propertyName": "hs_createdate", "direction": "ASCENDING"}],
        }
        if after:
            body["after"] = after
        r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/0-136/search",
            json=body, headers=headers, timeout=30,
        )
        data = r.json()
        if "results" not in data:
            raise RuntimeError(f"HubSpot search error: {data}")
        for row in data.get("results", []):
            p = row.get("properties", {})
            src = (p.get("lead_qoyod_source") or "").strip()
            if src not in paid_set:
                continue
            cd = p.get("hs_createdate") or ""
            if not cd:
                continue
            ts = datetime.fromisoformat(cd.replace("Z", "+00:00"))
            riyadh_date = (ts + timedelta(hours=3)).date()
            per_day[str(riyadh_date)] += 1
        nxt = data.get("paging", {}).get("next", {})
        after = nxt.get("after")
        if not after:
            break
    return dict(per_day)


def _compute_drift(bq: dict[str, int], hs: dict[str, int],
                    start: date, end: date) -> list[dict]:
    """Return per-day drift records, sorted by abs(diff) descending."""
    rows = []
    d = start
    while d <= end:
        ds = str(d)
        b = bq.get(ds, 0)
        h = hs.get(ds, 0)
        diff = b - h
        pct = abs(diff) / max(h, 1) * 100
        rows.append({
            "date": ds,
            "bq": b,
            "hubspot": h,
            "diff": diff,
            "pct": round(pct, 1),
            "flagged": pct >= DRIFT_PCT_THRESHOLD and abs(diff) >= DRIFT_ABS_THRESHOLD,
        })
        d += timedelta(days=1)
    rows.sort(key=lambda x: -abs(x["diff"]))
    return rows


def _format_slack_message(rows: list[dict], any_flagged: bool) -> str:
    """Build the Slack message body."""
    today_riyadh = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%d")
    if not any_flagged:
        return (
            f":white_check_mark: *BQ ↔ HubSpot daily check — {today_riyadh}*\n"
            f"Last 7 days reconciled. All within {DRIFT_PCT_THRESHOLD}% / "
            f"{DRIFT_ABS_THRESHOLD} leads of HubSpot. Nothing to fix."
        )
    lines = [
        f":rotating_light: *BQ ↔ HubSpot daily check — {today_riyadh}*",
        f"Drift detected (>{DRIFT_PCT_THRESHOLD}% AND >{DRIFT_ABS_THRESHOLD} leads).",
        "",
        "```",
        f"{'date':<12} {'BQ':>5} {'HS':>5} {'diff':>6} {'%':>6}",
        "-" * 40,
    ]
    for r in rows:
        marker = " ⚠️" if r["flagged"] else ""
        lines.append(
            f"{r['date']:<12} {r['bq']:>5} {r['hubspot']:>5} "
            f"{r['diff']:>+6} {r['pct']:>5.1f}%{marker}"
        )
    lines.append("```")
    lines.append("")
    lines.append("Check: scheduler running? recent BQ syncs successful? views materialized?")
    return "\n".join(lines)


def _post_slack(message: str, channel: str | None = None) -> bool:
    """Post a message to #approvals (or the configured channel). Returns
    True on success."""
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
    except Exception as e:
        print(f"[slack] import failed: {e}")
        return False
    if not SLACK_BOT_TOKEN:
        print("[slack] SLACK_BOT_TOKEN not set — skipping post")
        return False
    target = channel or SLACK_CHANNEL_APPROVAL
    try:
        WebClient(token=SLACK_BOT_TOKEN).chat_postMessage(
            channel=target, text=message, unfurl_links=False,
        )
        return True
    except Exception as e:
        print(f"[slack] post failed: {e}")
        return False


def run(days_back: int = 7, post_to_slack: bool = True) -> dict:
    """Main entry. Returns summary dict. Always prints to stdout regardless
    of slack outcome so the script is useful in CLI runs too."""
    from collectors.bq_writer import get_client, PROJECT_ID, DATASET
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("HUBSPOT_ACCESS_TOKEN not set")

    end = (datetime.utcnow() + timedelta(hours=3)).date() - timedelta(days=1)  # yesterday Riyadh
    start = end - timedelta(days=days_back - 1)

    client = get_client()
    bq = _bq_paid_leads_per_day(client, PROJECT_ID, DATASET, start, end)
    hs = _hubspot_paid_leads_per_day(token, start, end)
    rows = _compute_drift(bq, hs, start, end)

    any_flagged = any(r["flagged"] for r in rows)
    bq_total = sum(r["bq"] for r in rows)
    hs_total = sum(r["hubspot"] for r in rows)

    # Always print to stdout (ASCII-safe for Windows cp1252 console)
    print(f"\n=== BQ vs HubSpot reconciliation ({start} to {end}, {days_back}d) ===")
    print(f"{'date':<12} {'BQ':>5} {'HS':>5} {'diff':>6} {'%':>6}")
    print("-" * 40)
    for r in sorted(rows, key=lambda x: x["date"]):
        flag = " !!" if r["flagged"] else ""
        print(f"  {r['date']:<12} {r['bq']:>5} {r['hubspot']:>5} {r['diff']:>+6} {r['pct']:>5.1f}%{flag}")
    print(f"\nTOTAL: BQ={bq_total} HubSpot={hs_total} diff={bq_total - hs_total:+d} "
          f"({abs(bq_total - hs_total) / max(hs_total, 1) * 100:.1f}%)")
    print(f"Flagged days: {sum(1 for r in rows if r['flagged'])}")

    if post_to_slack:
        msg = _format_slack_message(rows, any_flagged)
        posted = _post_slack(msg)
        print(f"\nSlack posted: {posted}")

    # Log to agent_activity_log via the project's standard helper
    try:
        from logs.activity_logger import log_activity_async
        log_activity_async(
            role="bq_refresh",
            action="daily_reconciliation",
            status="alert" if any_flagged else "success",
            rows_affected=bq_total,
            details={
                "days_back": days_back,
                "bq_total": bq_total,
                "hs_total": hs_total,
                "flagged_count": sum(1 for r in rows if r["flagged"]),
                "flagged_dates": [r["date"] for r in rows if r["flagged"]],
            },
        )
    except Exception as e:
        print(f"[log] could not log to agent_activity_log: {e}")

    return {
        "rows": rows,
        "bq_total": bq_total,
        "hs_total": hs_total,
        "flagged_count": sum(1 for r in rows if r["flagged"]),
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--no-slack", action="store_true",
                   help="Skip Slack post (still prints to stdout)")
    args = p.parse_args()
    run(days_back=args.days, post_to_slack=not args.no_slack)
