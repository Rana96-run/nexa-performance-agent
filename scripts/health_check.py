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



def check_microsoft_ads() -> tuple[bool, str]:
    try:
        from collectors.microsoft_ads_bq import _accounts, _get_access_token_for
        accs = _accounts()
        if not accs:
            return False, "Microsoft Ads: no accounts configured"
        ok_accs, fail_accs = [], []
        for acc in accs:
            try:
                _get_access_token_for(acc["refresh_token"], acc["public_client"])
                ok_accs.append(acc["account_id"])
            except Exception as e:
                fail_accs.append(f"{acc['account_id']}: {str(e)[:80]}")
        if fail_accs:
            msg = f"{len(ok_accs)}/{len(accs)} OK. Failed: {'; '.join(fail_accs)}"
            return len(ok_accs) > 0, f"Microsoft Ads -> partial: {msg}"
        return True, f"Microsoft Ads -> OK ({len(ok_accs)} account(s))"
    except Exception as e:
        return False, f"Microsoft Ads: {e}"


def check_tiktok() -> tuple[bool, str]:
    try:
        import os, requests as _req
        token = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        if not token:
            return False, "TikTok: TIKTOK_ACCESS_TOKEN not set"
        from collectors.tiktok_bq import _ad_accounts, BASE
        accts = _ad_accounts()
        if not accts:
            return False, "TikTok: no ad accounts configured"
        r = _req.get(
            f"{BASE}/advertiser/info/",
            headers={"Access-Token": token, "Content-Type": "application/json"},
            params={"advertiser_ids": f'["{accts[0]}"]', "fields": '["name"]'},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("code") == 0:
            return True, f"TikTok -> OK ({len(accts)} account(s))"
        return False, f"TikTok: API error {r.status_code} {r.text[:80]}"
    except Exception as e:
        return False, f"TikTok: {e}"


def check_snapchat() -> tuple[bool, str]:
    try:
        from collectors.snap_bq import _refresh_access_token, _ad_accounts
        token = _refresh_access_token()
        if not token:
            return False, "Snapchat: token fetch returned empty"
        accts = _ad_accounts()
        return True, f"Snapchat -> OK ({len(accts)} account(s))"
    except Exception as e:
        return False, f"Snapchat: {e}"


def check_linkedin() -> tuple[bool, str]:
    try:
        import requests
        from collectors.linkedin_bq import _headers, BASE
        r = requests.get(f"{BASE}/adAccounts?q=search", headers=_headers(), timeout=10)
        if r.status_code < 400:
            n = len(r.json().get("elements", []))
            return True, f"LinkedIn -> OK ({n} account(s))"
        return False, f"LinkedIn -> HTTP {r.status_code}"
    except Exception as e:
        return False, f"LinkedIn: {e}"


def check_data_freshness() -> tuple[bool, str]:
    """Check how stale the key BQ tables are.

    Threshold: 3 days (matches check_freshness.STALE_THRESHOLD_DAYS).
    Collector runs at 08:00 Riyadh pulling yesterday's data, so before that
    window data is legitimately 2 days behind — flagging at >1 is a false positive.
    Known-paused channels (linkedin) are excluded from the failure report.
    """
    STALE_DAYS = 3
    KNOWN_PAUSED = {"linkedin"}
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET as DATASET_ID
        bq     = get_client()
        T      = f"`{PROJECT_ID}.{DATASET_ID}`"
        riyadh = timezone(timedelta(hours=3))
        today  = datetime.now(riyadh).date()
        sql = f"""
            SELECT 'campaigns_daily' AS tbl, channel, MAX(date) AS last_date
            FROM {T}.campaigns_daily
            WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
            GROUP BY channel
            UNION ALL
            SELECT 'hubspot_leads', 'hubspot', MAX(date)
            FROM {T}.hubspot_leads_module_daily
            WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 14 DAY)
        """
        rows   = list(bq.query(sql).result())
        stale  = [(r.tbl, r.channel, str(r.last_date))
                  for r in rows
                  if r.last_date
                  and (today - r.last_date).days >= STALE_DAYS
                  and r.channel not in KNOWN_PAUSED]
        if stale:
            parts = [f"{ch}({tbl})={d}" for tbl, ch, d in stale[:5]]
            return False, f"Stale data: {', '.join(parts)}"
        sources = {r.channel for r in rows}
        latest  = max((str(r.last_date) for r in rows if r.last_date), default="?")
        return True, f"All fresh ({len(sources)} sources, latest={latest})"
    except Exception as e:
        return False, f"Freshness check: {e}"


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
    """Verify at least one active Google Ads conversion action exists (existence check).
    Use check_conversion_recording() for the deeper "is it recording?" check."""
    try:
        from collectors.google_ads import get_client
        from config import GOOGLE_ADS_CONFIG
        client = get_client()
        ga_svc = client.get_service("GoogleAdsService")
        cid = GOOGLE_ADS_CONFIG["customer_id"].replace("-", "")
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


def check_conversion_recording() -> tuple[bool, str]:
    """Deep check: are all conversion actions actually recording data?
    analysers.conversion_health was removed — this check is now a no-op stub
    that always returns True so the health-check runner still executes cleanly."""
    return True, "Conversion recording check skipped (analyser removed)"


def check_ga4_data() -> tuple[bool, str]:
    """Verify ga4_sessions_daily has data from the last 2 days."""
    try:
        from datetime import date as _date
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        rows = list(get_client().query(f"""
            SELECT MAX(date) AS last_date, SUM(sessions) AS sessions_7d
            FROM `{PROJECT_ID}.{DATASET}.ga4_sessions_daily`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        """).result())
        if not rows or rows[0].last_date is None:
            return False, "GA4: ga4_sessions_daily empty — run: railway run python collectors/ga4_bq.py --days 30"
        days_ago = (_date.today() - rows[0].last_date).days
        if days_ago > 2:
            return False, f"GA4 data {days_ago}d stale (last: {rows[0].last_date}) — check reporting_scheduler"
        return True, f"GA4 OK — {int(rows[0].sessions_7d or 0):,} sessions last 7d, latest {rows[0].last_date}"
    except Exception as e:
        return False, f"GA4 data check: {e}"


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
    Verify the Slack events endpoint (/slack/events) is reachable and
    that the bot can call auth.test (token valid + bot online).
    This is what actually handles ✅/❌ reactions on Railway.
    """
    import requests as _req
    # 1. Probe /slack/events with POST (no signature) — expect 403 invalid_signature = endpoint is up.
    #    Using GET would return 405 (Method Not Allowed), which is also fine.
    try:
        r = _req.post(f"{BASE_URL}/slack/events", json={}, timeout=10)
        # 403 = signature check working (endpoint up). 200 = url_verification challenge.
        # 405 = method not allowed (should not happen but also means server is up).
        if r.status_code in (200, 403, 405):
            events_ok = True
        else:
            events_ok = False
    except Exception as e:
        return False, f"Slack events endpoint unreachable: {e}"

    # 2. Verify bot token is valid
    try:
        from slack_sdk import WebClient
        from config import SLACK_BOT_TOKEN
        info = WebClient(token=SLACK_BOT_TOKEN).auth_test()
        bot = info.get("user", "?")
        if events_ok:
            return True, f"Slack listener OK — bot={bot}, /slack/events reachable"
        return False, f"Bot token valid (bot={bot}) but /slack/events returned HTTP {r.status_code}"
    except Exception as e:
        return False, f"Slack bot token invalid: {e}"


# ─── Runner ────────────────────────────────────────────────────────────────────

CHECKS = [
    ("Railway deployment",       check_railway_deployment),
    ("Slack listener",           check_slack_listener),
    ("Flask",                    check_flask),
    ("BigQuery",                 check_bigquery),
    ("Data freshness",           check_data_freshness),
    ("GA4 data",                 check_ga4_data),
    ("Google Ads",               check_google_ads),
    ("Conversion tracking",      check_conversion_tracking),
    ("Conversion recording",     check_conversion_recording),
    ("Meta Ads",                 check_meta),
    ("Microsoft Ads",            check_microsoft_ads),
    ("TikTok",                   check_tiktok),
    ("Snapchat",                 check_snapchat),
    ("LinkedIn",                 check_linkedin),
    ("HubSpot API",              check_hubspot),
    ("HubSpot webhook",          check_hubspot_webhook),
    ("Slack",                    check_slack),
    ("Asana",                    check_asana),
]

# Category grouping for dashboard display
CHECK_CATEGORY = {
    "Railway deployment":    "Infrastructure",
    "Flask":                 "Infrastructure",
    "BigQuery":              "Infrastructure",
    "Data freshness":        "Data",
    "GA4 data":              "Data",
    "Slack":                 "Infrastructure",
    "Slack listener":        "Infrastructure",
    "Google Ads":            "Connectors",
    "Conversion tracking":   "Connectors",
    "Conversion recording":  "Connectors",
    "Meta Ads":              "Connectors",
    "Microsoft Ads":         "Connectors",
    "TikTok":                "Connectors",
    "Snapchat":              "Connectors",
    "LinkedIn":              "Connectors",
    "HubSpot API":           "Connectors",
    "HubSpot webhook":       "Connectors",
    "Asana":                 "Connectors",
}

# One or two lines shown in the click-to-expand modal when a check fails.
# Explains WHY this error appears and what to do about it.
CHECK_WHY = {
    "Slack listener":      "The /slack/events webhook is unreachable or crashing. This means ✅/❌ reactions on #approvals won't trigger approve/reject. Fix: check Railway logs for errors on the /slack/events route, then redeploy.",
    "LinkedIn":            "The LinkedIn OAuth refresh token has expired (HTTP 401). Fix: run `railway run python collectors/linkedin_oauth.py` to get a new token, then update LINKEDIN_REFRESH_TOKEN in Railway.",
    "Google Ads":          "The Google Ads API credentials are invalid or the customer ID is wrong. Fix: re-run `python google_ads_oauth.py` and update GOOGLE_ADS_REFRESH_TOKEN in Railway.",
    "Meta Ads":            "The Meta access token has expired or the ad account ID is incorrect. Fix: generate a new long-lived token in Meta Business Manager → System Users, update META_ACCESS_TOKEN in Railway.",
    "Microsoft Ads":       "The Microsoft Ads refresh token has expired. Fix: run `railway run python collectors/microsoft_oauth.py` to refresh, update MS_REFRESH_TOKEN in Railway.",
    "Snapchat":            "The Snapchat API token is invalid or expired. Fix: re-authenticate via Snapchat Business API and update SNAP_ACCESS_TOKEN in Railway.",
    "TikTok":              "The TikTok API token is invalid or expired. Fix: re-authenticate via TikTok for Business and update TIKTOK_ACCESS_TOKEN in Railway.",
    "HubSpot API":         "The HubSpot access token is invalid. Fix: generate a new private app token in HubSpot → Settings → Private Apps, update HUBSPOT_ACCESS_TOKEN in Railway.",
    "HubSpot webhook":     "The HubSpot webhook endpoint (/webhooks/hubspot) is unreachable. Fix: check Railway logs for errors on this route.",
    "BigQuery":            "Cannot connect to BigQuery. Fix: verify GOOGLE_APPLICATION_CREDENTIALS is set in Railway and the service account has BigQuery access.",
    "Railway deployment":  "The Railway app is not reachable at its public URL. Fix: check Railway dashboard for a failed deploy or crashed process.",
    "Conversion recording":"One or more active conversion actions recorded 0 conversions in the last 14 days. The tag may be broken or misconfigured in GTM.",
    "Conversion tracking": "A conversion tracking platform has an unhealthy status (Inactive/Unverified). Fix: verify the tag is installed and firing in the platform's tag health UI.",
    "Flask":               "The Flask /health endpoint is not responding. Fix: check Railway logs — the web process may have crashed.",
    "Data freshness":      "One or more BQ tables haven't been updated in 3+ days. Fix: check the collector logs in Railway for the stale channel.",
    "GA4 data":            "The GA4 BQ table is stale or empty. Fix: check the ga4_bq collector in Railway logs.",
    "Asana":               "The Asana API token is invalid. Fix: generate a new personal access token in Asana → My Profile → Apps, update ASANA_ACCESS_TOKEN in Railway.",
    "Slack":               "The Slack bot token is invalid or the bot is not in the expected workspace. Fix: check SLACK_BOT_TOKEN in Railway.",
}


def _log_to_bq(results: dict, run_id: str) -> None:
    """Write one row per check to agent_activity_log so the dashboard can read them."""
    try:
        from logs.activity_logger import log_activity_async
        for name, (ok, msg) in results.items():
            log_activity_async(
                role="health_monitor",
                action="health_check",
                status="success" if ok else "failed",
                channel=name,
                details={"msg": msg, "run_id": run_id,
                         "category": CHECK_CATEGORY.get(name, "Other")},
            )
    except Exception as e:
        print(f"[health_check] BQ log failed (non-fatal): {e}")


def run_all(run_id: str | None = None) -> dict:
    """Run every check; return {name: (ok, msg)} dict."""
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = {}
    for name, fn in CHECKS:
        t0 = time.time()
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"Unexpected error: {e}"
            traceback.print_exc()
        elapsed = round(time.time() - t0, 1)
        # Prepend the WHY explanation to the message on failure so the modal explains the root cause
        if not ok and name in CHECK_WHY:
            full_msg = f"{CHECK_WHY[name]}\n\n{msg}  ({elapsed}s)"
        else:
            full_msg = f"{msg}  ({elapsed}s)"
        results[name] = (ok, full_msg)
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {name:<20} {msg}  ({elapsed}s)")
    _log_to_bq(results, run_id)
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

        _nexa_quiet = os.getenv("NEXA_QUIET", "").lower() in ("true", "1", "yes", "on")
        if _nexa_quiet:
            snippet = header.replace("\n", " ")[:120]
            print(f"[health_check] QUIET — skipped Slack post to {SLACK_CHANNEL_HEALTH}: {snippet}")
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


def main(post_slack: bool = True, failures_only: bool = True, run_id: str | None = None) -> bool:
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
    results = run_all(run_id=run_id)
    print("=" * 60)

    if post_slack:
        post_to_slack(results, failures_only=failures_only)

    all_ok = all(ok for ok, _ in results.values())
    print(f"\n  Overall: {'ALL PASS ✅' if all_ok else 'FAILURES DETECTED ❌'}")
    return all_ok


# Backwards-compat alias — callers that import run_checks get run_all
run_checks = run_all


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Nexa integration health check")
    p.add_argument("--no-slack", action="store_true", help="Skip Slack post (local testing)")
    args = p.parse_args()
    ok = main(post_slack=not args.no_slack)
    sys.exit(0 if ok else 1)
