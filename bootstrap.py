"""
Runtime bootstrap for hosted environments (Replit, GitHub Actions, etc).

If the Google service-account JSON is provided via the
GOOGLE_APPLICATION_CREDENTIALS_JSON env var (instead of a file on disk),
write it to a tmp path and point GOOGLE_APPLICATION_CREDENTIALS at it.

Import this at the top of main.py so it runs before any collector uses BigQuery.
"""
import os
import tempfile


def _materialize_google_credentials():
    raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not raw:
        return  # either already a file path, or not using BQ
    target = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.path.join(
        tempfile.gettempdir(), "bigquery-key.json"
    )
    # only write once per process
    if not os.path.exists(target):
        with open(target, "w", encoding="utf-8") as f:
            f.write(raw)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = target


_materialize_google_credentials()
