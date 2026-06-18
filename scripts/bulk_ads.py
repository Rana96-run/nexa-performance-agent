"""
scripts/bulk_ads.py — Ad-level pause/enable CLI across Google Ads, Meta, Snapchat, TikTok.

Usage:
  python scripts/bulk_ads.py audit  [--days 30]           # safe: show what would be paused
  python scripts/bulk_ads.py execute [--days 30] [--yes]  # pause flagged ads
  python scripts/bulk_ads.py manual --action pause|enable --channel CHANNEL
                                    (--ad-name NAME | --ad-id ID)

Pause rules (applied from BigQuery data):
  1. Zero-conv rule  : spend > $70 over 7+ days, platform conversions = 0
  2. Junk lead rule  : 10+ days running, HS disqualified/total >= 60% (min 5 leads)
  3. High CPL rule   : CPL (spend / hs_leads) > $50 over 10+ days

Google Ads: pause via AdGroupAdService using ad resource name (GAQL lookup by name).
Meta/Snap/TikTok: pause via set_ad_status / pause_ad using ad_id from ads_daily.
"""
from __future__ import annotations

import argparse
import os
import sys
import io
from pathlib import Path

# Ensure project root is on path (script may be run as `python scripts/bulk_ads.py`)
sys.path.insert(0, str(Path(__file__).parent.parent))

# UTF-8 output for Arabic ad names
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from google.cloud import bigquery
from collectors.bq_writer import get_client as _get_bq_client, PROJECT_ID, DATASET

# ── Constants ─────────────────────────────────────────────────────────────────

PREFIX = "[bulk-ads]"

# Pause rule thresholds — sourced from config.py AD_CPL_PAUSE
from config import AD_CPL_PAUSE as HIGH_CPL_THRESHOLD  # noqa: E402
ZERO_CONV_SPEND    = 70.0   # USD: zero-conv rule minimum spend
ZERO_CONV_DAYS     = 7      # days running before zero-conv rule applies
JUNK_LEAD_DAYS     = 10     # days running before junk-lead rule applies
JUNK_LEAD_RATE     = 0.60   # 60% disqualified
JUNK_LEAD_MIN      = 5      # minimum HubSpot leads to qualify for junk-lead rule
HIGH_CPL_DAYS      = 10     # days running before high-CPL rule applies

# Google Ads accounts (Acc1 = primary, Acc2 = secondary)
GOOGLE_ADS_CUSTOMER_IDS = ["1513020554", "5753494964"]

# Channel values in ads_daily as stored by collectors
CHANNEL_GOOGLE = "google_ads"
CHANNEL_META   = "meta"
CHANNEL_SNAP   = "snapchat"
CHANNEL_TIKTOK = "tiktok"

# Map CLI --channel arg to BQ channel value
CHANNEL_MAP = {
    "google": CHANNEL_GOOGLE,
    "google_ads": CHANNEL_GOOGLE,
    "meta": CHANNEL_META,
    "facebook": CHANNEL_META,
    "snap": CHANNEL_SNAP,
    "snapchat": CHANNEL_SNAP,
    "tiktok": CHANNEL_TIKTOK,
}


# ── BQ queries ────────────────────────────────────────────────────────────────

_AD_PERF_SQL = """
WITH ad_perf AS (
  SELECT
    ad_name,
    channel,
    MAX(ad_id) AS ad_id,
    SUM(spend)          AS total_spend,
    SUM(conversions)    AS total_conv,
    COUNT(DISTINCT date) AS days_active,
    MIN(date)           AS first_date
  FROM `{project}.{dataset}.ads_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
  GROUP BY ad_name, channel
),
hs AS (
  SELECT
    LOWER(lead_utm_content) AS ad_key,
    SUM(leads_total)        AS hs_leads,
    SUM(leads_disqualified) AS hs_disq
  FROM `{project}.{dataset}.hubspot_leads_module_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
    AND lead_utm_content IS NOT NULL
  GROUP BY 1
)
SELECT
  a.ad_name,
  a.channel,
  a.ad_id,
  a.total_spend,
  a.total_conv,
  a.days_active,
  a.first_date,
  COALESCE(hs.hs_leads, 0)  AS hs_leads,
  COALESCE(hs.hs_disq,  0)  AS hs_disq,
  SAFE_DIVIDE(hs.hs_disq, NULLIF(hs.hs_leads, 0))   AS disq_rate,
  SAFE_DIVIDE(a.total_spend, NULLIF(hs.hs_leads, 0)) AS cpl
FROM ad_perf a
LEFT JOIN hs ON LOWER(a.ad_name) = hs.ad_key
WHERE a.total_spend > 20
ORDER BY a.total_spend DESC
"""


def _fetch_ad_perf(days: int) -> list[dict]:
    """Pull ad-level performance + HubSpot data from BigQuery."""
    client  = _get_bq_client()
    sql     = _AD_PERF_SQL.format(project=PROJECT_ID, dataset=DATASET, days=days)
    rows    = list(client.query(sql).result())
    return [dict(row) for row in rows]


# ── Rule evaluation ───────────────────────────────────────────────────────────

def _evaluate_rules(row: dict) -> list[str]:
    """
    Return list of rule names triggered for this ad row.
    Empty list = no pause needed.
    """
    triggered = []

    spend      = float(row.get("total_spend") or 0)
    conv       = float(row.get("total_conv")  or 0)
    days       = int(row.get("days_active")   or 0)
    hs_leads   = int(row.get("hs_leads")      or 0)
    hs_disq    = int(row.get("hs_disq")       or 0)
    disq_rate  = row.get("disq_rate")
    cpl        = row.get("cpl")

    # Rule 1: Zero-conv — spend > $70, 7+ days, zero platform conversions
    if spend > ZERO_CONV_SPEND and days >= ZERO_CONV_DAYS and conv == 0:
        triggered.append("zero_conv")

    # Rule 2: Junk lead — 10+ days, HS disq_rate >= 60%, min 5 leads
    if (days >= JUNK_LEAD_DAYS
            and hs_leads >= JUNK_LEAD_MIN
            and disq_rate is not None
            and float(disq_rate) >= JUNK_LEAD_RATE):
        triggered.append("junk_lead")

    # Rule 3: High CPL — CPL > $50, 10+ days
    if (days >= HIGH_CPL_DAYS
            and cpl is not None
            and float(cpl) > HIGH_CPL_THRESHOLD):
        triggered.append("high_cpl")

    return triggered


# ── Google Ads: lookup ad resource name by ad name ───────────────────────────

def _gaql_find_ad(ad_name: str, customer_id: str) -> str | None:
    """
    Search ad_group_ad for an ad whose name matches ad_name.
    Returns the resource_name or None if not found.
    """
    try:
        from collectors.google_ads import get_client
        client = get_client()
        ga_svc = client.get_service("GoogleAdsService")
        # Escape single quotes in ad name
        safe_name = ad_name.replace("'", "\\'")
        query = f"""
            SELECT ad_group_ad.resource_name,
                   ad_group_ad.ad.name,
                   ad_group_ad.status
            FROM ad_group_ad
            WHERE ad_group_ad.ad.name = '{safe_name}'
              AND ad_group_ad.status != 'REMOVED'
            LIMIT 1
        """
        rows = list(ga_svc.search(customer_id=customer_id, query=query))
        if rows:
            return rows[0].ad_group_ad.resource_name
    except Exception as e:
        print(f"{PREFIX} [warn] GAQL lookup error for '{ad_name}' (cid={customer_id}): {e}")
    return None


def _google_pause_by_name(ad_name: str) -> bool:
    """
    Look up ad resource name across both Google Ads accounts, then pause.
    Returns True on success, False if not found or error.
    """
    from executors.google_ads import set_ad_status
    for cid in GOOGLE_ADS_CUSTOMER_IDS:
        rn = _gaql_find_ad(ad_name, cid)
        if rn:
            try:
                set_ad_status(rn, "PAUSED", customer_id=cid)
                print(f"{PREFIX} PAUSED Google ad '{ad_name}' (resource={rn}, cid={cid})")
                return True
            except Exception as e:
                print(f"{PREFIX} [error] Failed to pause Google ad '{ad_name}': {e}")
                return False
    print(f"{PREFIX} [warn] Google ad '{ad_name}' not found in any account — skipped")
    return False


def _google_enable_by_name(ad_name: str) -> bool:
    """Enable a Google Ads ad by name. Searches both accounts."""
    from executors.google_ads import set_ad_status
    for cid in GOOGLE_ADS_CUSTOMER_IDS:
        rn = _gaql_find_ad(ad_name, cid)
        if rn:
            try:
                set_ad_status(rn, "ENABLED", customer_id=cid)
                print(f"{PREFIX} ENABLED Google ad '{ad_name}' (resource={rn}, cid={cid})")
                return True
            except Exception as e:
                print(f"{PREFIX} [error] Failed to enable Google ad '{ad_name}': {e}")
                return False
    print(f"{PREFIX} [warn] Google ad '{ad_name}' not found in any account — skipped")
    return False


def _google_enable_by_resource(resource_name: str, customer_id: str) -> bool:
    from executors.google_ads import set_ad_status
    try:
        set_ad_status(resource_name, "ENABLED", customer_id=customer_id)
        print(f"{PREFIX} ENABLED Google ad (resource={resource_name}, cid={customer_id})")
        return True
    except Exception as e:
        print(f"{PREFIX} [error] Failed to enable Google ad: {e}")
        return False


# ── Per-channel pause/enable dispatch ────────────────────────────────────────

def _pause_ad(channel: str, ad_name: str, ad_id: str | None) -> bool:
    """Pause an ad on the given channel. Returns True on success."""
    if channel == CHANNEL_GOOGLE:
        return _google_pause_by_name(ad_name)

    if channel == CHANNEL_META:
        if not ad_id:
            print(f"{PREFIX} [warn] No ad_id for Meta ad '{ad_name}' — printing action instead")
            print(f"{PREFIX} ACTION NEEDED: pause Meta ad '{ad_name}' (ad_id unknown) in Ads Manager")
            return False
        try:
            from executors.meta import set_ad_status
            set_ad_status(ad_id, "PAUSED")
            print(f"{PREFIX} PAUSED Meta ad '{ad_name}' (id={ad_id})")
            return True
        except Exception as e:
            print(f"{PREFIX} [error] Meta pause failed for '{ad_name}' (id={ad_id}): {e}")
            return False

    if channel == CHANNEL_SNAP:
        if not ad_id:
            print(f"{PREFIX} [warn] No ad_id for Snapchat ad '{ad_name}' — printing action instead")
            print(f"{PREFIX} ACTION NEEDED: pause Snapchat ad '{ad_name}' (ad_id unknown) in Ads Manager")
            return False
        try:
            from executors.snapchat import set_ad_status
            set_ad_status(ad_id, "PAUSED")
            print(f"{PREFIX} PAUSED Snapchat ad '{ad_name}' (id={ad_id})")
            return True
        except Exception as e:
            print(f"{PREFIX} [error] Snapchat pause failed for '{ad_name}' (id={ad_id}): {e}")
            return False

    if channel == CHANNEL_TIKTOK:
        if not ad_id:
            print(f"{PREFIX} [warn] No ad_id for TikTok ad '{ad_name}' — printing action instead")
            print(f"{PREFIX} ACTION NEEDED: pause TikTok ad '{ad_name}' (ad_id unknown) in Ads Manager")
            return False
        try:
            from executors.tiktok import pause_ad
            pause_ad(ad_id)
            print(f"{PREFIX} PAUSED TikTok ad '{ad_name}' (id={ad_id})")
            return True
        except Exception as e:
            print(f"{PREFIX} [error] TikTok pause failed for '{ad_name}' (id={ad_id}): {e}")
            return False

    print(f"{PREFIX} [warn] Unknown channel '{channel}' — skipped")
    return False


def _enable_ad(channel: str, ad_name: str | None, ad_id: str | None) -> bool:
    """Enable an ad on the given channel. Returns True on success."""
    if channel == CHANNEL_GOOGLE:
        if not ad_name:
            print(f"{PREFIX} [error] --ad-name required for Google Ads enable")
            return False
        return _google_enable_by_name(ad_name)

    if channel == CHANNEL_META:
        if not ad_id:
            print(f"{PREFIX} [error] --ad-id required for Meta enable")
            return False
        try:
            from executors.meta import set_ad_status
            set_ad_status(ad_id, "ACTIVE")
            print(f"{PREFIX} ENABLED Meta ad (id={ad_id})")
            return True
        except Exception as e:
            print(f"{PREFIX} [error] Meta enable failed (id={ad_id}): {e}")
            return False

    if channel == CHANNEL_SNAP:
        if not ad_id:
            print(f"{PREFIX} [error] --ad-id required for Snapchat enable")
            return False
        try:
            from executors.snapchat import set_ad_status
            set_ad_status(ad_id, "ACTIVE")
            print(f"{PREFIX} ENABLED Snapchat ad (id={ad_id})")
            return True
        except Exception as e:
            print(f"{PREFIX} [error] Snapchat enable failed (id={ad_id}): {e}")
            return False

    if channel == CHANNEL_TIKTOK:
        if not ad_id:
            print(f"{PREFIX} [error] --ad-id required for TikTok enable")
            return False
        try:
            from executors.tiktok import _post as _tt_post, _DEFAULT_ACCOUNT
            _tt_post("/ad/status/update/", {
                "advertiser_id":    _DEFAULT_ACCOUNT,
                "ad_ids":           [ad_id],
                "operation_status": "ENABLE",
            })
            print(f"{PREFIX} ENABLED TikTok ad (id={ad_id})")
            return True
        except Exception as e:
            print(f"{PREFIX} [error] TikTok enable failed (id={ad_id}): {e}")
            return False

    print(f"{PREFIX} [warn] Unknown channel '{channel}' — skipped")
    return False


# ── Audit output ──────────────────────────────────────────────────────────────

_COL_W = {
    "channel":  10,
    "ad_name":  45,
    "spend":     8,
    "days":      5,
    "conv":      5,
    "hs_leads":  8,
    "disq_rate": 9,
    "cpl":       8,
    "rule":     22,
}


def _fmt_row(row: dict, rules: list[str]) -> str:
    ch       = (row.get("channel") or "")[:_COL_W["channel"]].ljust(_COL_W["channel"])
    name     = (row.get("ad_name") or "")[:_COL_W["ad_name"]].ljust(_COL_W["ad_name"])
    spend    = f"${float(row.get('total_spend') or 0):>6.1f}"
    days     = str(int(row.get("days_active") or 0)).rjust(_COL_W["days"])
    conv     = f"{float(row.get('total_conv') or 0):>4.0f}"
    hs       = str(int(row.get("hs_leads") or 0)).rjust(_COL_W["hs_leads"])
    dr       = row.get("disq_rate")
    disq     = (f"{float(dr)*100:>5.0f}%") if dr is not None else "    -"
    cpl_v    = row.get("cpl")
    cpl      = (f"${float(cpl_v):>5.1f}") if cpl_v is not None else "   -"
    rule_str = (",".join(rules))[:_COL_W["rule"]].ljust(_COL_W["rule"])
    return f"  {ch}  {name}  {spend}  {days}d  {conv}cv  {hs}hs  {disq}disq  {cpl}cpl  {rule_str}"


def _print_header():
    ch    = "CHANNEL".ljust(_COL_W["channel"])
    name  = "AD_NAME".ljust(_COL_W["ad_name"])
    spend = "SPEND".rjust(7)
    days  = "DAYS".rjust(_COL_W["days"])
    conv  = "CONV".rjust(4)
    hs    = "HS_LEADS".rjust(_COL_W["hs_leads"])
    disq  = "DISQ%".rjust(6)
    cpl   = "CPL".rjust(6)
    rule  = "RULE(S)".ljust(_COL_W["rule"])
    print(f"\n  {ch}  {name}  {spend}  {days}   {conv}   {hs}   {disq}   {cpl}   {rule}")
    print("  " + "-" * 135)


# ── Mode: audit ───────────────────────────────────────────────────────────────

def cmd_audit(days: int) -> list[dict]:
    """
    Query BQ, evaluate all 3 rules, print flagged ads.
    Returns list of flagged rows (with 'rules' key added).
    """
    print(f"{PREFIX} Fetching ad performance from BigQuery (last {days} days)...")
    try:
        rows = _fetch_ad_perf(days)
    except Exception as e:
        print(f"{PREFIX} [error] BQ query failed: {e}")
        sys.exit(1)

    print(f"{PREFIX} Evaluating {len(rows)} ads against pause rules...")

    flagged = []
    for row in rows:
        rules = _evaluate_rules(row)
        if rules:
            row["rules"] = rules
            flagged.append(row)

    if not flagged:
        print(f"{PREFIX} No ads flagged for pause.")
        print(f"\n{PREFIX} Audit complete: 0 ads flagged (0 paused, 0 skipped)")
        return flagged

    print(f"{PREFIX} {len(flagged)} ad(s) flagged:")
    _print_header()
    for row in flagged:
        print(_fmt_row(row, row["rules"]))

    return flagged


# ── Mode: execute ─────────────────────────────────────────────────────────────

def cmd_execute(days: int, yes: bool) -> None:
    flagged = cmd_audit(days)
    if not flagged:
        return

    print()
    if not yes:
        answer = input(f"{PREFIX} Pause {len(flagged)} ad(s)? Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print(f"{PREFIX} Aborted.")
            print(f"\n{PREFIX} Audit complete: {len(flagged)} ads flagged (0 paused, {len(flagged)} skipped)")
            return

    paused  = 0
    skipped = 0
    paused_names: list[str] = []
    for row in flagged:
        ad_name = row.get("ad_name") or ""
        ad_id   = row.get("ad_id")
        channel = row.get("channel") or ""
        rules   = row.get("rules", [])

        print(f"{PREFIX} Pausing '{ad_name}' ({channel}) — rules: {', '.join(rules)}")
        ok = _pause_ad(channel, ad_name, ad_id)
        if ok:
            paused += 1
            paused_names.append(f"{channel}:{ad_name}")
        else:
            skipped += 1

    print(f"\n{PREFIX} Audit complete: {len(flagged)} ads flagged ({paused} paused, {skipped} skipped)")

    if paused:
        try:
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="manual_script", action="ads_paused",
                channel="multi", rows_affected=paused,
                details={"ads": paused_names[:30], "skipped": skipped,
                         "source": "bulk_ads.py execute"},
            )
        except Exception:
            pass


# ── Mode: manual ──────────────────────────────────────────────────────────────

def cmd_manual(action: str, channel_arg: str, ad_name: str | None, ad_id: str | None) -> None:
    channel = CHANNEL_MAP.get(channel_arg.lower())
    if not channel:
        print(f"{PREFIX} [error] Unknown channel '{channel_arg}'. "
              f"Valid: {', '.join(sorted(CHANNEL_MAP.keys()))}")
        sys.exit(1)

    if not ad_name and not ad_id:
        print(f"{PREFIX} [error] Provide --ad-name or --ad-id")
        sys.exit(1)

    if action == "pause":
        # For non-Google, prefer ad_id; for Google, prefer ad_name
        ok = _pause_ad(channel, ad_name or "", ad_id)
    elif action == "enable":
        ok = _enable_ad(channel, ad_name, ad_id)
    else:
        print(f"{PREFIX} [error] --action must be 'pause' or 'enable'")
        sys.exit(1)

    result = "done" if ok else "failed/skipped"
    print(f"\n{PREFIX} Audit complete: 1 ads flagged (manual {action}: {result})")

    if ok:
        try:
            from logs.activity_logger import log_activity_async
            log_activity_async(
                role="manual_script",
                action="ads_paused" if action == "pause" else "ads_enabled",
                channel=CHANNEL_MAP.get(channel_arg.lower(), channel_arg),
                rows_affected=1,
                details={"ad_name": ad_name, "ad_id": ad_id,
                         "source": "bulk_ads.py manual"},
            )
        except Exception:
            pass


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bulk_ads.py",
        description="Ad-level pause/enable across Google Ads, Meta, Snapchat, TikTok.",
    )
    sub = p.add_subparsers(dest="mode", required=True)

    # audit
    audit_p = sub.add_parser("audit", help="Show what would be paused (default, safe)")
    audit_p.add_argument("--days", type=int, default=30,
                         help="Lookback window in days (default 30)")
    audit_p.add_argument("--dry-run", action="store_true",
                         help="Alias for audit mode (no-op flag, audit never executes)")

    # execute
    exec_p = sub.add_parser("execute", help="Pause the flagged ads")
    exec_p.add_argument("--days", type=int, default=30,
                        help="Lookback window in days (default 30)")
    exec_p.add_argument("--yes", action="store_true",
                        help="Skip confirmation prompt")
    exec_p.add_argument("--dry-run", action="store_true",
                        help="Run audit only (overrides execute mode)")

    # manual
    man_p = sub.add_parser("manual", help="Pause or enable a specific ad by name or ID")
    man_p.add_argument("--action", required=True, choices=["pause", "enable"],
                       help="Action to perform")
    man_p.add_argument("--channel", required=True,
                       help="Channel: google, meta, snap, tiktok")
    man_p.add_argument("--ad-name", default=None,
                       help="Ad name (required for Google Ads; optional for others)")
    man_p.add_argument("--ad-id", default=None,
                       help="Ad ID (required for Meta/Snap/TikTok; optional for Google)")

    return p


def main():
    parser = _build_parser()
    args   = parser.parse_args()

    if args.mode == "audit" or getattr(args, "dry_run", False):
        cmd_audit(getattr(args, "days", 30))

    elif args.mode == "execute":
        if args.dry_run:
            # --dry-run on execute falls back to audit
            cmd_audit(args.days)
        else:
            cmd_execute(args.days, args.yes)

    elif args.mode == "manual":
        cmd_manual(
            action=args.action,
            channel_arg=args.channel,
            ad_name=args.ad_name,
            ad_id=args.ad_id,
        )


if __name__ == "__main__":
    main()
