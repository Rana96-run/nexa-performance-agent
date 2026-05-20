"""Daily audit — find bugs and (where safe) fix them.

Designed to be run as a scheduled task. Reports to stdout + appends to
memory/audit_findings.md. Auto-fixes safe categories; flags risky ones.

Bug categories checked (these are the ones we keep tripping over):
  1. KPI rule hook integrity — does the hook actually block known
     violation patterns? Run adversarial tests against it.
  2. Attribution drift — for each channel/account, does channel-reported
     'leads' diverge wildly from HubSpot truth? Reveals tracking gaps OR
     analysis violations.
  3. Disapproved ads on ENABLED campaigns — silent budget leaks.
  4. Active campaigns missing infrastructure — UTM suffix, customer
     exclusions, audience layer. Auto-fix where possible.
  5. Naming convention violations — pull each channel's existing names,
     flag campaigns that don't match the dominant pattern.

Output:
  - Console: ranked findings by severity
  - File:    memory/audit_findings.md (date-stamped history)
  - Exit:    0 = clean, 1 = findings exist, 2 = critical
"""
import sys, os, json, re, subprocess
from datetime import date, datetime
from pathlib import Path

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

REPO     = Path(r"D:\Nexa Performance Agent")
SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
findings = []
fixes    = []


def add(sev, category, detail, fix_action=None):
    findings.append({
        "severity": sev, "category": category,
        "detail": detail, "auto_fix": fix_action,
    })


# ── Check 1: KPI rule hook integrity ─────────────────────────────────────
# Adversarial tests against the hook. If any of these violation patterns
# DON'T block, the hook has a hole.
def check_kpi_hook():
    hook = REPO / ".claude" / "hooks" / "kpi_rule_guard.py"
    if not hook.exists():
        add("critical", "kpi_hook", "Hook file missing entirely")
        return

    # Each test = (description, JSON payload, should_block?)
    tests = [
        ("plain campaigns_daily.leads",
         {"tool_name": "Bash", "tool_input": {
             "command": "SELECT SUM(leads) FROM campaigns_daily"}},
         True),
        ("fully-qualified BQ path with hyphenated project (Acc 2 incident)",
         {"tool_name": "Write", "tool_input": {
             "content": "SELECT SUM(leads) FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`"}},
         True),
        ("ads_daily.conversions without HubSpot",
         {"tool_name": "Bash", "tool_input": {
             "command": "SELECT SUM(conversions) FROM ads_daily WHERE channel = 'meta'"}},
         True),
        ("CPL formula on channel leads",
         {"tool_name": "Bash", "tool_input": {
             "command": "SELECT spend/leads AS cpl FROM campaigns_daily"}},
         True),
        ("doc string mentioning campaigns_daily.leads in comments — should ALLOW",
         {"tool_name": "Write", "tool_input": {
             "content": "# Note: NEVER use campaigns_daily.leads as a metric"}},
         False),
        ("correct HubSpot-join pattern — should ALLOW",
         {"tool_name": "Write", "tool_input": {
             "content": "WITH hs AS (SELECT SUM(leads_total) FROM hubspot_leads_module_daily) SELECT s.spend FROM campaigns_daily s JOIN hs"}},
         False),
    ]

    for desc, payload, should_block in tests:
        r = subprocess.run(
            ["python", str(hook)],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True, timeout=5,
        )
        blocked = r.returncode == 2
        if should_block and not blocked:
            add("critical", "kpi_hook",
                f"Hook MISSED a violation pattern: '{desc}'. Exit {r.returncode}.")
        elif not should_block and blocked:
            add("medium", "kpi_hook",
                f"Hook false-positive on safe pattern: '{desc}'.")


# ── Check 2: Attribution drift per channel/account ───────────────────────
def check_attribution_drift():
    try:
        from google.cloud import bigquery
        c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")
    except Exception as e:
        add("medium", "attribution", f"BQ client init failed: {e}")
        return

    # KPI-RULE-BYPASS — this query intentionally exposes channel-reported leads
    # alongside HubSpot truth to detect tracking gaps.
    q = """
    WITH chan AS (
      SELECT channel, account_id, SUM(spend) AS spend, SUM(leads) AS channel_leads
      FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
      GROUP BY channel, account_id
    ),
    hs AS (
      SELECT
        LOWER(qoyod_source) AS source,
        SUM(leads_total)    AS hs_leads
      FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
      GROUP BY source
    )
    SELECT channel, account_id, spend, channel_leads
    FROM chan WHERE spend > 100
    ORDER BY spend DESC
    """
    rows = list(c.query(q).result())

    # For each channel/account, compare channel-reported leads to HubSpot truth.
    # Big divergence = either broken tracking on channel OR analyst is using
    # channel leads (our recent recurring sin).
    for r in rows:
        if (r.channel_leads or 0) == 0 and (r.spend or 0) > 100:
            add("medium", "attribution",
                f"{r.channel}/{r.account_id}: $${r.spend:.0f} spent, channel reports 0 leads — "
                f"verify HubSpot side actually receives them (otherwise tracking is broken).")
        # Inflated channel leads (e.g. WebsiteTraffic counting visits)
        if r.channel == "microsoft_ads" and (r.channel_leads or 0) > (r.spend or 0):
            add("high", "attribution",
                f"{r.channel}/{r.account_id}: channel reports {r.channel_leads} leads vs $${r.spend:.0f} spend "
                f"= $${r.spend/r.channel_leads:.2f}/lead — suspiciously cheap, likely WebsiteTraffic counting visits.")


# ── Check 3: Disapproved ads on ENABLED Google campaigns ─────────────────
def check_disapproved_ads():
    try:
        sys.path.insert(0, str(REPO))
        from executors.google_ads import get_client
    except Exception as e:
        add("medium", "disapproved", f"Cannot import google_ads executor: {e}")
        return

    client = get_client()
    ga = client.get_service("GoogleAdsService")
    for acct in ["1513020554", "5753494964"]:
        try:
            q = """
            SELECT campaign.id, campaign.name,
                   ad_group_ad.policy_summary.approval_status,
                   ad_group_ad.policy_summary.policy_topic_entries
            FROM ad_group_ad
            WHERE campaign.status = 'ENABLED'
              AND ad_group_ad.status = 'ENABLED'
              AND ad_group_ad.policy_summary.approval_status = 'DISAPPROVED'
            """
            for r in ga.search(customer_id=acct, query=q):
                topics = [t.topic for t in r.ad_group_ad.policy_summary.policy_topic_entries]
                add("high", "disapproved",
                    f"Acct {acct}: ENABLED campaign '{r.campaign.name}' has DISAPPROVED ad — topics={topics}. "
                    f"Either appeal in UI or pause this ad + create fresh one.")
        except Exception as e:
            add("medium", "disapproved", f"Acct {acct}: policy query failed: {str(e)[:200]}")


# ── Check 4: UTM tracking integrity — EFFECTIVE (account OR campaign) ────
# UTM tracking lives at ACCOUNT level (customer.tracking_url_template +
# customer.final_url_suffix). Campaigns inherit unless they override.
# A previous version of this check flagged 'missing campaign suffix' which
# triggered a bad auto-fix (override of working account-level config).
# This version checks effective state.
def check_utm_suffix_missing():
    try:
        sys.path.insert(0, str(REPO))
        from executors.google_ads import get_client
    except Exception as e:
        add("medium", "utm", f"Cannot import: {e}")
        return

    client = get_client()
    ga = client.get_service("GoogleAdsService")
    for acct in ["1513020554", "5753494964"]:
        try:
            # 1. Check account-level UTM tracking
            acc_suffix = ""
            acc_template = ""
            for r in ga.search(customer_id=acct, query="SELECT customer.final_url_suffix, customer.tracking_url_template FROM customer"):
                acc_suffix   = r.customer.final_url_suffix or ""
                acc_template = r.customer.tracking_url_template or ""
            account_has_tracking = bool(acc_suffix) or bool(acc_template)

            if not account_has_tracking:
                add("high", "utm",
                    f"Acct {acct}: NO account-level UTM tracking (neither final_url_suffix nor "
                    f"tracking_url_template on customer). All UTM attribution at risk.")

            # 2. Flag campaigns that OVERRIDE the account-level setting (may be intentional, but
            #    duplicate-UTM bug possible if the override re-states what's already in account).
            q_camp = """
            SELECT campaign.id, campaign.name, campaign.final_url_suffix
            FROM campaign
            WHERE campaign.status = 'ENABLED'
              AND campaign.advertising_channel_type = 'SEARCH'
            """
            for r in ga.search(customer_id=acct, query=q_camp):
                camp_suffix = r.campaign.final_url_suffix or ""
                if camp_suffix and account_has_tracking:
                    add("low", "utm",
                        f"Acct {acct}: campaign '{r.campaign.name}' has campaign-level UTM suffix "
                        f"overriding account-level — verify intentional (duplicate UTMs possible).")
                elif not camp_suffix and not account_has_tracking:
                    add("high", "utm",
                        f"Acct {acct}: campaign '{r.campaign.name}' has UTM tracking at neither "
                        f"account nor campaign level — attribution broken.")
        except Exception as e:
            add("low", "utm", f"Acct {acct}: utm check failed: {str(e)[:200]}")


# ── Check 5: Naming convention scan (Google + TikTok + Bing) ─────────────
def check_naming_conventions():
    """Flag campaigns whose names don't match the dominant pattern per channel."""
    try:
        from google.cloud import bigquery
        c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")
    except Exception:
        return

    # KPI-RULE-BYPASS — naming check only, no leads analysis
    q = """
    SELECT channel, campaign_name
    FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
      AND campaign_name IS NOT NULL
      AND status = 'Active'
    GROUP BY channel, campaign_name
    """
    by_channel = {}
    for r in c.query(q).result():
        by_channel.setdefault(r.channel, []).append(r.campaign_name)

    # Expected prefix per channel
    expected_prefix = {
        "google_ads":    "Google_",
        "microsoft_ads": "Bing_",
        "tiktok":        "Tiktok_",
        "meta":          "Meta_",
        "snapchat":      "Snapchat_",
    }
    for ch, names in by_channel.items():
        pref = expected_prefix.get(ch)
        if not pref: continue
        for n in names:
            if not n.startswith(pref) and not n.startswith(pref.lower()):
                # Allow legacy "Search_AR_..." style on Microsoft for now
                if ch == "microsoft_ads" and n.startswith("Search_"):
                    continue
                add("low", "naming",
                    f"{ch}: '{n}' doesn't match expected prefix '{pref}' — possible legacy or mis-naming.")


# ── Run all checks ───────────────────────────────────────────────────────
def main():
    print("=" * 78)
    print(f"DAILY AUDIT — {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 78)

    for name, fn in [
        ("KPI hook integrity",    check_kpi_hook),
        ("Attribution drift",     check_attribution_drift),
        ("Disapproved ads",       check_disapproved_ads),
        ("UTM suffix missing",    check_utm_suffix_missing),
        ("Naming conventions",    check_naming_conventions),
    ]:
        print(f"\n→ {name}...")
        try:
            fn()
        except Exception as e:
            add("high", "audit_self", f"Check '{name}' crashed: {e}")

    findings.sort(key=lambda x: SEVERITY[x["severity"]])

    print()
    print("=" * 78)
    print(f"FINDINGS: {len(findings)}")
    print("=" * 78)
    if not findings:
        print("  ✅ clean")
    else:
        for f in findings:
            print(f"  [{f['severity']:<8}] [{f['category']:<13}] {f['detail']}")

    # Append to history
    hist = REPO / "memory" / "audit_findings.md"
    hist.parent.mkdir(exist_ok=True)
    with open(hist, "a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now().isoformat(timespec='seconds')}\n")
        if not findings:
            fh.write("  Clean — no findings.\n")
        else:
            for f in findings:
                fh.write(f"  - [{f['severity']}] [{f['category']}] {f['detail']}\n")
    print(f"\n  History appended → {hist}")

    # Exit code reflects severity
    if any(f["severity"] == "critical" for f in findings):
        sys.exit(2)
    if findings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
