"""
YouTube OAuth helper.
Opens browser -> sign in with Google account that owns the Qoyod channel ->
prints refresh token + channel ID.

Run:  python scripts/youtube_oauth.py
Then paste YT_* into .env.

Pre-req:
  pip install google-auth-oauthlib google-api-python-client
  In Google Cloud Console, create OAuth Client ID (Desktop app),
  paste client_id + client_secret into .env as YT_CLIENT_ID / YT_CLIENT_SECRET.
"""
import os
import sys
import requests
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main():
    cid = os.getenv("YT_CLIENT_ID")
    sec = os.getenv("YT_CLIENT_SECRET")
    if not cid or not sec:
        print("Missing YT_CLIENT_ID / YT_CLIENT_SECRET in .env"); sys.exit(1)

    flow = InstalledAppFlow.from_client_config({
        "installed": {
            "client_id": cid,
            "client_secret": sec,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }, scopes=SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    # Resolve channel ID
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "id,snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {creds.token}"},
    )
    items = r.json().get("items", [])
    channel_id = items[0]["id"] if items else "<not found>"
    channel_title = items[0]["snippet"]["title"] if items else ""

    print("\n=== SUCCESS ===")
    print(f"Channel: {channel_title} ({channel_id})")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    print(f"YT_CHANNEL_ID={channel_id}")
    print("\nPaste the two above into .env.")


if __name__ == "__main__":
    main()
