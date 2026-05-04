"""
executors/keyword_approval.py
==============================
Approval-gated keyword additions for Google Ads.

Flow:
  1. Nightly audit produces `add_as_keyword` (converting search terms) and
     `add_as_negative` (wasted spend terms).
  2. post_keyword_approval() posts a concise Slack message to #approvals
     with pre-added ✅/❌ reactions and persists the pending payload to
     memory/pending_keyword_approvals.json.
  3. The NEXT nightly run calls check_and_execute_pending() which reads the
     file, checks each Slack message for a ✅ reaction, executes approved
     additions via the Google Ads API, logs the result, and removes the entry.

Negative keywords are DIRECT-EXECUTE (no approval needed) and are handled
in audit_and_execute_negatives().
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

_PENDING_FILE = Path(__file__).parent.parent / "memory" / "pending_keyword_approvals.json"
_RIYADH = timezone(timedelta(hours=3))


# ─── Slack approval posting ───────────────────────────────────────────────────

def post_keyword_approval(add_kw: list[dict], add_neg: list[dict]) -> str | None:
    """
    Keywords go to Asana only (via google_ads_audit_tasks.py). No Slack post.
    Negatives are direct-executed immediately; converting terms are persisted
    as Asana tasks and skipped here (no approval gate without Slack).
    """
    if not add_kw and not add_neg:
        return None

    from logs.activity_logger import log_activity_async as _bq_log

    if add_neg:
        _execute_negatives(add_neg)
        print(f"[keyword-approval] Direct-executed {len(add_neg)} negatives (no Slack)")
        _bq_log(role="keyword_approval",
                      action=f"direct-executed {len(add_neg)} negative keywords",
                      channel="google_ads", status="ok", rows_affected=len(add_neg),
                      details={"terms": [t.get("query", "") for t in add_neg[:10]]})

    if add_kw:
        print(f"[keyword-approval] {len(add_kw)} converting terms → Asana only (no Slack)")
        _bq_log(role="keyword_approval",
                      action=f"{len(add_kw)} converting search terms → Asana task",
                      channel="google_ads", status="ok", rows_affected=len(add_kw),
                      details={"terms": [t.get("query", "") for t in add_kw[:10]]})

    return None


# ─── State persistence ────────────────────────────────────────────────────────

def _persist_pending(ts: str | None,
                     add_kw: list[dict],
                     add_neg: list[dict]) -> None:
    """Append a new pending approval record to the JSON file."""
    records = _load_pending()
    records.append({
        "ts":         ts,
        "add_kw":     add_kw,
        "add_neg":    add_neg,
        "created_at": datetime.now(_RIYADH).isoformat(),
        "executed":   False,
    })
    _save_pending(records)


def _load_pending() -> list[dict]:
    if _PENDING_FILE.exists():
        try:
            return json.loads(_PENDING_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_pending(records: list[dict]) -> None:
    _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PENDING_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── Check approvals and execute ─────────────────────────────────────────────

def check_and_execute_pending() -> dict:
    """
    Read pending approvals, check Slack reactions, execute approved ones.
    Returns {"executed": int, "skipped": int, "pending": int}.
    """
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_APPROVAL
    from notifications.quiet import is_quiet

    records = _load_pending()
    if not records:
        print("[keyword-approval] No pending approvals.")
        return {"executed": 0, "skipped": 0, "pending": 0}

    executed = skipped = 0
    remaining: list[dict] = []

    wc = WebClient(token=SLACK_BOT_TOKEN)

    for rec in records:
        ts = rec.get("ts")
        add_kw  = rec.get("add_kw",  [])
        add_neg = rec.get("add_neg", [])

        # No ts = posted in quiet mode; execute negatives, skip keyword adds
        if not ts:
            if add_neg:
                _execute_negatives(add_neg)
            skipped += len(add_kw)
            continue

        # Check Slack reaction
        approval = _check_reaction(wc, SLACK_CHANNEL_APPROVAL, ts)

        if approval == "approved":
            print(f"[keyword-approval] ts={ts} approved — executing {len(add_kw)} keywords, "
                  f"{len(add_neg)} negatives")
            _execute_keywords(add_kw)
            _execute_negatives(add_neg)
            executed += len(add_kw) + len(add_neg)
            # Don't keep in remaining — resolved

        elif approval == "rejected":
            print(f"[keyword-approval] ts={ts} rejected — skipping {len(add_kw)} keywords")
            skipped += len(add_kw)
            if add_neg:
                # Negatives execute even if keywords are rejected
                _execute_negatives(add_neg)
            # Resolved — don't keep

        else:  # pending — keep for next run, but expire after 3 days
            from datetime import datetime as _dt
            created = _dt.fromisoformat(rec["created_at"])
            age_days = (_dt.now(_RIYADH) - created).days
            if age_days >= 3:
                print(f"[keyword-approval] ts={ts} expired after {age_days}d — discarding")
                skipped += len(add_kw)
            else:
                remaining.append(rec)

    _save_pending(remaining)
    print(f"[keyword-approval] Done. executed={executed}, skipped={skipped}, "
          f"pending={len(remaining)}")
    return {"executed": executed, "skipped": skipped, "pending": len(remaining)}


def _check_reaction(wc, channel: str, ts: str) -> str:
    """Returns 'approved', 'rejected', or 'pending'."""
    from slack_sdk.errors import SlackApiError
    try:
        resp = wc.reactions_get(channel=channel, timestamp=ts)
        reactions = [r["name"] for r in resp.get("message", {}).get("reactions", [])]
        # Bot pre-adds both reactions with rows_affected=1; user approval adds rows_affected=2+
        for r in resp.get("message", {}).get("reactions", []):
            if r["name"] == "white_check_mark" and r["count"] >= 2:
                return "approved"
            if r["name"] == "x" and r["count"] >= 2:
                return "rejected"
        return "pending"
    except SlackApiError as e:
        print(f"[keyword-approval] reaction check error: {e}")
        return "pending"


# ─── Execution helpers ────────────────────────────────────────────────────────

def _execute_keywords(add_kw: list[dict]) -> None:
    """Add each approved search term as an EXACT-match keyword in its ad group."""
    from executors.google_ads import add_keywords

    # Group by (customer_id, ad_group_resource) to batch API calls
    groups: dict[tuple, list[dict]] = {}
    for kw in add_kw:
        key = (kw.get("customer_id", ""), kw.get("ad_group_resource", ""))
        if not key[0] or not key[1]:
            print(f"[keyword-approval] skipping '{kw['term']}' — missing resource info")
            continue
        groups.setdefault(key, []).append(kw)

    for (cid, ag_rn), batch in groups.items():
        kw_payloads = [{"text": kw["term"], "match_type": "EXACT"} for kw in batch]
        try:
            add_keywords(
                adgroup_resource_name=ag_rn,
                keywords=kw_payloads,
                customer_id=cid,
            )
            terms = ", ".join(f"`{kw['term']}`" for kw in batch)
            print(f"[keyword-approval] EXECUTED: added to {ag_rn}: {terms}")
        except Exception as e:
            print(f"[keyword-approval] add_keywords failed for {ag_rn}: {e}")


def _execute_negatives(add_neg: list[dict]) -> None:
    """Add wasted search terms as EXACT negative keywords at campaign level."""
    from executors.google_ads import add_negative_keywords

    # Group by (customer_id, campaign_resource)
    groups: dict[tuple, list[dict]] = {}
    for neg in add_neg:
        key = (neg.get("customer_id", ""), neg.get("campaign_resource", ""))
        if not key[0] or not key[1]:
            print(f"[keyword-approval] skipping negative '{neg['term']}' — missing resource info")
            continue
        groups.setdefault(key, []).append(neg)

    for (cid, camp_rn), batch in groups.items():
        neg_payloads = [{"text": neg["term"], "match_type": "EXACT"} for neg in batch]
        try:
            add_negative_keywords(
                campaign_resource_name=camp_rn,
                keywords=neg_payloads,
                customer_id=cid,
            )
            terms = ", ".join(f"`{neg['term']}`" for neg in batch)
            print(f"[keyword-approval] EXECUTED: negatives added to {camp_rn}: {terms}")
        except Exception as e:
            print(f"[keyword-approval] add_negative_keywords failed for {camp_rn}: {e}")


# ─── Manual trigger ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = check_and_execute_pending()
    print(result)
