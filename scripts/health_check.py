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
            return True, f"{BASE_URL}/health → OK"
        return False, f"{BASE_URL}/health → HTTP {r.status_code}"
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
            return True, "HubSpot API → OK"
        return False, f"HubSpot API → HTTP {r.status_code}"
    except Exception as e:
        return False, f"HubSpot: {e}"


def check_bigquery() -> tuple[bool, str]:
    try:
        from collectors.bq_writer import get_client, PROJECT_ID
        client = get_client()
        list(client.query("SELECT 1").result())
        return True, f"BigQuery → OK (project={PROJECT_ID})"
    except Exception as e:
        return False, f"BigQuery: {e}"


def check_google_ads() -> tuple[bool, str]:
    try:
        from google.ads.googleads.client import GoogleAdsClient
        from config import GOOGLE_ADS_CONFIG
        cfg = {**GOOGLE_ADS_CONFIG, "use_proto_plus": True}
        client = GoogleAdsClient.load_from_dict(cfg, version="v18")
        svc = client.get_service("CustomerService")
        r = svc.list_accessible_customers()
        count = len(r.resource_names)
        return True, f"Google Ads → {count} accessible account(s)"
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
            return True, f"Meta API → OK (id={d['id']})"
        return False, f"Meta API → {d.get('error', {}).get('message', 'unknown error')}"
    except Exception as e:
        return False, f"Meta: {e}"


def check_slack() -> tuple[bool, str]:
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN
        r = WebClient(token=SLACK_BOT_TOKEN).auth_test()
        return True, f"Slack → OK (bot={r['user']})"
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
            return True, f"Asana → OK (user={name})"
        return False, f"Asana → HTTP {r.status_code}"
    except Exception as e:
        return False, f"Asana: {e}"


def check_zapier_webhook() -> tuple[bool, str]:
    try:
        import requests
        r = requests.get(f"{BASE_URL}/webhooks/zapier", timeout=10)
        if r.status_code == 200:
            return True, "/webhooks/zapier → OK"
        return False, f"/webhooks/zapier → HTTP {r.status_code}"
    except Exception as e:
        return False, f"Zapier webhook: {e}"


def check_hubspot_webhook() -> tuple[bool, str]:
    try:
        import requests
        r = requests.get(f"{BASE_URL}/webhooks/hubspot", timeout=10)
        if r.status_code == 200:
            return True, "/webhooks/hubspot → OK"
        return False, f"/webhooks/hubspot → HTTP {r.status_code}"
    except Exception as e:
        return False, f"HubSpot webhook: {e}"


# ─── Runner ────────────────────────────────────────────────────────────────────

CHECKS = [
    ("Flask",             check_flask),
    ("HubSpot API",       check_hubspot),
    ("BigQuery",          check_bigquery),
    ("Google Ads",        check_google_ads),
    ("Meta Ads",          check_meta),
    ("Slack",             check_slack),
    ("Asana",             check_asana),
    ("Zapier webhook",    check_zapier_webhook),
    ("HubSpot webhook",   check_hubspot_webhook),
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
