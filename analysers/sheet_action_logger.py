"""ZATCA Action Log auto-updater.

Auto-appends team-relevant actions to the master sheet's '14 ZATCA Action Log'
tab. Runs from operational_scheduler nightly. Replaces the manual one-off
_log_session_to_sheet.py pattern.

Sources two types of action rows:
  1. Live ad-account writes (from agent_activity_log BQ table) — pause, scale,
     keyword adds, ad creates, sitelink changes — anything that touched a
     platform via an API.
  2. Code/infrastructure changes (from a fixed list of git-commit-derived
     entries you can append to via append_infrastructure_entries()).

Idempotent: tracks the last-written row's date in the sheet itself (no
external state). On each run, scans agent_activity_log for actions since
the last logged date and appends only the new ones.

The sheet's design IS the source of truth for what's been logged; we don't
keep a parallel cursor in BQ.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
TAB      = "14 ZATCA Action Log"
HEADER   = ["date", "campaign_scope", "action", "detail", "status"]

# Actions worth logging to the team-visible sheet. Excludes routine refresh
# noise and successful-by-default cadence completions.
TEAM_VISIBLE_ACTIONS = {
    # Ad-platform writes
    "pause_campaign", "pause_ad", "pause_adset", "pause_keyword",
    "scale_campaign", "scale_adset",
    "add_keywords", "add_negatives", "remove_keywords",
    "create_campaign", "create_adset", "create_ad",
    "edit_rsa", "edit_sitelinks", "edit_extensions",
    # Schema / infra / dashboard changes
    "schema_change", "dashboard_fix", "collector_fix", "scheduler_change",
    # Notable status events
    "compliance_violation_found", "compliance_violation_fixed",
}


def _sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds)


def _read_last_logged_date(svc) -> str | None:
    """Read the sheet, return the most recent date already logged."""
    vals = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{TAB}'!A1:A1000",
    ).execute().get("values", [])
    # Drop header, find max date
    dates = [r[0] for r in vals[1:] if r and r[0]]
    if not dates:
        return None
    return max(dates)


def _append_rows(svc, rows: list[list[str]]) -> int:
    """Append rows to the sheet. Returns number written."""
    if not rows:
        return 0
    svc.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"'{TAB}'!A:E",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


def _scan_activity_log_for_team_actions(since_date: str) -> list[list[str]]:
    """Pull agent_activity_log entries since since_date (exclusive) that match
    TEAM_VISIBLE_ACTIONS. Returns rows in [date, scope, action, detail, status] format."""
    from collectors.bq_writer import get_client
    c = get_client()
    proj = os.environ["BQ_PROJECT_ID"]
    ds   = os.environ["BQ_DATASET"]

    # Build action filter — wildcard-match on action names
    action_patterns = "|".join(TEAM_VISIBLE_ACTIONS)
    sql = f"""
    SELECT
      DATE(ts, 'Asia/Riyadh')                                    AS date,
      IFNULL(channel, 'Infrastructure')                          AS scope,
      action,
      SUBSTR(IFNULL(JSON_VALUE(details, '$.summary'),
                    IFNULL(JSON_VALUE(details, '$.detail'),
                           '')), 1, 400)                          AS detail,
      status
    FROM `{proj}.{ds}.agent_activity_log`
    WHERE DATE(ts, 'Asia/Riyadh') > '{since_date}'
      AND REGEXP_CONTAINS(action, r'{action_patterns}')
      AND role != 'bq_refresh'  -- exclude noise
    ORDER BY ts
    """
    rows = []
    for r in c.query(sql).result():
        rows.append([
            str(r.date),
            r.scope or "—",
            r.action,
            r.detail or "",
            "Done" if r.status == "success" else r.status,
        ])
    return rows


def update_sheet(extra_rows: list[list[str]] = None) -> dict:
    """Main entry point. Scheduler-callable.

    Args:
        extra_rows: optional manually-supplied infrastructure rows to append
            alongside the BQ-derived ones. Use this for code/schema changes
            that aren't logged to agent_activity_log.
    Returns:
        {'last_logged_date': ..., 'appended': N, 'detail': summary}
    """
    svc = _sheets_service()
    last_date = _read_last_logged_date(svc)
    print(f"[sheet_logger] Last logged date: {last_date or '(empty sheet)'}")

    # Pull team-visible actions from BQ since last_date
    if last_date:
        bq_rows = _scan_activity_log_for_team_actions(last_date)
    else:
        # Empty sheet — start from yesterday so first run isn't gigantic
        yday = (datetime.now(timezone(timedelta(hours=3))).date()
                - timedelta(days=1)).isoformat()
        bq_rows = _scan_activity_log_for_team_actions(yday)

    all_rows = bq_rows + (extra_rows or [])
    if not all_rows:
        print("[sheet_logger] No new team-visible actions since last log.")
        return {"last_logged_date": last_date, "appended": 0,
                "detail": "no new rows"}

    written = _append_rows(svc, all_rows)
    print(f"[sheet_logger] Appended {written} new row(s) to '{TAB}'")
    return {"last_logged_date": last_date, "appended": written,
            "detail": f"appended {written} rows"}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, ".")
    from dotenv import load_dotenv; load_dotenv()
    result = update_sheet()
    print(result)
