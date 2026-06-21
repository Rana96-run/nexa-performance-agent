"""
Hex notebook refresh — triggers a re-run of published Hex apps via the
Hex REST API so dashboards always show fresh BQ data after each collector
pass.

Env vars required:
  HEX_API_TOKEN              — Hex Settings → API Keys → Create token
  HEX_PERFORMANCE_PROJECT_ID — project token from the performance dashboard URL

Project IDs come from the app URL slug — the alphanumeric part after the
last dash in the path segment:
  .../app/Qoyod-marketing-performance-<token>/latest
  Set HEX_PERFORMANCE_PROJECT_ID in Railway.

If HEX_API_TOKEN is not set, this module no-ops silently so local dev
and offline runs are not affected.

Note: HEX_ACTIVITY_PROJECT_ID and the Hex Activity dashboard were removed
2026-06-21. Railway /activity is the sole activity dashboard going forward.
"""
from __future__ import annotations

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE   = "https://app.hex.tech/api/v1"
_TOKEN  = os.getenv("HEX_API_TOKEN")

# Project IDs extracted from app URLs (alphanumeric suffix after last dash)
# Activity dashboard removed 2026-06-21 — Railway /activity is the sole activity view.
_PROJECTS = {
    "performance": os.getenv("HEX_PERFORMANCE_PROJECT_ID", "019de9ff-969c-7000-8463-5dfe9a5f730a"),
}

_POLL_INTERVAL = 5   # seconds between status checks
_TIMEOUT       = 300  # give up after 5 minutes


def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"}


def _trigger_run(project_id: str) -> str | None:
    """POST /project/{id}/run — returns run_id or None on failure.

    Critical params:
      updatePublishedResults=true → push the new run output into the published
                                     app so the dashboard URL shows fresh data.
                                     Without this, the published app keeps
                                     showing cached results from the last
                                     manual publish — that's the trap that
                                     made the dashboard look 5 days stale on
                                     2026-05-06.
      useCachedSqlResults=false  → bypass any per-cell cache so the SQL hits
                                     BigQuery again for the latest partitions.
    """
    url = f"{_BASE}/project/{project_id}/run"
    body = {
        "updatePublishedResults": True,
        "useCachedSqlResults":    False,
    }
    try:
        r = requests.post(url, json=body, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            run_id = r.json().get("runId") or r.json().get("runStatusUrl", "")
            print(f"[hex] triggered run for {project_id}: {run_id}")
            return run_id or "ok"
        print(f"[hex] trigger failed {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        print(f"[hex] trigger error: {e}")
        return None


def _wait_for_run(project_id: str, run_id: str) -> bool:
    """Poll GET /project/{id}/run/{run_id} until complete or timeout."""
    url = f"{_BASE}/project/{project_id}/run/{run_id}"
    deadline = time.time() + _TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(url, headers=_headers(), timeout=10)
            if r.status_code == 200:
                status = r.json().get("status", "").upper()
                if status in ("COMPLETED", "SUCCESS"):
                    return True
                if status in ("FAILED", "ERRORED", "KILLED"):
                    print(f"[hex] run {run_id} ended with status: {status}")
                    return False
            # still running → keep polling
        except Exception as e:
            print(f"[hex] poll error: {e}")
        time.sleep(_POLL_INTERVAL)
    print(f"[hex] timeout waiting for run {run_id}")
    return False


def refresh_all(wait: bool = False) -> dict[str, bool]:
    """
    Trigger a re-run of all Hex notebooks.

    Args:
        wait: If True, poll until each run completes before returning.
              Default False — fire-and-forget (Hex queues the run).

    Returns:
        dict of project_name -> success bool
    """
    if not _TOKEN:
        print("[hex] HEX_API_TOKEN not set — skipping Hex refresh")
        return {}

    results = {}
    for name, project_id in _PROJECTS.items():
        if not project_id:
            continue
        run_id = _trigger_run(project_id)
        if run_id and wait:
            results[name] = _wait_for_run(project_id, run_id)
        else:
            results[name] = run_id is not None

    ok  = [n for n, v in results.items() if v]
    bad = [n for n, v in results.items() if not v]
    print(f"[hex] refresh triggered: {ok or 'none'}"
          + (f" | FAILED: {bad}" if bad else ""))
    return results
