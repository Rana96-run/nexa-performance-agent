"""
Monthly Winning Creative Report
================================
Runs on the 1st of every month via operational_scheduler._run_monthly_creative_report().
Also runnable manually: railway run python scripts/monthly_creative_report.py

What it does:
  1. Queries BQ v_ad_performance for last 30 days (min 3 leads per ad)
  2. Classifies each ad: winner / optimise / underperformer
  3. Creates a Google Sheet: "Winning Creatives — {Month} {Year}"
     One tab per channel, Summary tab first
  4. Creates an Asana task for the design team with top winners + actions
"""

import os
import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
BQ_PROJECT    = os.getenv("BQ_PROJECT_ID")
BQ_DATASET    = os.getenv("BQ_DATASET")
ASANA_TOKEN   = os.getenv("ASANA_ACCESS_TOKEN")
ASANA_PROJECT = os.getenv("ASANA_PROJECT_OPTIMIZATION")
DRIVE_FOLDER  = "Nexa Performance Reports"   # top-level Drive folder

TODAY         = datetime.date.today()
MONTH_NAME    = TODAY.strftime("%B")
YEAR          = TODAY.strftime("%Y")
SHEET_TITLE   = f"Winning Creatives — {MONTH_NAME} {YEAR}"

# Thresholds (fixed — not from config)
WINNER_QUAL_RATIO = 0.50
WINNER_CPL        = 25.00

CHANNELS = ["Meta", "Google", "Snapchat", "TikTok", "LinkedIn", "Microsoft"]

# ── BQ query ──────────────────────────────────────────────────────────────────
QUERY = f"""
SELECT
  channel,
  ad_name,
  ad_id,
  SUM(clicks)                                                       AS clicks,
  SAFE_DIVIDE(SUM(clicks), NULLIF(SUM(impressions), 0))            AS ctr,
  SUM(leads_total)                                                  AS leads,
  SUM(qualified)                                                    AS qualified_leads,
  SAFE_DIVIDE(SUM(qualified), NULLIF(SUM(leads_total), 0))         AS qual_ratio,
  SAFE_DIVIDE(SUM(spend),     NULLIF(SUM(leads_total), 0))         AS cpl,
  SUM(spend)                                                        AS spend
FROM `{BQ_PROJECT}.{BQ_DATASET}.v_ad_performance`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND leads_total > 0
GROUP BY channel, ad_name, ad_id
HAVING SUM(leads_total) >= 3
ORDER BY channel, qual_ratio DESC, cpl ASC
"""


def classify(row: dict) -> str:
    """Return 'winner', 'optimise', or 'underperformer'."""
    qr  = row.get("qual_ratio") or 0
    cpl = row.get("cpl") or 999
    if qr > WINNER_QUAL_RATIO and cpl <= WINNER_CPL:
        return "winner"
    if qr > WINNER_QUAL_RATIO:
        return "optimise"
    return "underperformer"


def run_bq() -> list[dict]:
    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT)
    print(f"[monthly-creative] Querying BQ for last 30 days…")
    rows = [dict(r) for r in client.query(QUERY).result()]
    print(f"[monthly-creative] {len(rows)} ads found")
    return rows


def build_sheet(rows: list[dict]) -> str:
    """Create Google Sheet, return its URL."""
    import googleapiclient.discovery
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    sheets_svc = googleapiclient.discovery.build("sheets", "v4", credentials=creds)
    drive_svc  = googleapiclient.discovery.build("drive",  "v3", credentials=creds)

    # Create the spreadsheet
    sheet_meta = sheets_svc.spreadsheets().create(body={
        "properties": {"title": SHEET_TITLE},
        "sheets": [{"properties": {"title": "Summary"}}],
    }).execute()
    sheet_id  = sheet_meta["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"

    # Group rows by channel, classify
    by_channel: dict[str, list[dict]] = {}
    for r in rows:
        ch = r["channel"].capitalize()
        # Normalize channel name to match CHANNELS list
        for c in CHANNELS:
            if c.lower() in ch.lower():
                ch = c
                break
        r["_status"] = classify(r)
        by_channel.setdefault(ch, []).append(r)

    # Sort each channel: winners first, then optimise, then underperformers
    STATUS_ORDER = {"winner": 0, "optimise": 1, "underperformer": 2}
    for ch in by_channel:
        by_channel[ch].sort(key=lambda x: (STATUS_ORDER[x["_status"]], x.get("cpl") or 999))

    # Add one tab per channel with data, write rows
    add_requests = []
    for ch in CHANNELS:
        if ch not in by_channel:
            continue
        add_requests.append({"addSheet": {"properties": {"title": ch}}})

    if add_requests:
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": add_requests}
        ).execute()

    header = ["Rank", "Ad Name", "Ad ID", "Clicks", "CTR", "Leads",
              "Qualified", "Qual%", "CPL ($)", "Spend ($)", "Status"]

    for ch, ch_rows in by_channel.items():
        data = [header]
        for i, r in enumerate(ch_rows, 1):
            status_label = {"winner": "✅ Winner",
                            "optimise": "⚠️ Optimise",
                            "underperformer": "🔴 Underperformer"}[r["_status"]]
            data.append([
                i,
                r.get("ad_name") or "",
                str(r.get("ad_id") or ""),
                r.get("clicks") or 0,
                f"{(r.get('ctr') or 0)*100:.2f}%",
                r.get("leads") or 0,
                r.get("qualified_leads") or 0,
                f"{(r.get('qual_ratio') or 0)*100:.1f}%",
                f"${r.get('cpl') or 0:.2f}",
                f"${r.get('spend') or 0:.0f}",
                status_label,
            ])
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{ch}!A1",
            valueInputOption="RAW",
            body={"values": data},
        ).execute()

    # Build Summary tab
    summary_data = [["Channel", "Winners", "Optimise", "Total Ads",
                     "Best Ad Name", "Best Qual%"]]
    for ch in CHANNELS:
        if ch not in by_channel:
            continue
        ch_rows  = by_channel[ch]
        winners  = sum(1 for r in ch_rows if r["_status"] == "winner")
        optimise = sum(1 for r in ch_rows if r["_status"] == "optimise")
        best     = ch_rows[0] if ch_rows else {}
        summary_data.append([
            ch, winners, optimise, len(ch_rows),
            best.get("ad_name") or "—",
            f"{(best.get('qual_ratio') or 0)*100:.1f}%",
        ])

    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Summary!A1",
        valueInputOption="RAW",
        body={"values": summary_data},
    ).execute()

    # Move to Drive folder
    try:
        folder_q = (f"name='{DRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder' "
                    f"and trashed=false")
        folders = drive_svc.files().list(q=folder_q, fields="files(id)").execute()
        if folders.get("files"):
            folder_id = folders["files"][0]["id"]
            drive_svc.files().update(
                fileId=sheet_id,
                addParents=folder_id,
                removeParents="root",
                fields="id, parents",
            ).execute()
            print(f"[monthly-creative] Moved sheet to '{DRIVE_FOLDER}' folder")
    except Exception as e:
        print(f"[monthly-creative] Drive folder move failed (non-fatal): {e}")

    print(f"[monthly-creative] Sheet created: {sheet_url}")
    return sheet_url


def create_asana_task(rows: list[dict], sheet_url: str):
    import requests as req

    by_channel: dict[str, list[dict]] = {}
    for r in rows:
        r["_status"] = classify(r)
        ch = r["channel"].capitalize()
        for c in CHANNELS:
            if c.lower() in ch.lower():
                ch = c
                break
        by_channel.setdefault(ch, []).append(r)

    top_winners = []
    underperformers = []
    for ch, ch_rows in by_channel.items():
        winners = [r for r in ch_rows if r["_status"] == "winner"]
        under   = [r for r in ch_rows if r["_status"] == "underperformer"]
        if winners:
            best = sorted(winners, key=lambda x: -(x.get("qual_ratio") or 0))[0]
            top_winners.append(
                f"• {ch}: {best.get('ad_name')} — "
                f"{(best.get('qual_ratio') or 0)*100:.0f}% qual, "
                f"${best.get('cpl') or 0:.0f} CPL"
            )
        if under:
            worst = sorted(under, key=lambda x: (x.get("qual_ratio") or 1))[0]
            underperformers.append(
                f"• {ch}: {worst.get('ad_name')} — "
                f"{(worst.get('qual_ratio') or 0)*100:.0f}% qual"
            )

    due = (TODAY + datetime.timedelta(days=7)).isoformat()
    notes = (
        f"WINNING CREATIVES — {MONTH_NAME} {YEAR}\n\n"
        f"Google Sheet: {sheet_url}\n\n"
        f"TOP WINNERS THIS MONTH:\n"
        + "\n".join(top_winners or ["• No winners meeting both thresholds this month"]) + "\n\n"
        "DESIGN TEAM ACTION:\n"
        "• Replicate the winning creative format for each channel listed above\n"
        "• Prioritise: duplicate into a new variant with a fresh hook, same format and CTA\n"
        "• For 'optimise' rows: the creative works — review bid/budget before replacing\n\n"
        "UNDERPERFORMERS TO REPLACE:\n"
        + "\n".join(underperformers or ["• None"]) + "\n\n"
        f"Created: {TODAY.isoformat()} | Due: {due} | Priority: Medium | "
        "Type: Recommendation | Channel: all | Asset level: ad | "
        "Action: optimize → [Creative Strategist]"
    )

    resp = req.post(
        "https://app.asana.com/api/1.0/tasks",
        headers={"Authorization": f"Bearer {ASANA_TOKEN}",
                 "Content-Type": "application/json"},
        json={"data": {
            "name": f"Winning Creatives — {MONTH_NAME} {YEAR}",
            "notes": notes,
            "projects": [ASANA_PROJECT],
            "completed": False,
            "due_on": due,
        }},
    )
    task = resp.json().get("data", {})
    print(f"[monthly-creative] Asana task: "
          f"https://app.asana.com/0/{ASANA_PROJECT}/{task.get('gid')}")


if __name__ == "__main__":
    print(f"\n=== Monthly Creative Report — {MONTH_NAME} {YEAR} ===\n")
    rows     = run_bq()
    sheet_url = build_sheet(rows)
    create_asana_task(rows, sheet_url)
    print(f"\n✅ Done. Sheet: {sheet_url}")
