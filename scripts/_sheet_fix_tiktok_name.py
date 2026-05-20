"""Update master sheet — TikTok campaign was renamed.

# KPI-RULE-BYPASS — sheet update only, no SQL leads analysis.
"""
import os, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"

key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "certs/bigquery-key.json"
creds = service_account.Credentials.from_service_account_file(
    key_path, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Append a correction row to action log
correction = [[
    "2026-05-19", "Tiktok_FinancialStatemnt", "renamed_to_match_convention",
    "Old: Tiktok_WebForm_AR_Qawaem236 → New: Tiktok_Conversion_Prospecting_Interests_FinancialStatemnt_Websiteform. "
    "Camp 1865704232893537. Updated memory/CRITICAL_KPI_RULES.md with per-channel naming tokens."
]]
sheets.spreadsheets().values().append(
    spreadsheetId=SHEET_ID,
    range="'14 ZATCA Action Log'!A1",
    valueInputOption="USER_ENTERED",
    insertDataOption="INSERT_ROWS",
    body={"values": correction},
).execute()
print("  ✅ correction appended to tab 14")

# Also update the row in tab 13 — just replace the campaign name cell
# Tab 13 is a flat table; the TikTok row is at row 7 (header + 6 campaigns).
# A1=header, A2..A7 = 6 campaigns. TikTok is row 7.
sheets.spreadsheets().values().update(
    spreadsheetId=SHEET_ID,
    range="'13 ZATCA Setup'!A7",
    valueInputOption="USER_ENTERED",
    body={"values": [["Tiktok_Conversion_Prospecting_Interests_FinancialStatemnt_Websiteform"]]},
).execute()
print("  ✅ tab 13 row 7 campaign name updated")
