"""
scripts/health_check.py
========================
Self-contained health check for all Nexa integrations.

Runs automatically on startup via operational_scheduler and posts a single
status block to Slack so Amar can see the system state at a glance.

Manual run (local or Railway shell):
    python scripts/health_check.py

What it checks:
  - Flask server /health endpoint (own URL)
  - HubSpot API (crm/v3/objects/leads — 1 row)
  - BigQuery connectivity (SELECT 1)
  - Google Ads (counts accessible accounts)
  - Meta Ads API (validates token)
  - Slack bot token (auth.test)
  - Asana token (users/me)
  - Zapier webhook endpoint (GET /webhooks/zapier)

Env vars needed: same as normal agent. RAILWAY_PUBLIC_DOMAIN is auto-set
by Railway; falls back to localhost for local runs.
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Make sure we can find project root when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from scripts import bootstrap  # materialise BQ credentials from env  # noqa


# ─── Config ───────────────────────────────────────────────────────────────────

RAILWAY_DOMAIN = (
    os.getenv("RAILWAY_PUBLIC_DOMAIN")          # set automatically by Railway
    or os.getenv("RAILWAY_STATIC_URL", "").removeprefix("https://")
    or "localhost:8080"
)
BASE_URL = f"https://{RAILWAY_DOMAIN}" if not RAILWAY_DOMAIN.startswith("localhost") else f"http://{RAILWAY_DOMAIN}"


def _now() -> str:
    tz = timezone(timedelta(hours=3))
    return datetime.now(tz).strftime("%d %b %Y %H:%M KSA")


# ─── Individual checks ─────────────────────────────────────────────────────────

def check_flask() -> tuple[bool, str]:
    """Own /health endpoint."""
    try:
        import requests
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return True, f"{BASE_URL}/health -> OK"
        return False, f"{BASE_URL}/health -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"Flask unreachable: {e}"


def check_hubspot() -> tuple[bool, str]:
    try:
        import requests
        from config import HUBSPOT_TOKEN
        r = requests.get(
            "https://api.hubapi.com/crm/v3/objects/0-136?limit=1",
            headers={"Authorization": f"Bearer {HUBSPOT_TOKEN}"},
            timeout=10,
        )
        if r.status_code in (200, 404):
            return True, "HubSpot API -> OK"
        return False, f"HubSpot API -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"HubSpot: {e}"


def check_bigquery() -> tuple[bool, str]:
    try:
        from collectors.bq_writer import get_client, PROJECT_ID
        client = get_client()
        list(client.query("SELECT 1").result())
        return True, f"BigQuery -> OK (project={PROJECT_ID})"
    except Exception as e:
        return False, f"BigQuery: {e}"


def check_google_ads() -> tuple[bool, str]:
    try:
        from collectors.google_ads_bq import _client, _customer_ids
        client = _client()
        ids = _customer_ids()
        if not ids:
            return False, "Google Ads: GOOGLE_ADS_CUSTOMER_IDS not set"
        # Run a minimal GAQL query on the first account to validate connectivity
        svc = client.get_service("GoogleAdsService")
        q = "SELECT customer.id FROM customer LIMIT 1"
        resp = svc.search_stream(customer_id=ids[0], query=q)
        for _ in resp:
            pass
        return True, f"Google Ads -> OK ({len(ids)} account(s))"
    except Exception as e:
        return False, f"Google Ads: {e}"


def check_meta() -> tuple[bool, str]:
    try:
        import requests
        from config import META_ACCESS_TOKEN
        r = requests.get(
            "https://graph.facebook.com/v18.0/me",
            params={"access_token": META_ACCESS_TOKEN},
            timeout=10,
        )
        d = r.json()
        if r.status_code == 200 and "id" in d:
            return True, f"Meta API -> OK (id={d['id']})"
        return False, f"Meta API -> {d.get('error', {}).get('message', 'unknown error')}"
    except Exception as e:
        return False, f"Meta: {e}"


def check_slack() -> tuple[bool, str]:
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN
        r = WebClient(token=SLACK_BOT_TOKEN).auth_test()
        return True, f"Slack -> OK (bot={r['user']})"
    except Exception as e:
        return False, f"Slack: {e}"


def check_asana() -> tuple[bool, str]:
    try:
        import requests
        token = os.getenv("ASANA_ACCESS_TOKEN")
        if not token:
            return False, "Asana: ASANA_ACCESS_TOKEN not set"
        r = requests.get(
            "https://app.asana.com/api/1.0/users/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            name = r.json().get("data", {}).get("name", "?")
            return True, f"Asana -> OK (user={name})"
        return False, f"Asana -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"Asana: {e}"


def check_zapier_webhook() -> tuple[bool, str]:
    try:
        import requests
        r = requests.get(f"{BASE_URL}/webhooks/zapier", timeout=10)
        if r.status_code == 200:
            return True, "/webhooks/zapier -> OK"
        return False, f"/webhooks/zapier -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"Zapier webhook: {e}"


def check_hubspot_webhook() -> tuple[bool, str]:
    try:
        import requests
        r = requests.get(f"{BASE_URL}/webhooks/hubspot", timeout=10)
        if r.status_code == 200:
            return True, "/webhooks/hubspot -> OK"
        return False, f"/webhooks/hubspot -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"HubSpot webhook: {e}"


def check_conversion_tracking() -> tuple[bool, str]:
    """
    Verify at least one active Google Ads conversion action exists.
    A missing or broken conversion action means the agent is optimising blind.
    """
    try:
        from executors.google_ads import get_client
        from config import GOOGLE_ADS_CUSTOMER_ID
        client = get_client()
        ga_svc = client.get_service("GoogleAdsService")
        cid = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
        q = """
            SELECT conversion_action.name, conversion_action.status
            FROM conversion_action
            WHERE conversion_action.status = 'ENABLED'
            LIMIT 10
        """
        active = [row.conversion_action.name for row in ga_svc.search(customer_id=cid, query=q)]
        if active:
            return True, f"{len(active)} active conversion action(s): {', '.join(active[:3])}"
        return False, "No active conversion actions in Google Ads — agent optimising blind"
    except Exception as e:
        return False, f"Conversion tracking check: {e}"


def check_railway_deployment() -> tuple[bool, str]:
    """
    Verify the Railway deployment is healthy and GitHub source is connected.
    Uses Railway's GraphQL API (requires RAILWAY_API_TOKEN env var).
    Falls back to checking the /health endpoint age if token not available.
    """
    import requests
    token = os.getenv("RAILWAY_API_TOKEN", "")
    service_id = os.getenv("RAILWAY_SERVICE_ID", "")

    if token and service_id:
        try:
            query = """
            query($serviceId: String!) {
              deployments(input: { serviceId: $serviceId }, first: 1) {
                edges { node { status createdAt url } }
              }
            }
            """
            r = requests.post(
                "https://backboard.railway.app/graphql/v2",
                json={"query": query, "variables": {"serviceId": service_id}},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if r.status_code != 200:
                return False, f"Railway API -> HTTP {r.status_code}"
            edges = r.json().get("data", {}).get("deployments", {}).get("edges", [])
            if not edges:
                return False, "Railway: no deployments found"
            latest = edges[0]["node"]
            status = latest.get("status", "UNKNOWN")
            if status in ("SUCCESS", "ACTIVE"):
                return True, f"Railway deployment -> {status}"
            return False, f"Railway deployment -> {status} (check dashboard)"
        except Exception as e:
            return False, f"Railway API error: {e}"

    # Fallback: just verify the app responds (Flask check already does this,
    # but re-check here for a Railway-specific label in the report)
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200:
            return True, f"Railway app reachable (no API token for full check)"
        return False, f"Railway app unreachable -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"Railway app unreachable: {e}"


def check_slack_listener() -> tuple[bool, str]:
    """
    Verify the Slack listener is alive by checking its log file for a recent
    heartbeat (last write within 3 minutes). Falls back to process table.
    """
    import subprocess, time as _time
    log_candidates = [
        Path("logs/slack-listener.log"),
        Path("/app/logs/slack-listener.log"),
    ]
    for log_path in log_candidates:
        if log_path.exists():
            age_s = _time.time() - log_path.stat().st_mtime
            if age_s < 180:
                return True, f"Slack listener log updated {int(age_s)}s ago"
            return False, f"Slack listener log stale — last update {int(age_s//60)}m ago (process may be down)"

    # Fallback: look for the process
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "slack_listener"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            return True, f"Slack listener process running (pid {out.split()[0]})"
        return False, "Slack listener process NOT found — run: python slack_listener.py"
    except Exception:
        return False, "Could not verify Slack listener (pgrep unavailable)"


# ─── Runner ────────────────────────────────────────────────────────────────────

CHECKS = [
    ("Railway deployment",    check_railway_deployment),
    ("Slack listener",        check_slack_listener),
    ("Flask",                 check_flask),
    ("HubSpot API",           check_hubspot),
    ("BigQuery",              check_bigquery),
    ("Google Ads",            check_google_ads),
    ("Conversion tracking",   check_conversion_tracking),
    ("Meta Ads",              check_meta),
    ("Slack",                 check_slack),
    ("Asana",                 check_asana),
    ("Zapier webhook",        check_zapier_webhook),
    ("HubSpot webhook",       check_hubspot_webhook),
]


def run_all() -> dict:
    """Run every check; return {name: (ok, msg)} dict."""
    results = {}
    for name, fn in CHECKS:
        t0 = time.time()
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"Unexpected error: {e}"
            traceback.print_exc()
        elapsed = round(time.time() - t0, 1)
        results[name] = (ok, f"{msg}  ({elapsed}s)")
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {name:<20} {msg}  ({elapsed}s)")
    return results


def post_to_slack(results: dict, failures_only: bool = True) -> None:
    """Post health status to Slack.

    Args:
        results:       {name: (ok, msg)} from run_all()
        failures_only: If True (default), only post when there are failures.
                       Silence when all green — no noise.
    """
    ok_count   = sum(1 for ok, _ in results.values() if ok)
    fail_count = len(results) - ok_count

    if failures_only and fail_count == 0:
        print("[health_check] All checks passed — no Slack post (failures_only=True)")
        return

    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_HEALTH

        # Only include failed checks in the Slack message to keep it short
        failed_lines = [
            f":x:  *{name}*  — {msg}"
            for name, (ok, msg) in results.items()
            if not ok
        ]
        overall = ":warning:" if fail_count else ":white_check_mark:"
        header = (
            f"{overall} *Nexa Health — {_now()}*\n"
            f"{fail_count} issue(s) detected  ({ok_count}/{len(results)} passing)"
        )

        from notifications.quiet import is_quiet, quiet_log
        if is_quiet():
            quiet_log("health_check", SLACK_CHANNEL_HEALTH, header)
        else:
            WebClient(token=SLACK_BOT_TOKEN).chat_postMessage(
                channel=SLACK_CHANNEL_HEALTH,
                text=header,
                blocks=[
                    {"type": "section", "text": {"type": "mrkdwn", "text": header}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(failed_lines)}},
                ],
            )
            print(f"[health_check] Posted {fail_count} failure(s) to Slack")
    except Exception as e:
        print(f"[health_check] Slack post failed: {e}")


def main(post_slack: bool = True, failures_only: bool = True) -> bool:
    """Return True if all checks pass.

    Args:
        post_slack:    Whether to post results to Slack (default True).
        failures_only: Only post to Slack when failures are found (default True).
                       Set False to force a full status post (e.g. manual runs).
    """
    print("=" * 60)
    print(f"  Nexa Health Check — {_now()}")
    print(f"  Base URL: {BASE_URL}")
    print("=" * 60)
    results = run_all()
    print("=" * 60)

    if post_slack:
        post_to_slack(results, failures_only=failures_only)

    all_ok = all(ok for ok, _ in results.values())
    print(f"\n  Overall: {'ALL PASS ✅' if all_ok else 'FAILURES DETECTED ❌'}")
    return all_ok


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Nexa integration health check")
    p.add_argument("--no-slack", action="store_true", help="Skip Slack post (local testing)")
    args = p.parse_args()
    ok = main(post_slack=not args.no_slack)
    sys.exit(0 if ok else 1)
