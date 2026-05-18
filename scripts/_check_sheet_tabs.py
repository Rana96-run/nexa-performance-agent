"""Print exact byte representation of existing tab names."""
import sys, os
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from google.oauth2 import service_account
from googleapiclient.discovery import build

SHEET_ID = "120o-BXLdpvT5phvTY2ePiYcKiyQi5kcXedLuq_cDtVg"
key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "certs/bigquery-key.json"
creds = service_account.Credentials.from_service_account_file(
    key_path,
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)
sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
for s in meta["sheets"]:
    name = s["properties"]["title"]
    code_points = " ".join(f"U+{ord(c):04X}" for c in name)
    print(f"{name!r}")
    print(f"   codepoints: {code_points}")
