"""
bulk_keywords.py — Bulk add keywords / negative keywords to Google Ads.

Usage
-----
# Add positive keywords to an ad group
python scripts/bulk_keywords.py add-keywords \\
    --adgroup "customers/5753494964/adGroups/123456" \\
    --cid 5753494964 \\
    --keywords "برنامج محاسبة,EXACT" "نظام محاسبي,PHRASE" "accounting software,BROAD"

# Add positive keywords from a CSV file
python scripts/bulk_keywords.py add-keywords \\
    --adgroup "customers/5753494964/adGroups/123456" \\
    --file keywords.csv

# Add negative keywords at campaign level
python scripts/bulk_keywords.py add-negatives \\
    --campaign "customers/5753494964/campaigns/789" \\
    --cid 5753494964 \\
    --keywords "مجاني,BROAD" "وظائف,BROAD"

# Add negative keywords from a CSV file
python scripts/bulk_keywords.py add-negatives \\
    --campaign "customers/5753494964/campaigns/789" \\
    --file negatives.csv

# Interactive mode
python scripts/bulk_keywords.py interactive

# From search terms analysis
python scripts/bulk_keywords.py from-search-terms --days 30 --dry-run
python scripts/bulk_keywords.py from-search-terms --days 30

CSV format (first line is header):
    keyword,match_type,cpc_bid_usd
    برنامج محاسبة,EXACT,1.50
    نظام محاسبي,PHRASE
    accounting software,BROAD
"""
from __future__ import annotations

import csv
import io
import os
import sys

# Ensure repo root is on sys.path when run as scripts/bulk_keywords.py
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
load_dotenv()

from config import GOOGLE_ADS_CONFIG
from collectors.google_ads import get_client
from executors.google_ads import add_keywords, add_negative_keywords, list_search_terms, classify_search_terms

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_CID = GOOGLE_ADS_CONFIG["customer_id"]
_ALL_CIDS = ["1513020554", "5753494964"]
_VALID_MATCH = {"EXACT", "PHRASE", "BROAD"}
_PREFIX = "[bulk-kw]"

# ---------------------------------------------------------------------------
# Logging — use print since utils/logging_utils.py does not exist
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"{_PREFIX} {msg}", flush=True)


# ---------------------------------------------------------------------------
# Argument parsing helpers (no argparse — simple dispatch)
# ---------------------------------------------------------------------------

def _get_flag(argv: list[str], flag: str, default: str | None = None) -> str | None:
    """Return the value after --flag, or default."""
    try:
        idx = argv.index(flag)
        return argv[idx + 1]
    except (ValueError, IndexError):
        return default


def _has_flag(argv: list[str], flag: str) -> bool:
    return flag in argv


def _get_multi_flag(argv: list[str], flag: str) -> list[str]:
    """
    Collect all positional values that come after --flag and before the next
    flag (token starting with --).  Also handles multiple --flag occurrences.
    """
    results = []
    i = 0
    while i < len(argv):
        if argv[i] == flag:
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                results.append(argv[i])
                i += 1
        else:
            i += 1
    return results


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

def _read_csv(path: str) -> list[dict]:
    """
    Read a keyword CSV.  Expected header: keyword,match_type,cpc_bid_usd
    cpc_bid_usd is optional.
    Returns list of {"text": str, "match_type": str, "cpc_bid_usd": float|None}
    """
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=2):
            text = row.get("keyword", "").strip()
            match = row.get("match_type", "BROAD").strip().upper()
            if not text:
                _log(f"  Row {i}: empty keyword — skipped")
                continue
            if match not in _VALID_MATCH:
                _log(f"  Row {i}: unknown match_type {match!r} — defaulting to BROAD")
                match = "BROAD"
            bid_raw = (row.get("cpc_bid_usd") or "").strip()
            bid = None
            if bid_raw:
                try:
                    bid = float(bid_raw)
                except ValueError:
                    _log(f"  Row {i}: invalid cpc_bid_usd {bid_raw!r} — ignored")
            kw: dict = {"text": text, "match_type": match}
            if bid is not None:
                kw["cpc_bid_usd"] = bid
            rows.append(kw)
    return rows


# ---------------------------------------------------------------------------
# Inline keyword parsing from CLI strings ("text,MATCH_TYPE" or "text,MATCH,bid")
# ---------------------------------------------------------------------------

def _parse_kw_arg(token: str) -> dict:
    """
    Parse a single keyword token from the CLI.
    Formats accepted:
        "برنامج محاسبة,EXACT"
        "برنامج محاسبة,EXACT,1.50"
        "accounting software"          (defaults to BROAD)
    """
    parts = [p.strip() for p in token.split(",")]
    text = parts[0]
    match = parts[1].upper() if len(parts) > 1 else "BROAD"
    if match not in _VALID_MATCH:
        _log(f"  Warning: unknown match_type {match!r} for {text!r} — defaulting to BROAD")
        match = "BROAD"
    kw: dict = {"text": text, "match_type": match}
    if len(parts) > 2:
        try:
            kw["cpc_bid_usd"] = float(parts[2])
        except ValueError:
            _log(f"  Warning: invalid bid {parts[2]!r} — ignored")
    return kw


# ---------------------------------------------------------------------------
# Preview table
# ---------------------------------------------------------------------------

def _print_preview(keywords: list[dict], target: str, action: str) -> None:
    """Print a fixed-width preview table."""
    col_kw  = max(len("KEYWORD"),     max((len(k["text"]) for k in keywords), default=0))
    col_mt  = max(len("MATCH_TYPE"),  max((len(k["match_type"]) for k in keywords), default=0))
    col_bid = max(len("BID_USD"),     max((len(f"{k.get('cpc_bid_usd', '-')}") for k in keywords), default=0))
    col_tgt = max(len("TARGET"),      len(target))
    col_act = max(len("ACTION"),      len(action))

    sep = f"  {'─' * col_kw}  {'─' * col_mt}  {'─' * col_bid}  {'─' * col_tgt}  {'─' * col_act}"
    hdr = (
        f"  {'KEYWORD':<{col_kw}}  {'MATCH_TYPE':<{col_mt}}  "
        f"{'BID_USD':<{col_bid}}  {'TARGET':<{col_tgt}}  {'ACTION':<{col_act}}"
    )
    print()
    print(sep)
    print(hdr)
    print(sep)
    for kw in keywords:
        bid_str = str(kw["cpc_bid_usd"]) if kw.get("cpc_bid_usd") else "-"
        print(
            f"  {kw['text']:<{col_kw}}  {kw['match_type']:<{col_mt}}  "
            f"{bid_str:<{col_bid}}  {target:<{col_tgt}}  {action:<{col_act}}"
        )
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------

def _confirm(dry_run: bool, yes: bool) -> bool:
    if dry_run:
        _log("Dry-run mode — no changes will be made.")
        return False
    if yes:
        return True
    answer = input("Proceed? Type 'yes' to confirm: ").strip().lower()
    return answer == "yes"


# ---------------------------------------------------------------------------
# Duplicate-safe wrapper around add_keywords / add_negative_keywords
# ---------------------------------------------------------------------------

def _safe_add_keywords(adgroup_rn: str, keywords: list[dict], cid: str) -> int:
    """Add keywords, skipping duplicates. Returns count added."""
    from google.ads.googleads.errors import GoogleAdsException

    added = 0
    # Attempt bulk first; fall back to one-by-one on duplicate error
    try:
        results = add_keywords(adgroup_rn, keywords, customer_id=cid)
        added = len(results)
    except GoogleAdsException as exc:
        skip_count = 0
        for err in exc.failure.errors:
            if "CRITERION_DUPLICATE" in str(err.error_code):
                skip_count += 1
        if skip_count == len(keywords):
            _log(f"  All {len(keywords)} keyword(s) already exist — skipped.")
            return 0
        # Partial duplicates: retry one-by-one
        _log(f"  Duplicate(s) detected — retrying one-by-one ({len(keywords)} keywords)...")
        for kw in keywords:
            try:
                add_keywords(adgroup_rn, [kw], customer_id=cid)
                added += 1
            except GoogleAdsException as inner:
                msgs = [str(e.error_code) for e in inner.failure.errors]
                if any("CRITERION_DUPLICATE" in m for m in msgs):
                    _log(f"  Duplicate skipped: {kw['text']} [{kw['match_type']}]")
                else:
                    _log(f"  Error adding {kw['text']!r}: {inner}")
    return added


def _safe_add_negatives(campaign_rn: str, keywords: list[dict], cid: str) -> int:
    """Add negative keywords, skipping duplicates. Returns count added."""
    from google.ads.googleads.errors import GoogleAdsException

    added = 0
    try:
        results = add_negative_keywords(campaign_rn, keywords, customer_id=cid)
        added = len(results)
    except GoogleAdsException as exc:
        skip_count = 0
        for err in exc.failure.errors:
            if "CRITERION_DUPLICATE" in str(err.error_code):
                skip_count += 1
        if skip_count == len(keywords):
            _log(f"  All {len(keywords)} negative keyword(s) already exist — skipped.")
            return 0
        _log(f"  Duplicate(s) detected — retrying one-by-one ({len(keywords)} negatives)...")
        for kw in keywords:
            try:
                add_negative_keywords(campaign_rn, [kw], customer_id=cid)
                added += 1
            except GoogleAdsException as inner:
                msgs = [str(e.error_code) for e in inner.failure.errors]
                if any("CRITERION_DUPLICATE" in m for m in msgs):
                    _log(f"  Duplicate skipped: {kw['text']} [{kw['match_type']}]")
                else:
                    _log(f"  Error adding {kw['text']!r}: {inner}")
    return added


# ---------------------------------------------------------------------------
# Google Ads helpers (listing campaigns / ad groups — not in executor)
# ---------------------------------------------------------------------------

def _list_campaigns_for_account(cid: str) -> list[dict]:
    """Return list of {id, name, status, resource_name} for one customer."""
    client = get_client()
    ga_svc = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name, campaign.status, campaign.resource_name
        FROM campaign
        WHERE campaign.status != 'REMOVED'
        ORDER BY campaign.name
    """
    rows = []
    try:
        for row in ga_svc.search(customer_id=cid, query=query):
            rows.append({
                "id":            str(row.campaign.id),
                "name":          row.campaign.name,
                "status":        row.campaign.status.name,
                "resource_name": row.campaign.resource_name,
                "cid":           cid,
            })
    except Exception as e:
        _log(f"  Could not list campaigns for account {cid}: {e}")
    return rows


def _list_adgroups_for_campaign(campaign_id: str, cid: str) -> list[dict]:
    """Return list of {id, name, status, resource_name} for one campaign."""
    client = get_client()
    ga_svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.resource_name
        FROM ad_group
        WHERE campaign.id = {campaign_id}
          AND ad_group.status != 'REMOVED'
        ORDER BY ad_group.name
    """
    rows = []
    try:
        for row in ga_svc.search(customer_id=cid, query=query):
            rows.append({
                "id":            str(row.ad_group.id),
                "name":          row.ad_group.name,
                "status":        row.ad_group.status.name,
                "resource_name": row.ad_group.resource_name,
            })
    except Exception as e:
        _log(f"  Could not list ad groups for campaign {campaign_id}: {e}")
    return rows


# ---------------------------------------------------------------------------
# Mode 1: add-keywords
# ---------------------------------------------------------------------------

def cmd_add_keywords(argv: list[str]) -> None:
    adgroup_rn = _get_flag(argv, "--adgroup")
    cid        = _get_flag(argv, "--cid", _DEFAULT_CID)
    file_path  = _get_flag(argv, "--file")
    dry_run    = _has_flag(argv, "--dry-run")
    yes        = _has_flag(argv, "--yes")

    if not adgroup_rn:
        print("Error: --adgroup <resource_name> is required.")
        print("  Example: --adgroup customers/5753494964/adGroups/123456")
        sys.exit(1)

    # Collect keywords
    if file_path:
        _log(f"Reading keywords from {file_path} ...")
        keywords = _read_csv(file_path)
    else:
        raw_tokens = _get_multi_flag(argv, "--keywords")
        if not raw_tokens:
            print("Error: supply keywords via --keywords or --file.")
            sys.exit(1)
        keywords = [_parse_kw_arg(t) for t in raw_tokens]

    if not keywords:
        _log("No keywords found — nothing to do.")
        return

    _log(f"Preview: {len(keywords)} keyword(s) -> {adgroup_rn} (account {cid})")
    _print_preview(keywords, adgroup_rn, "ADD_KEYWORD")

    if not _confirm(dry_run, yes):
        _log("Aborted.")
        return

    _log("Executing ...")
    added = _safe_add_keywords(adgroup_rn, keywords, cid)
    _log(f"Done. Added {added} keywords, {len(keywords) - added} skipped (duplicates).")
    print(f"\nAdded {added} keywords, 0 negatives")


# ---------------------------------------------------------------------------
# Mode 2: add-negatives
# ---------------------------------------------------------------------------

def cmd_add_negatives(argv: list[str]) -> None:
    campaign_rn = _get_flag(argv, "--campaign")
    cid         = _get_flag(argv, "--cid", _DEFAULT_CID)
    file_path   = _get_flag(argv, "--file")
    dry_run     = _has_flag(argv, "--dry-run")
    yes         = _has_flag(argv, "--yes")

    if not campaign_rn:
        print("Error: --campaign <resource_name> is required.")
        print("  Example: --campaign customers/5753494964/campaigns/789")
        sys.exit(1)

    if file_path:
        _log(f"Reading negatives from {file_path} ...")
        keywords = _read_csv(file_path)
    else:
        raw_tokens = _get_multi_flag(argv, "--keywords")
        if not raw_tokens:
            print("Error: supply keywords via --keywords or --file.")
            sys.exit(1)
        keywords = [_parse_kw_arg(t) for t in raw_tokens]

    if not keywords:
        _log("No keywords found — nothing to do.")
        return

    _log(f"Preview: {len(keywords)} negative keyword(s) -> {campaign_rn} (account {cid})")
    _print_preview(keywords, campaign_rn, "ADD_NEGATIVE")

    if not _confirm(dry_run, yes):
        _log("Aborted.")
        return

    _log("Executing ...")
    added = _safe_add_negatives(campaign_rn, keywords, cid)
    _log(f"Done. Added {added} negatives, {len(keywords) - added} skipped (duplicates).")
    print(f"\nAdded 0 keywords, {added} negatives")


# ---------------------------------------------------------------------------
# Mode 3: interactive
# ---------------------------------------------------------------------------

def cmd_interactive(argv: list[str]) -> None:
    dry_run = _has_flag(argv, "--dry-run")
    yes     = _has_flag(argv, "--yes")

    # 1. List campaigns across both accounts
    print()
    _log("Fetching campaigns from both accounts ...")
    all_campaigns: list[dict] = []
    for cid in _ALL_CIDS:
        _log(f"  Account {cid} ...")
        camps = _list_campaigns_for_account(cid)
        all_campaigns.extend(camps)

    if not all_campaigns:
        _log("No campaigns found.")
        return

    print()
    print(f"  {'#':<4}  {'ACCOUNT':<14}  {'STATUS':<8}  CAMPAIGN")
    print(f"  {'─'*4}  {'─'*14}  {'─'*8}  {'─'*60}")
    for i, c in enumerate(all_campaigns, start=1):
        print(f"  {i:<4}  {c['cid']:<14}  {c['status']:<8}  {c['name']}")
    print()

    # 2. Pick campaign
    raw = input("Enter campaign number: ").strip()
    try:
        camp = all_campaigns[int(raw) - 1]
    except (ValueError, IndexError):
        _log(f"Invalid selection: {raw!r}")
        sys.exit(1)

    cid         = camp["cid"]
    camp_rn     = camp["resource_name"]
    camp_name   = camp["name"]
    campaign_id = camp["id"]

    # 3. Ask: add positive (to ad group) or negative (to campaign)
    print()
    print("  1. Add positive keywords to an ad group")
    print("  2. Add negative keywords to this campaign")
    kw_type_raw = input("Choose (1/2): ").strip()

    if kw_type_raw == "2":
        # Negative path — no ad group needed
        _collect_and_add_negatives_interactive(camp_rn, cid, dry_run, yes)
        return

    # 4. List ad groups in selected campaign
    _log(f"Fetching ad groups for: {camp_name} ...")
    adgroups = _list_adgroups_for_campaign(campaign_id, cid)

    if not adgroups:
        _log("No ad groups found in this campaign.")
        return

    print()
    print(f"  {'#':<4}  {'STATUS':<8}  AD GROUP")
    print(f"  {'─'*4}  {'─'*8}  {'─'*60}")
    for i, ag in enumerate(adgroups, start=1):
        print(f"  {i:<4}  {ag['status']:<8}  {ag['name']}")
    print()

    raw = input("Enter ad group number: ").strip()
    try:
        adgroup = adgroups[int(raw) - 1]
    except (ValueError, IndexError):
        _log(f"Invalid selection: {raw!r}")
        sys.exit(1)

    adgroup_rn = adgroup["resource_name"]
    _log(f"Selected ad group: {adgroup['name']}")

    # 5. Collect keywords interactively
    print()
    print("Enter keywords one per line. Format: keyword text | MATCH_TYPE | optional_bid")
    print("  Examples:")
    print("    برنامج محاسبة | EXACT | 1.50")
    print("    نظام محاسبي | PHRASE")
    print("    accounting software | BROAD")
    print("Press Enter on an empty line when done.")
    print()

    keywords: list[dict] = []
    while True:
        line = input("  Keyword: ").strip()
        if not line:
            break
        parts = [p.strip() for p in line.split("|")]
        text  = parts[0]
        if not text:
            continue
        match = parts[1].upper() if len(parts) > 1 else "BROAD"
        if match not in _VALID_MATCH:
            _log(f"  Unknown match_type {match!r} — defaulting to BROAD")
            match = "BROAD"
        kw: dict = {"text": text, "match_type": match}
        if len(parts) > 2:
            try:
                kw["cpc_bid_usd"] = float(parts[2])
            except ValueError:
                _log(f"  Invalid bid {parts[2]!r} — ignored")
        keywords.append(kw)
        _log(f"  Added to list: {text} [{match}]")

    if not keywords:
        _log("No keywords entered — nothing to do.")
        return

    _log(f"Preview: {len(keywords)} keyword(s) -> {adgroup['name']} (account {cid})")
    _print_preview(keywords, adgroup_rn, "ADD_KEYWORD")

    if not _confirm(dry_run, yes):
        _log("Aborted.")
        return

    _log("Executing ...")
    added = _safe_add_keywords(adgroup_rn, keywords, cid)
    _log(f"Done. Added {added} keywords, {len(keywords) - added} skipped (duplicates).")
    print(f"\nAdded {added} keywords, 0 negatives")


def _collect_and_add_negatives_interactive(
    campaign_rn: str, cid: str, dry_run: bool, yes: bool
) -> None:
    print()
    print("Enter negative keywords one per line. Format: keyword text | MATCH_TYPE")
    print("Press Enter on an empty line when done.")
    print()

    keywords: list[dict] = []
    while True:
        line = input("  Negative keyword: ").strip()
        if not line:
            break
        parts = [p.strip() for p in line.split("|")]
        text  = parts[0]
        if not text:
            continue
        match = parts[1].upper() if len(parts) > 1 else "BROAD"
        if match not in _VALID_MATCH:
            _log(f"  Unknown match_type {match!r} — defaulting to BROAD")
            match = "BROAD"
        keywords.append({"text": text, "match_type": match})
        _log(f"  Added to list: {text} [{match}]")

    if not keywords:
        _log("No keywords entered — nothing to do.")
        return

    _log(f"Preview: {len(keywords)} negative keyword(s) -> {campaign_rn}")
    _print_preview(keywords, campaign_rn, "ADD_NEGATIVE")

    if not _confirm(dry_run, yes):
        _log("Aborted.")
        return

    _log("Executing ...")
    added = _safe_add_negatives(campaign_rn, keywords, cid)
    _log(f"Done. Added {added} negatives, {len(keywords) - added} skipped (duplicates).")
    print(f"\nAdded 0 keywords, {added} negatives")


# ---------------------------------------------------------------------------
# Mode 4: from-search-terms
# ---------------------------------------------------------------------------

def cmd_from_search_terms(argv: list[str]) -> None:
    days    = int(_get_flag(argv, "--days", "30"))
    cid     = _get_flag(argv, "--cid", _DEFAULT_CID)
    dry_run = _has_flag(argv, "--dry-run")
    yes     = _has_flag(argv, "--yes")

    _log(f"Fetching search terms for last {days} days (account {cid}) ...")
    terms = list_search_terms(days=days, customer_id=cid)

    if not terms:
        _log("No search terms found.")
        return

    _log(f"Classifying {len(terms)} terms ...")
    buckets = classify_search_terms(terms)

    convert_terms  = buckets["convert"]
    negative_terms = buckets["negative"]
    watch_terms    = buckets["watch"]

    print()
    print(f"  Convert  (add as keywords)   : {len(convert_terms)}")
    print(f"  Negative (add as negatives)  : {len(negative_terms)}")
    print(f"  Watch    (flag, no action)   : {len(watch_terms)}")
    print(f"  Ignore                       : {len(buckets['ignore'])}")

    # Build keyword lists for preview
    kw_to_add: list[dict]    = []
    neg_to_add: list[dict]   = []
    kw_targets: list[str]    = []   # adgroup resource name per convert term
    neg_targets: list[str]   = []   # campaign resource name per negative term

    # For convert terms: add to the same ad group they appeared in
    for t in convert_terms:
        kw_to_add.append({"text": t["query"], "match_type": "EXACT"})
        kw_targets.append(t["ad_group_resource_name"])

    # For negative terms: add at campaign level — derive campaign RN from ad group RN
    # ad_group resource_name = customers/{cid}/adGroups/{ag_id}
    # campaign resource_name = customers/{cid}/campaigns/{campaign_id}
    # We have campaign_id from the term dict.
    for t in negative_terms:
        neg_to_add.append({"text": t["query"], "match_type": "BROAD"})
        # Build campaign resource name from cid + campaign_id
        campaign_rn = f"customers/{cid}/campaigns/{t['campaign_id']}"
        neg_targets.append(campaign_rn)

    if not kw_to_add and not neg_to_add:
        _log("Nothing actionable in this window.")
        return

    # Print preview tables
    if kw_to_add:
        print()
        print("--- CONVERTING SEARCH TERMS (will be added as EXACT keywords) ---")
        col_q  = max(len("QUERY"),    max(len(k["text"]) for k in kw_to_add))
        col_mt = max(len("MATCH"),    10)
        col_tg = max(len("AD_GROUP"), max(len(t) for t in kw_targets))
        sep = f"  {'─'*col_q}  {'─'*col_mt}  {'─'*col_tg}"
        print(sep)
        print(f"  {'QUERY':<{col_q}}  {'MATCH':<{col_mt}}  {'AD_GROUP':<{col_tg}}")
        print(sep)
        for kw, tgt in zip(kw_to_add, kw_targets):
            print(f"  {kw['text']:<{col_q}}  {kw['match_type']:<{col_mt}}  {tgt:<{col_tg}}")
        print(sep)

    if neg_to_add:
        print()
        print("--- NEGATIVE SEARCH TERMS (will be added as BROAD campaign negatives) ---")
        col_q  = max(len("QUERY"),    max(len(k["text"]) for k in neg_to_add))
        col_mt = max(len("MATCH"),    10)
        col_tg = max(len("CAMPAIGN"), max(len(t) for t in neg_targets))
        sep = f"  {'─'*col_q}  {'─'*col_mt}  {'─'*col_tg}"
        print(sep)
        print(f"  {'QUERY':<{col_q}}  {'MATCH':<{col_mt}}  {'CAMPAIGN':<{col_tg}}")
        print(sep)
        for kw, tgt in zip(neg_to_add, neg_targets):
            print(f"  {kw['text']:<{col_q}}  {kw['match_type']:<{col_mt}}  {tgt:<{col_tg}}")
        print(sep)

    if watch_terms:
        print()
        print("--- WATCH TERMS (no action taken — review manually) ---")
        for t in watch_terms:
            print(f"  {t['query']}  [{t['clicks']} clicks, ${t['cost_usd']:.2f}]")

    print()
    if not _confirm(dry_run, yes):
        _log("Aborted.")
        return

    _log("Executing ...")

    # Add converting terms grouped by ad group (one batch per unique ad group)
    kw_added_total = 0
    if kw_to_add:
        # Group by adgroup resource name
        from collections import defaultdict
        by_adgroup: dict[str, list[dict]] = defaultdict(list)
        for kw, tgt in zip(kw_to_add, kw_targets):
            by_adgroup[tgt].append(kw)
        for ag_rn, kws in by_adgroup.items():
            added = _safe_add_keywords(ag_rn, kws, cid)
            kw_added_total += added
            _log(f"  {added}/{len(kws)} keywords added to {ag_rn}")

    # Add negatives grouped by campaign resource name
    neg_added_total = 0
    if neg_to_add:
        from collections import defaultdict
        by_campaign: dict[str, list[dict]] = defaultdict(list)
        for kw, tgt in zip(neg_to_add, neg_targets):
            by_campaign[tgt].append(kw)
        for camp_rn, kws in by_campaign.items():
            added = _safe_add_negatives(camp_rn, kws, cid)
            neg_added_total += added
            _log(f"  {added}/{len(kws)} negatives added to {camp_rn}")

    _log("Done.")
    print(f"\nAdded {kw_added_total} keywords, {neg_added_total} negatives")


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

def _print_help() -> None:
    print(__doc__)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Force UTF-8 output for Arabic keywords
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_help()
        return

    cmd = argv[0]
    rest = argv[1:]

    if cmd == "add-keywords":
        cmd_add_keywords(rest)
    elif cmd == "add-negatives":
        cmd_add_negatives(rest)
    elif cmd == "interactive":
        cmd_interactive(rest)
    elif cmd == "from-search-terms":
        cmd_from_search_terms(rest)
    else:
        print(f"Unknown command: {cmd!r}")
        print("Valid commands: add-keywords  add-negatives  interactive  from-search-terms")
        print("Run with --help for full usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
