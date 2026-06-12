"""
LinkedIn headless token refresh — exchanges LI_REFRESH_TOKEN for a fresh
LI_ACCESS_TOKEN and writes it to the `platform_tokens` BQ table so
collectors/linkedin_bq.py picks it up without a Railway redeploy.

Called nightly by operational_scheduler._nightly() at step 3f.
Also callable manually: railway run python scripts/linkedin_refresh.py

LinkedIn token lifetimes:
  access_token   — 60 days  (this script renews it)
  refresh_token  — 365 days (stays in Railway env, never changes on refresh)
"""
from __future__ import annotations
import os, sys, requests
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID     = os.getenv("LI_CLIENT_ID")
CLIENT_SECRET = os.getenv("LI_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("LI_REFRESH_TOKEN")
TOKEN_URL     = "https://www.linkedin.com/oauth/v2/accessToken"
BQ_PROJECT    = os.getenv("BQ_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "angular-axle-492812-q4")
BQ_DATASET    = os.getenv("BQ_DATASET", "qoyod_marketing")
TOKEN_TABLE   = f"{BQ_PROJECT}.{BQ_DATASET}.platform_tokens"


def _ensure_table() -> None:
    """Create platform_tokens table if it doesn't exist."""
    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT)
    schema = [
        bigquery.SchemaField("platform",       "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("token_type",     "STRING",    mode="REQUIRED"),  # access | refresh
        bigquery.SchemaField("token_value",    "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("expires_at",     "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("refreshed_at",   "TIMESTAMP", mode="REQUIRED"),
    ]
    table = bigquery.Table(TOKEN_TABLE, schema=schema)
    try:
        client.create_table(table, exists_ok=True)
    except Exception as e:
        print(f"[li-refresh] table ensure warning (non-fatal): {e}")


def _write_token(access_token: str, expires_in: int) -> None:
    """Write new access token to BQ platform_tokens table."""
    from google.cloud import bigquery
    import io, json
    client     = bigquery.Client(project=BQ_PROJECT)
    now        = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in)
    row = {
        "platform":     "linkedin",
        "token_type":   "access",
        "token_value":  access_token,
        "expires_at":   expires_at.isoformat(),
        "refreshed_at": now.isoformat(),
    }
    ndjson = (json.dumps(row) + "\n").encode()
    job_cfg = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("platform",     "STRING"),
            bigquery.SchemaField("token_type",   "STRING"),
            bigquery.SchemaField("token_value",  "STRING"),
            bigquery.SchemaField("expires_at",   "TIMESTAMP"),
            bigquery.SchemaField("refreshed_at", "TIMESTAMP"),
        ],
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    client.load_table_from_file(io.BytesIO(ndjson), TOKEN_TABLE, job_config=job_cfg).result()
    print(f"[li-refresh] token written to BQ, expires {expires_at.strftime('%Y-%m-%d %H:%M UTC')}")


def get_active_token() -> str | None:
    """
    Read the most-recent non-expired LinkedIn access token from BQ.
    Falls back to env var LI_ACCESS_TOKEN if BQ has nothing valid.
    Called by collectors/linkedin_bq.py at startup.
    """
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=BQ_PROJECT)
        sql = f"""
            SELECT token_value, expires_at
            FROM `{TOKEN_TABLE}`
            WHERE platform = 'linkedin' AND token_type = 'access'
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP())
            ORDER BY refreshed_at DESC
            LIMIT 1
        """
        rows = list(client.query(sql).result())
        if rows:
            return rows[0].token_value
    except Exception:
        pass
    return os.getenv("LI_ACCESS_TOKEN")  # fallback


def refresh_token() -> str:
    """
    Exchange LI_REFRESH_TOKEN for a new access token.
    Writes it to BQ. Returns the new access token string.
    """
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        missing = [k for k, v in {
            "LI_CLIENT_ID": CLIENT_ID,
            "LI_CLIENT_SECRET": CLIENT_SECRET,
            "LI_REFRESH_TOKEN": REFRESH_TOKEN
        }.items() if not v]
        raise EnvironmentError(f"[li-refresh] Missing env vars: {missing}")

    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }, timeout=15)

    if resp.status_code != 200:
        raise RuntimeError(
            f"[li-refresh] LinkedIn token refresh failed: "
            f"HTTP {resp.status_code} — {resp.text[:200]}"
        )

    data         = resp.json()
    access_token = data["access_token"]
    expires_in   = data.get("expires_in", 5184000)  # default 60 days

    _ensure_table()
    _write_token(access_token, expires_in)
    print(f"[li-refresh] access token refreshed OK (expires_in={expires_in}s)")
    return access_token


if __name__ == "__main__":
    t = refresh_token()
    print(f"[li-refresh] new token: {t[:20]}...")
