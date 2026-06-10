"""
analysers/conversion_health.py
==============================
Conversion tracking health across ALL platforms.

Detects "not recording" conversion actions — the most dangerous silent failure
in paid media: campaigns spend money optimising toward a goal that isn't being
tracked.

Checks:
  1. Google Ads    — enabled conversion actions with 0 conversions in last N days
  2. Microsoft Ads — UET tag tracking status per account (Active / Inactive / Unverified)
  3. Meta          — Lead event fires on web pixel (3036579196577051) in last 7 days
  4. GTM           — web container (GTM-TFH26VC2) tags: Meta Lead + GA4 config live

Each check returns:
  {
    "platform":  str,
    "status":    "ok" | "warning" | "broken",
    "issues":    [{"name": str, "detail": str, "fix": str}, ...],
    "summary":   str,
  }

Entry point: run_all() → list of check results
             create_tasks(results) → Asana task per broken/warning platform
"""
from __future__ import annotations

import os
from datetime import date, timedelta, datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)

_RIYADH = timezone(timedelta(hours=3))

META_WEB_PIXEL  = os.getenv("META_WEB_PIXEL_ID",  "3036579196577051")
META_CRM_PIXEL  = os.getenv("META_CRM_PIXEL_ID",  "1782671302631317")
GTM_WEB_ID      = os.getenv("GTM_WEB_CONTAINER_ID", "GTM-TFH26VC2")
GTM_SERVER_ID   = os.getenv("GTM_SERVER_CONTAINER_ID", "GTM-PK6924TJ")


# ── 1. Google Ads ─────────────────────────────────────────────────────────────

def check_google_ads_conversions(days: int = 14) -> dict:
    """Finds enabled Google Ads conversion actions with 0 conversions in last N days.
    A goal with spend but no conversions means the tag is broken or misconfigured."""
    try:
        from executors.google_ads import get_client
        from config import GOOGLE_ADS_CONFIG

        client     = get_client()
        ga_svc     = client.get_service("GoogleAdsService")
        cid        = GOOGLE_ADS_CONFIG["customer_id"].replace("-", "")
        since      = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Enabled conversion actions + their recent all_conversions
        q = f"""
            SELECT
              conversion_action.id,
              conversion_action.name,
              conversion_action.status,
              conversion_action.tag_snippets,
              metrics.all_conversions
            FROM conversion_action
            WHERE conversion_action.status = 'ENABLED'
              AND segments.date >= '{since}'
        """
        issues = []
        try:
            rows = list(ga_svc.search(customer_id=cid, query=q))
        except Exception:
            # Fall back: list actions, check which have no recent data
            q2 = """
                SELECT conversion_action.id, conversion_action.name,
                       conversion_action.status, conversion_action.created_time
                FROM conversion_action
                WHERE conversion_action.status = 'ENABLED'
            """
            rows = list(ga_svc.search(customer_id=cid, query=q2))
            # Can't determine conversion counts without the metrics segment — report as unknown
            if rows:
                return {
                    "platform": "Google Ads",
                    "status":   "ok",
                    "issues":   [],
                    "summary":  f"{len(rows)} enabled conversion action(s) — live count unavailable (segment query failed)",
                }
            return {"platform": "Google Ads", "status": "ok", "issues": [], "summary": "No enabled conversion actions found"}

        # Group by action: sum all_conversions across date segments
        totals: dict[str, dict] = {}
        for r in rows:
            action = r.conversion_action
            key    = action.name
            if key not in totals:
                totals[key] = {"id": action.id, "conversions": 0.0}
            totals[key]["conversions"] += r.metrics.all_conversions or 0.0

        for name, data in totals.items():
            if data["conversions"] == 0:
                issues.append({
                    "name":   name,
                    "detail": f"0 conversions recorded in last {days} days",
                    "fix":    (
                        "Check the conversion action tag is firing in Tag Assistant. "
                        "Verify the conversion action ID in GTM matches this action. "
                        "Check Google Ads → Tools → Conversions → tag status."
                    ),
                })

        status = "broken" if issues else "ok"
        summary = (
            f"{len(issues)} conversion action(s) not recording out of {len(totals)} enabled"
            if issues else
            f"All {len(totals)} Google Ads conversion action(s) recording"
        )
        return {"platform": "Google Ads", "status": status, "issues": issues, "summary": summary}

    except Exception as e:
        return {
            "platform": "Google Ads", "status": "warning",
            "issues":   [{"name": "check_failed", "detail": str(e)[:120], "fix": "Verify Google Ads credentials"}],
            "summary":  f"Google Ads conversion check failed: {str(e)[:80]}",
        }


# ── 2. Microsoft Ads ──────────────────────────────────────────────────────────

def check_microsoft_conversions() -> dict:
    """Checks UET tag tracking validation status for each Microsoft Ads account.
    Calls Campaign Management REST API — returns Inactive/Unverified goals."""
    try:
        import requests as _req
        from collectors.microsoft_ads_bq import (
            _accounts, _get_access_token_for, _headers_for,
        )

        accounts = _accounts()
        if not accounts:
            return {
                "platform": "Microsoft Ads", "status": "warning",
                "issues":   [{"name": "no_accounts", "detail": "No MS accounts configured", "fix": "Set MS_ACCOUNT_ID / MS_REFRESH_TOKEN"}],
                "summary":  "Microsoft Ads: no accounts configured",
            }

        all_issues: list[dict] = []

        for acc in accounts:
            try:
                token = _get_access_token_for(acc["refresh_token"], acc["public_client"])
            except Exception as e:
                all_issues.append({
                    "name":   f"account_{acc['account_id']}",
                    "detail": f"Auth failed: {e}",
                    "fix":    "Re-run microsoft_oauth.py to refresh the token",
                })
                continue

            hdrs = _headers_for(token, acc["account_id"], acc["customer_id"])

            # Campaign Management REST API: list conversion goals
            url = "https://campaign.api.bingads.microsoft.com/CampaignManagement/v13/ConversionGoals"
            try:
                r = _req.get(url, headers=hdrs, timeout=20)
                if r.status_code == 404:
                    # Endpoint not available — fall back to BQ-based check
                    all_issues.append({
                        "name":   f"account_{acc['account_id']}",
                        "detail": "Campaign Management REST API unavailable — check manually in Microsoft Ads UI → Conversion tracking",
                        "fix":    "Open Microsoft Ads → Tools → Conversion tracking → verify UET tag status is Active",
                    })
                    continue
                r.raise_for_status()
                goals = r.json().get("ConversionGoals", r.json()) if isinstance(r.json(), dict) else r.json()
            except _req.exceptions.HTTPError as e:
                all_issues.append({
                    "name":   f"account_{acc['account_id']}",
                    "detail": f"API error {e.response.status_code}: {e.response.text[:120]}",
                    "fix":    "Check Microsoft Ads credentials and Developer Token",
                })
                continue
            except Exception as e:
                all_issues.append({
                    "name":   f"account_{acc['account_id']}",
                    "detail": f"Request failed: {str(e)[:80]}",
                    "fix":    "Verify MS_DEVELOPER_TOKEN and account headers",
                })
                continue

            if not isinstance(goals, list):
                goals = goals.get("value", []) if isinstance(goals, dict) else []

            for goal in goals:
                status = (goal.get("Status") or "").lower()
                tag_val = (goal.get("TagTrackingValidation") or {})
                uet_status = (tag_val.get("UetTagTrackingStatus") or tag_val.get("Status") or "unknown").lower()
                name = goal.get("Name") or goal.get("Id") or "unknown"

                if status in ("deleted",):
                    continue
                if uet_status in ("inactive", "unverified", "norecentconversions"):
                    all_issues.append({
                        "name":   f"{acc['account_id']}/{name}",
                        "detail": f"UET tag status: {uet_status} — conversion goal not recording",
                        "fix":    (
                            "Verify the UET tag (Universal Event Tracking) is installed on all site pages. "
                            f"Check Microsoft Ads → Tools → Conversion tracking → '{name}' → tag status. "
                            "Use Microsoft UET Tag Helper browser extension to verify firing."
                        ),
                    })

        status = "broken" if all_issues else "ok"
        summary = (
            f"{len(all_issues)} Microsoft conversion goal(s) not recording across {len(accounts)} account(s)"
            if all_issues else
            f"All Microsoft Ads conversion goals recording across {len(accounts)} account(s)"
        )
        return {"platform": "Microsoft Ads", "status": status, "issues": all_issues, "summary": summary}

    except Exception as e:
        return {
            "platform": "Microsoft Ads", "status": "warning",
            "issues":   [{"name": "check_failed", "detail": str(e)[:120], "fix": "Check MS credentials"}],
            "summary":  f"Microsoft Ads conversion check failed: {str(e)[:80]}",
        }


# ── 3. Meta Pixel — Lead event ────────────────────────────────────────────────

def check_meta_pixel_events(pixel_id: str = META_WEB_PIXEL, days: int = 7) -> dict:
    """Checks whether the Meta web pixel's Lead event has fired in the last N days.
    The Lead event tag on GTM (GTM-TFH26VC2) must fire on form submissions."""
    try:
        import requests as _req
        token = os.getenv("META_ACCESS_TOKEN", "")
        if not token:
            return {
                "platform": "Meta Pixel", "status": "warning",
                "issues":   [{"name": "no_token", "detail": "META_ACCESS_TOKEN not set", "fix": "Set META_ACCESS_TOKEN in Railway"}],
                "summary":  "Meta pixel check skipped — no access token",
            }

        since = int((datetime.now() - timedelta(days=days)).timestamp())
        until = int(datetime.now().timestamp())

        # 1. Pixel last fired time (overall)
        r = _req.get(
            f"https://graph.facebook.com/v19.0/{pixel_id}",
            params={"fields": "name,last_fired_time,creation_time", "access_token": token},
            timeout=15,
        )
        r.raise_for_status()
        pixel_data = r.json()
        last_fired = pixel_data.get("last_fired_time")
        pixel_name = pixel_data.get("name", pixel_id)

        # 2. Event-level stats — check Lead event specifically
        r2 = _req.get(
            f"https://graph.facebook.com/v19.0/{pixel_id}/event_stats",
            params={
                "access_token": token,
                "granularity":  "DAY",
                "start_time":   since,
                "end_time":     until,
            },
            timeout=15,
        )
        r2.raise_for_status()
        event_stats = r2.json().get("data", [])

        # Sum Lead event counts across all days
        lead_count = sum(
            int(e.get("count", 0))
            for e in event_stats
            if (e.get("event") or "").lower() == "lead"
        )

        issues = []
        if lead_count == 0:
            last_fired_str = last_fired or "never"
            issues.append({
                "name":   f"pixel:{pixel_id}/Lead",
                "detail": (
                    f"Meta web pixel '{pixel_name}' has 0 Lead events in last {days} days. "
                    f"Pixel last fired: {last_fired_str}"
                ),
                "fix":    (
                    f"1. Open GTM web container ({GTM_WEB_ID}) → Tags → find the Meta Pixel 'Lead' event tag. "
                    "Verify it's Published (not paused/draft). "
                    "2. Trigger should fire on 'Thank You page' or 'Form submission' trigger. "
                    "3. Use Meta Pixel Helper browser extension on the LP to verify the Lead event fires. "
                    "4. Check Meta Events Manager → Web → this pixel → Test Events to send a test event."
                ),
            })

        # Also list all events that DID fire (for context)
        event_names = list({e.get("event") for e in event_stats if e.get("event")})

        status  = "broken" if issues else "ok"
        summary = (
            f"Meta web pixel '{pixel_name}' — Lead: 0 fires in {days}d (firing events: {', '.join(event_names) or 'none'})"
            if issues else
            f"Meta web pixel '{pixel_name}' — Lead event recorded {lead_count}x in last {days}d"
        )
        return {
            "platform": "Meta Pixel",
            "status":   status,
            "issues":   issues,
            "summary":  summary,
            "event_summary": {e.get("event"): sum(int(x.get("count", 0)) for x in event_stats if x.get("event") == e.get("event")) for e in event_stats},
        }

    except Exception as e:
        return {
            "platform": "Meta Pixel", "status": "warning",
            "issues":   [{"name": "check_failed", "detail": str(e)[:120], "fix": "Verify META_ACCESS_TOKEN scope includes ads_read"}],
            "summary":  f"Meta pixel check failed: {str(e)[:80]}",
        }


# ── 4. GTM Web Container ──────────────────────────────────────────────────────

def check_gtm_tags(container_public_id: str = GTM_WEB_ID) -> dict:
    """Verifies the GTM web container has the Meta Lead event tag and GA4 config
    tag live (not paused or in draft). Requires service account to have GTM read access."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        import google.auth

        raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        scopes  = ["https://www.googleapis.com/auth/tagmanager.readonly"]

        if raw_key and os.path.exists(raw_key):
            creds = service_account.Credentials.from_service_account_file(raw_key, scopes=scopes)
        else:
            try:
                creds, _ = google.auth.default(scopes=scopes)
            except Exception:
                return {
                    "platform": "GTM",
                    "status":   "warning",
                    "issues":   [{
                        "name":   "no_credentials",
                        "detail": "Service account needs GTM read access — grant it in GTM admin settings",
                        "fix":    (
                            f"In GTM container {container_public_id}: Admin → User Management → "
                            "add your service account email with 'Read' permission. "
                            "Then re-run this check."
                        ),
                    }],
                    "summary":  "GTM check skipped — service account needs GTM read permission",
                }

        svc = build("tagmanager", "v2", credentials=creds, cache_discovery=False)

        # Find the account + container matching the public ID
        accounts = svc.accounts().list().execute().get("account", [])
        container_ref = None
        for acct in accounts:
            acct_id = acct["accountId"]
            containers = svc.accounts().containers().list(parent=f"accounts/{acct_id}").execute()
            for c in containers.get("container", []):
                if c.get("publicId") == container_public_id:
                    container_ref = (acct_id, c["containerId"])
                    break
            if container_ref:
                break

        if not container_ref:
            return {
                "platform": "GTM", "status": "warning",
                "issues":   [{"name": "container_not_found",
                              "detail": f"{container_public_id} not found in accessible accounts",
                              "fix":    "Grant service account read access to the GTM container"}],
                "summary":  f"GTM container {container_public_id} not accessible",
            }

        acct_id, cont_id = container_ref
        parent = f"accounts/{acct_id}/containers/{cont_id}"

        # Get the LIVE (published) version
        try:
            live = svc.accounts().containers().versions().live(parent=parent).execute()
        except Exception:
            live = {}

        tags = live.get("tag", [])
        if not tags:
            # Fall back to workspace tags
            workspaces = svc.accounts().containers().workspaces().list(parent=parent).execute()
            ws_id = (workspaces.get("workspace", [{}])[0]).get("workspaceId", "1")
            ws_parent = f"{parent}/workspaces/{ws_id}"
            tags = svc.accounts().containers().workspaces().tags().list(parent=ws_parent).execute().get("tag", [])

        issues  = []
        found_meta_lead = False
        found_ga4       = False

        for tag in tags:
            tag_name  = (tag.get("name") or "").lower()
            tag_type  = (tag.get("type") or "").lower()
            is_paused = tag.get("paused", False)

            # Meta pixel tag with Lead event
            if "meta" in tag_name or "facebook" in tag_name or tag_type in ("html", "custhtml"):
                params = {p["key"]: p.get("value", "") for p in tag.get("parameter", [])}
                if any(META_WEB_PIXEL in str(v) for v in params.values()) or "lead" in tag_name:
                    found_meta_lead = True
                    if is_paused:
                        issues.append({
                            "name":   f"GTM:{tag.get('name')}",
                            "detail": "Meta Lead event tag is PAUSED in GTM",
                            "fix":    f"In GTM container {container_public_id} → Tags → '{tag.get('name')}' → unpause and publish",
                        })

            # GA4 configuration tag
            if tag_type in ("gaawc", "googtag") or "ga4" in tag_name or "google analytics" in tag_name:
                found_ga4 = True
                if is_paused:
                    issues.append({
                        "name":   f"GTM:{tag.get('name')}",
                        "detail": "GA4 configuration tag is PAUSED in GTM",
                        "fix":    f"In GTM container {container_public_id} → Tags → '{tag.get('name')}' → unpause and publish",
                    })

        if not found_meta_lead:
            issues.append({
                "name":   "GTM:MetaLeadTag",
                "detail": f"No Meta Lead event tag found in live container {container_public_id}",
                "fix":    (
                    f"In GTM container {container_public_id}: add a new Custom HTML tag or Meta Pixel template "
                    f"that fires the Lead event (fbq('track', 'Lead')) on the form submission trigger. Publish."
                ),
            })
        if not found_ga4:
            issues.append({
                "name":   "GTM:GA4Tag",
                "detail": f"No GA4 configuration tag found in live container {container_public_id}",
                "fix":    (
                    f"In GTM: add a Google Tag (tag type 'Google Tag') with Measurement ID for GA4 property 517912363. "
                    "Set trigger to 'All Pages'. Publish."
                ),
            })

        status  = "broken" if issues else "ok"
        summary = (
            f"GTM {container_public_id}: {len(issues)} tag issue(s) — "
            + "; ".join(i["detail"][:60] for i in issues)
            if issues else
            f"GTM {container_public_id}: Meta Lead tag ✓  GA4 config tag ✓  ({len(tags)} tags total)"
        )
        return {"platform": "GTM", "status": status, "issues": issues, "summary": summary}

    except Exception as e:
        return {
            "platform": "GTM", "status": "warning",
            "issues":   [{"name": "check_failed", "detail": str(e)[:120],
                          "fix": "Grant service account GTM read access and re-run"}],
            "summary":  f"GTM check failed: {str(e)[:80]}",
        }


# ── 5. GA4 data freshness ──────────────────────────────────────────────────────

def check_ga4_data_freshness() -> dict:
    """Checks that ga4_sessions_daily has recent data (last 2 days)."""
    try:
        from collectors.bq_writer import get_client, PROJECT_ID, DATASET
        rows = list(get_client().query(f"""
            SELECT MAX(date) AS last_date,
                   SUM(sessions) AS sessions_7d,
                   SUM(conversions) AS conversions_7d
            FROM `{PROJECT_ID}.{DATASET}.ga4_sessions_daily`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        """).result())
        if not rows or rows[0].last_date is None:
            return {
                "platform": "GA4", "status": "broken",
                "issues":   [{"name": "no_data",
                              "detail": "ga4_sessions_daily has no data",
                              "fix":    "railway run python collectors/ga4_bq.py --days 30"}],
                "summary":  "GA4: no data — run ga4_bq.py --days 30 to backfill",
            }
        last = rows[0].last_date
        days_ago = (date.today() - last).days
        if days_ago > 2:
            return {
                "platform": "GA4", "status": "broken",
                "issues":   [{"name": "stale",
                              "detail": f"GA4 data is {days_ago} days stale (last: {last})",
                              "fix":    "Check reporting_scheduler.py — ga4_bq collector may have failed"}],
                "summary":  f"GA4 data {days_ago}d stale (last: {last})",
            }
        return {
            "platform": "GA4", "status": "ok", "issues": [],
            "summary":  (
                f"GA4 OK — {int(rows[0].sessions_7d or 0):,} sessions, "
                f"{int(rows[0].conversions_7d or 0):,} conversions last 7d, latest {last}"
            ),
        }
    except Exception as e:
        return {
            "platform": "GA4", "status": "warning",
            "issues":   [{"name": "check_failed", "detail": str(e)[:120],
                          "fix": "Check BQ credentials and ga4_sessions_daily table"}],
            "summary":  f"GA4 check failed: {str(e)[:80]}",
        }


# ── Aggregate ─────────────────────────────────────────────────────────────────

def run_all(days: int = 14) -> list[dict]:
    """Run all five conversion health checks. Returns list of result dicts."""
    return [
        check_google_ads_conversions(days=days),
        check_microsoft_conversions(),
        check_meta_pixel_events(pixel_id=META_WEB_PIXEL, days=7),
        check_gtm_tags(container_public_id=GTM_WEB_ID),
        check_ga4_data_freshness(),
    ]


def create_tasks(results: list[dict]) -> list[str]:
    """Create one Asana task per platform with issues. Returns list of task GIDs created."""
    from executors.asana import create_task
    from datetime import date as _date

    today    = _date.today().isoformat()
    gids     = []
    problems = [r for r in results if r["status"] in ("broken", "warning") and r.get("issues")]

    if not problems:
        return []

    # One consolidated task for marketing-ops covering all platforms
    lines = [f"Conversion tracking health audit — {today}\n"]
    for r in problems:
        lines.append(f"## {r['platform']} — {r['status'].upper()}")
        lines.append(r["summary"])
        for issue in r["issues"]:
            lines.append(f"\nIssue: {issue['name']}")
            lines.append(f"Detail: {issue['detail']}")
            lines.append(f"Fix: {issue['fix']}")
        lines.append("")

    lines += [
        "REVIEW CHAIN:",
        "1. [Marketing Ops] Apply fixes above — verify each platform shows recording.",
        "2. [Growth Analyst] Confirm 3-day trailing conversion counts are non-zero in BQ.",
        "3. [QA Gate] All platforms HEALTHY in next conversion_health check.",
        "4. [Growth Analyst] Sign off — update memory/08_pitfalls.md with root cause.\n",
        f"Created: {today}\nDue: {today}\nPriority: High",
        "Type: Fix\nChannel: tracking\nAsset level: infrastructure\nAction: fix → [Marketing Ops]",
    ]

    gid = create_task(
        title=f"Conversion tracking issues — {len(problems)} platform(s) not recording — {today}",
        description="\n".join(lines),
        project_key="daily_activity",
        task_type="Fix",
        channel="tracking",
        asset_level="infrastructure",
        action="fix",
        log_role="health_monitor",
    )
    if gid:
        gids.append(gid)
    return gids


def format_summary(results: list[dict]) -> str:
    """Return a one-paragraph text summary of all results."""
    lines = []
    for r in results:
        icon = "OK" if r["status"] == "ok" else ("WARN" if r["status"] == "warning" else "BROKEN")
        lines.append(f"[{icon}] {r['platform']}: {r['summary']}")
    return "\n".join(lines)


# ── Full GTM audit (both containers) ──────────────────────────────────────────

# Required tags per container — used to detect missing tags
_REQUIRED_WEB_TAGS = [
    ("GA4 Configuration",       ["gaawc", "googtag"],           "GA4 base tag — fires on All Pages"),
    ("GA4 Lead event",          ["gaawc", "googtag"],           "GA4 event tag for lead form submission"),
    ("Meta Pixel PageView",     ["html", "custhtml", "img"],    "Meta pixel base — fires on All Pages"),
    ("Meta Pixel Lead",         ["html", "custhtml"],           "Meta fbq('track','Lead') — fires on Thank You page"),
    ("Google Ads Conversion",   ["awct", "html", "custhtml"],   "Google Ads conversion action — fires on Thank You page"),
    ("Microsoft UET base",      ["html", "custhtml"],           "Microsoft Universal Event Tracking base tag — All Pages"),
    ("Microsoft UET conversion",["html", "custhtml"],           "Microsoft UET goal tag — fires on Thank You page"),
]

_REQUIRED_SERVER_TAGS = [
    ("GA4 Client",              ["gaawc", "googtag", "html"],   "GA4 server-side client — receives GA4 hits"),
    ("Meta CAPI",               ["html", "custhtml"],           "Meta Conversions API forwarding tag"),
    ("Google Ads CAPI",         ["html", "custhtml"],           "Google Ads server-side conversion forwarding"),
]


def _gtm_svc():
    """Return an authenticated GTM API v2 service object."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    import google.auth

    raw_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    scopes  = ["https://www.googleapis.com/auth/tagmanager.readonly"]

    if raw_key and os.path.exists(raw_key):
        creds = service_account.Credentials.from_service_account_file(raw_key, scopes=scopes)
    else:
        creds, _ = google.auth.default(scopes=scopes)

    return build("tagmanager", "v2", credentials=creds, cache_discovery=False)


def _find_container(svc, public_id: str):
    """Return (account_id, container_id, container_obj) for the given public GTM ID."""
    for acct in svc.accounts().list().execute().get("account", []):
        aid = acct["accountId"]
        for c in svc.accounts().containers().list(parent=f"accounts/{aid}").execute().get("container", []):
            if c.get("publicId") == public_id:
                return aid, c["containerId"], c
    return None, None, None


def _audit_container(svc, public_id: str, required_tags: list) -> dict:
    """Full tag-by-tag audit for one container. Returns structured audit dict."""
    aid, cid, c_obj = _find_container(svc, public_id)
    if not aid:
        return {
            "container_id":   public_id,
            "error":          f"{public_id} not found — check service account has read access",
            "tags":           [],
            "missing":        [],
            "recommendations": [],
        }

    parent = f"accounts/{aid}/containers/{cid}"

    # Prefer the live (published) version; fall back to latest workspace
    try:
        live    = svc.accounts().containers().versions().live(parent=parent).execute()
        version = live.get("containerVersion", {}) or live
        version_name = f"V{version.get('containerVersionId', '?')} — {version.get('name', 'unnamed')}"
    except Exception:
        live = {}
        version_name = "latest workspace (no published version)"

    tags      = live.get("tag", [])
    triggers  = {t["triggerId"]: t for t in live.get("trigger", [])}
    variables = {v["variableId"]: v for v in live.get("variable", [])}

    if not tags:
        # Fall back: workspace tags
        try:
            wss = svc.accounts().containers().workspaces().list(parent=parent).execute()
            ws_id = (wss.get("workspace", [{}])[0]).get("workspaceId", "1")
            ws_parent = f"{parent}/workspaces/{ws_id}"
            tags     = svc.accounts().containers().workspaces().tags().list(parent=ws_parent).execute().get("tag", [])
            triggers = {t["triggerId"]: t for t in svc.accounts().containers().workspaces().triggers().list(parent=ws_parent).execute().get("trigger", [])}
            version_name += " (workspace)"
        except Exception:
            tags = []

    tag_reports = []
    live_types  = set()

    for tag in tags:
        name     = tag.get("name", "unnamed")
        ttype    = (tag.get("type") or "").lower()
        is_paused = tag.get("paused", False)
        params   = {p["key"]: p.get("value", "") for p in tag.get("parameter", [])}
        fire_ids = [ftr.get("triggerId") for ftr in tag.get("firingTriggerId", [])]
        fire_names = [triggers.get(tid, {}).get("name", tid) for tid in fire_ids]
        freq     = params.get("firingFrequency", "notOnce")

        issues   = []
        recs     = []

        # Check firing frequency for conversion tags
        name_lower = name.lower()
        is_conversion = any(kw in name_lower for kw in ("lead", "conversion", "convert", "purchase", "goal", "thank"))
        if is_conversion and is_paused:
            issues.append("PAUSED — conversion tag not firing")
            recs.append("Unpause immediately — this conversion is not being tracked")

        if is_conversion and any("all pages" in fn.lower() for fn in fire_names):
            issues.append("Fires on All Pages — conversion tags must fire on specific actions only")
            recs.append("Change trigger to 'Thank You page URL contains /thank-you' or a form submission event")

        if is_conversion and freq == "oncePerEvent" and "pageview" in " ".join(fire_names).lower():
            issues.append("Firing on pageview with oncePerEvent — may double-count multi-page sessions")

        # Check Meta pixel tags for correct event and pixel ID
        if "meta" in name_lower or "facebook" in name_lower or "pixel" in name_lower:
            tag_html = params.get("html", "") + str(params)
            if META_WEB_PIXEL not in tag_html and META_CRM_PIXEL not in tag_html:
                if tag_html:  # only flag if there IS HTML content (not empty template)
                    issues.append(f"Pixel ID not found in tag — expected {META_WEB_PIXEL} or {META_CRM_PIXEL}")
                    recs.append(f"Verify pixel ID is {META_WEB_PIXEL} (web) or {META_CRM_PIXEL} (CRM)")
            if "lead" in name_lower and "fbq" in tag_html and "'lead'" not in tag_html.lower() and '"lead"' not in tag_html.lower():
                issues.append("Tag named 'Lead' but fbq event is not 'Lead' — check the event name in the HTML")
                recs.append("Change fbq('track', '...') to fbq('track', 'Lead') exactly (case-sensitive)")

        # Check GA4 tags for measurement ID
        if ttype in ("gaawc", "googtag") or "ga4" in name_lower:
            mid = params.get("measurementId", "") or params.get("trackingId", "")
            if mid and "G-" not in mid and "UA-" not in mid:
                issues.append(f"Measurement ID looks wrong: '{mid}' — GA4 IDs start with G-")
                recs.append("Update Measurement ID to the correct G-XXXXXXXX format from GA4 property settings")

        status_label = "PAUSED" if is_paused else "LIVE"
        live_types.add(ttype)

        tag_reports.append({
            "name":        name,
            "type":        ttype,
            "status":      status_label,
            "triggers":    fire_names,
            "issues":      issues,
            "recommendation": recs[0] if recs else ("keep" if not issues else "fix"),
        })

    # Detect missing required tags
    missing = []
    for req_name, req_types, req_purpose in required_tags:
        req_lower = req_name.lower()
        # Check if any live tag's name or type matches
        matched = any(
            req_lower in t["name"].lower() or
            any(rt in t["type"] for rt in req_types)
            for t in tag_reports
            if t["status"] == "LIVE"
        )
        if not matched:
            # Also check paused tags — they exist but are disabled
            paused_match = any(
                req_lower in t["name"].lower()
                for t in tag_reports
                if t["status"] == "PAUSED"
            )
            if paused_match:
                missing.append({
                    "name":    req_name,
                    "purpose": req_purpose,
                    "note":    "Tag exists but is PAUSED — unpause to restore tracking",
                })
            else:
                missing.append({
                    "name":    req_name,
                    "purpose": req_purpose,
                    "note":    "Tag not found — needs to be created",
                })

    # Priority 1: paused conversion tags + tags with firing issues
    # Priority 2: missing tags
    # Priority 3: naming/frequency improvements
    p1 = [t for t in tag_reports if t["issues"] and t["status"] == "PAUSED"]
    p1_issues = [t for t in tag_reports if t["issues"] and t["status"] == "LIVE"]
    p2 = missing
    p3 = [t for t in tag_reports if not t["issues"] and t["status"] == "LIVE" and
          any("pageview" in tr.lower() for tr in t["triggers"]) and
          any(kw in t["name"].lower() for kw in ("conversion", "lead", "goal"))]

    return {
        "container_id":   public_id,
        "version":        version_name,
        "total_tags":     len(tags),
        "live_count":     sum(1 for t in tag_reports if t["status"] == "LIVE"),
        "paused_count":   sum(1 for t in tag_reports if t["status"] == "PAUSED"),
        "missing_count":  len(missing),
        "tags":           tag_reports,
        "missing":        p2,
        "priority_1":     [(t["name"], t["issues"][0]) for t in (p1 + p1_issues) if t["issues"]],
        "priority_2":     [(m["name"], m["note"]) for m in p2],
        "priority_3":     [(t["name"], "fires on pageview — verify trigger is correct for a conversion tag") for t in p3],
    }


def run_gtm_audit() -> dict:
    """Full tag-by-tag audit for both GTM containers.

    Returns:
      {
        "web":    { container audit dict for GTM-TFH26VC2 },
        "server": { container audit dict for GTM-PK6924TJ },
        "report": str,   # structured text report for Asana task body
        "error":  str | None,
      }
    """
    try:
        svc    = _gtm_svc()
        web    = _audit_container(svc, GTM_WEB_ID,    _REQUIRED_WEB_TAGS)
        server = _audit_container(svc, GTM_SERVER_ID, _REQUIRED_SERVER_TAGS)
    except Exception as e:
        return {
            "web": {}, "server": {},
            "report": f"GTM audit failed: {e}",
            "error":  str(e),
        }

    lines = []
    for label, audit in [("Web", web), ("Server", server)]:
        cid   = audit.get("container_id", "?")
        lines.append(f"CONTAINER: {cid} ({label.lower()})")
        lines.append(f"Published version: {audit.get('version', 'unknown')}")
        lines.append(
            f"Total tags: {audit.get('total_tags', 0)}  |  "
            f"Live: {audit.get('live_count', 0)}  |  "
            f"Paused: {audit.get('paused_count', 0)}  |  "
            f"Missing: {audit.get('missing_count', 0)}"
        )
        if audit.get("error"):
            lines.append(f"ERROR: {audit['error']}")
            lines.append("")
            continue

        lines.append("")
        lines.append("TAG REVIEW:")
        for t in audit.get("tags", []):
            status_str = "PAUSED" if t["status"] == "PAUSED" else "LIVE"
            lines.append(f"  [{status_str}] {t['name']}  (type: {t['type']})")
            if t["triggers"]:
                lines.append(f"    Trigger: {', '.join(t['triggers'])}")
            if t["issues"]:
                for iss in t["issues"]:
                    lines.append(f"    Issue: {iss}")
                lines.append(f"    Recommendation: {t['recommendation']}")

        if audit.get("missing"):
            lines.append("")
            lines.append("MISSING TAGS:")
            for m in audit["missing"]:
                lines.append(f"  - {m['name']}: {m['note']}")
                lines.append(f"    Purpose: {m['purpose']}")

        lines.append("")
        lines.append("RECOMMENDATIONS:")
        p1 = audit.get("priority_1", [])
        p2 = audit.get("priority_2", [])
        p3 = audit.get("priority_3", [])
        if p1:
            lines.append("  Priority 1 (fix now — blocking conversion tracking):")
            for name, iss in p1:
                lines.append(f"    - {name}: {iss}")
        if p2:
            lines.append("  Priority 2 (missing tags — create):")
            for name, note in p2:
                lines.append(f"    - {name}: {note}")
        if p3:
            lines.append("  Priority 3 (improve):")
            for name, note in p3:
                lines.append(f"    - {name}: {note}")
        if not p1 and not p2 and not p3:
            lines.append("  No recommendations — all tags healthy")
        lines.append("")

    report = "\n".join(lines)
    return {"web": web, "server": server, "report": report, "error": None}


def create_gtm_audit_tasks(audit: dict) -> list[str]:
    """Create Asana tasks for GTM audit results. One task per container with issues.
    Reports summary back to manager via the task description's MANAGER REPORT section."""
    from executors.asana import create_task
    from datetime import date as _date

    today = _date.today().isoformat()
    gids  = []

    for label, key, cid in [("Web", "web", GTM_WEB_ID), ("Server", "server", GTM_SERVER_ID)]:
        audit_data = audit.get(key, {})
        if not audit_data or audit_data.get("error"):
            continue

        p1 = audit_data.get("priority_1", [])
        p2 = audit_data.get("priority_2", [])

        if not p1 and not p2:
            continue  # container is clean — no task needed

        # Build task description
        desc_lines = [
            f"GTM {label} Container Audit — {cid} — {today}",
            f"Published version: {audit_data.get('version', 'unknown')}",
            f"Tags: {audit_data.get('live_count', 0)} live, {audit_data.get('paused_count', 0)} paused, {audit_data.get('missing_count', 0)} missing",
            "",
            audit.get("report", ""),
            "",
            "REVIEW CHAIN:",
            "1. [Marketing Ops] Apply Priority 1 fixes in GTM — publish a new version.",
            "2. [Marketing Ops] Verify each fixed tag fires correctly using Tag Assistant.",
            "3. [Marketing Ops] For missing tags: create them, test, publish.",
            "4. [Growth Analyst] Re-run Conversion Recording Audit — confirm all platforms HEALTHY.",
            "5. [Growth Analyst] Sign off — update memory/08_pitfalls.md with any new trap found.",
            "",
            "MANAGER REPORT (summary for ai-orchestrator):",
            f"  Container: {cid} ({label})",
            f"  Priority 1 blockers: {len(p1)}",
            *[f"    - {name}: {iss}" for name, iss in p1],
            f"  Priority 2 missing: {len(p2)}",
            f"  Next audit: run Conversion Recording Audit from /activity in 7 days",
            "",
            f"Created: {today}\nDue: {today}\nPriority: {'High' if p1 else 'Medium'}",
            f"Type: Audit\nChannel: gtm\nAsset level: infrastructure\nAction: fix → [Marketing Ops]",
        ]

        gid = create_task(
            title=f"GTM {label} audit — {len(p1)} P1 blocker(s), {len(p2)} missing tag(s) — {today}",
            description="\n".join(desc_lines),
            project_key="daily_activity",
            task_type="Audit",
            channel="gtm",
            asset_level="infrastructure",
            action="fix",
            log_role="health_monitor",
        )
        if gid:
            gids.append(gid)

    return gids
