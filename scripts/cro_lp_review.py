"""
CRO Weekly LP Review
====================
Run with: railway run python scripts/cro_lp_review.py

What it does:
  1. Queries BQ: last 7 days of LP performance (destination_url × spend/clicks/leads/qualified)
  2. Writes results to Google Sheet tab LP-{today} in the main reporting sheet
  3. Creates a draft Asana task with top 10 LPs and any flags (CPQL > $85 or CVR < 1%)
"""

import os
import json
import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID       = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
ASANA_PROJECT  = os.getenv("ASANA_PROJECT_OPTIMIZATION")
ASANA_TOKEN    = os.getenv("ASANA_ACCESS_TOKEN")
BQ_PROJECT     = os.getenv("BQ_PROJECT_ID")
BQ_DATASET     = os.getenv("BQ_DATASET")
TODAY          = datetime.date.today().isoformat()         # e.g. 2026-06-12
TAB_NAME       = f"LP-{TODAY}"

CPQL_FLAG_THRESHOLD = 85.0
CVR_FLAG_THRESHOLD  = 0.01   # 1%

# ── BQ Query ──────────────────────────────────────────────────────────────────
QUERY = f"""
WITH hs AS (
  SELECT
    date,
    lead_utm_campaign,
    SUM(leads_total)     AS leads,
    SUM(leads_qualified) AS qualified_leads
  FROM `{BQ_PROJECT}.{BQ_DATASET}.hubspot_leads_module_daily`
  GROUP BY date, lead_utm_campaign
),
base AS (
  SELECT
    c.destination_url,
    SUM(c.spend)                                                      AS spend,
    SUM(c.clicks)                                                     AS clicks,
    SUM(c.impressions)                                                AS impressions,
    SUM(COALESCE(hs.leads, 0))                                        AS leads,
    SUM(COALESCE(hs.qualified_leads, 0))                              AS qualified_leads
  FROM `{BQ_PROJECT}.{BQ_DATASET}.campaigns_daily` c
  LEFT JOIN hs
    ON  c.date = hs.date
    AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
  WHERE c.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    AND c.destination_url IS NOT NULL
    AND c.clicks > 0
  GROUP BY c.destination_url
)
SELECT
  destination_url,
  ROUND(spend, 2)                                                      AS spend,
  clicks,
  impressions,
  leads,
  qualified_leads,
  ROUND(SAFE_DIVIDE(leads, clicks), 4)                                 AS cvr,
  ROUND(SAFE_DIVIDE(spend, NULLIF(qualified_leads, 0)), 2)             AS cpql,
  ROUND(SAFE_DIVIDE(spend, NULLIF(leads, 0)), 2)                       AS cpl
FROM base
ORDER BY spend DESC
"""

# ── Step 1: Run BQ ────────────────────────────────────────────────────────────
def run_bq():
    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT)
    print(f"Running BQ query for last 7 days…")
    rows = list(client.query(QUERY).result())
    print(f"  → {len(rows)} LPs found")
    return [dict(r) for r in rows]


# ── Step 2: Write to Google Sheet ─────────────────────────────────────────────
def write_sheet(rows):
    import googleapiclient.discovery
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = googleapiclient.discovery.build("sheets", "v4", credentials=creds)
    sheets  = service.spreadsheets()

    # Add new tab
    sheets.batchUpdate(spreadsheetId=SHEET_ID, body={
        "requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]
    }).execute()
    print(f"  Created tab: {TAB_NAME}")

    # Write header + data
    header = ["LP URL", "Spend ($)", "Clicks", "Impressions",
              "Leads", "Qualified", "CVR", "CPQL ($)", "CPL ($)", "Flags"]
    data = [header]
    for r in rows:
        flags = []
        if r["cpql"] and r["cpql"] > CPQL_FLAG_THRESHOLD:
            flags.append(f"CPQL ${r['cpql']:.0f} > $85")
        if r["cvr"] and r["cvr"] < CVR_FLAG_THRESHOLD:
            flags.append(f"CVR {r['cvr']*100:.2f}% < 1%")
        data.append([
            r["destination_url"],
            r["spend"],
            r["clicks"],
            r["impressions"],
            r["leads"],
            r["qualified_leads"],
            f"{r['cvr']*100:.2f}%" if r["cvr"] else "—",
            f"${r['cpql']:.2f}"    if r["cpql"] else "—",
            f"${r['cpl']:.2f}"     if r["cpl"]  else "—",
            " | ".join(flags) if flags else "✅"
        ])

    sheets.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{TAB_NAME}!A1",
        valueInputOption="RAW",
        body={"values": data}
    ).execute()
    print(f"  → Wrote {len(rows)} rows to {TAB_NAME}")
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}#gid={TAB_NAME}"


# ── Step 3: Create draft Asana task ──────────────────────────────────────────
def create_asana_draft(rows, sheet_url):
    import requests as req

    top10  = rows[:10]
    flags  = [r for r in rows if
              (r["cpql"] and r["cpql"] > CPQL_FLAG_THRESHOLD) or
              (r["cvr"]  and r["cvr"]  < CVR_FLAG_THRESHOLD)]

    # Build table
    table_lines = ["LP URL | Spend | Clicks | Leads | Qualified | CVR | CPQL | Flags",
                   "---|---|---|---|---|---|---|---"]
    for r in top10:
        flag_str = []
        if r["cpql"] and r["cpql"] > CPQL_FLAG_THRESHOLD:
            flag_str.append(f"⚠️ CPQL ${r['cpql']:.0f}")
        if r["cvr"] and r["cvr"] < CVR_FLAG_THRESHOLD:
            flag_str.append(f"⚠️ CVR {r['cvr']*100:.2f}%")
        table_lines.append(
            f"{r['destination_url']} | ${r['spend']:.0f} | {r['clicks']} | "
            f"{r['leads']} | {r['qualified_leads']} | "
            f"{r['cvr']*100:.2f}% | "
            f"{'$'+str(r['cpql']) if r['cpql'] else '—'} | "
            f"{'✅' if not flag_str else ' '.join(flag_str)}"
        )

    flag_summary = "\n".join(
        f"• {r['destination_url']} — "
        + (f"CPQL ${r['cpql']:.0f} > $85 " if r['cpql'] and r['cpql'] > CPQL_FLAG_THRESHOLD else "")
        + (f"CVR {r['cvr']*100:.2f}% < 1%"  if r['cvr']  and r['cvr']  < CVR_FLAG_THRESHOLD  else "")
        for r in flags
    ) or "None — all LPs within thresholds."

    notes = f"""[DRAFT] CRO LP REVIEW — {TODAY}

Period: {(datetime.date.today() - datetime.timedelta(days=7)).isoformat()} to {TODAY}
Full sheet: {sheet_url}

TOP 10 LPs BY SPEND
{chr(10).join(table_lines)}

FLAGS (CPQL > $85 or CVR < 1%):
{flag_summary}

RECOMMENDED ACTIONS:
• For flagged LPs: review copy, CTA placement, form length, and mobile load speed
• If CPQL > $85 on ≥ 2 channels for the same LP → escalate to performance-lead for budget reallocation
• If CVR < 1% on high-spend LP → CRO test in next sprint

Created: {TODAY}
Due: {(datetime.date.today() + datetime.timedelta(days=7)).isoformat()}
Priority: Medium
Type: Review
Channel: all
Asset level: landing page
Action: review → [CRO Specialist]
"""

    resp = req.post(
        "https://app.asana.com/api/1.0/tasks",
        headers={"Authorization": f"Bearer {ASANA_TOKEN}",
                 "Content-Type": "application/json"},
        json={"data": {
            "name": f"[DRAFT] CRO LP Review — {TODAY}",
            "notes": notes,
            "projects": [ASANA_PROJECT],
            "completed": False
        }}
    )
    task = resp.json().get("data", {})
    print(f"  Draft Asana task: https://app.asana.com/0/{ASANA_PROJECT}/{task.get('gid')}")
    return task


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n=== CRO LP Review — {TODAY} ===\n")

    print("Step 1: Querying BigQuery…")
    rows = run_bq()

    print("\nStep 2: Writing to Google Sheet…")
    sheet_url = write_sheet(rows)

    print("\nStep 3: Creating draft Asana task…")
    task = create_asana_draft(rows, sheet_url)

    print(f"\n✅ Done. Sheet tab: {TAB_NAME} | Asana draft created (not published to Slack).")
