"""
executors/keyword_approval.py
==============================
Keyword execution helpers.

Keywords are managed via Asana tasks only — there is no Slack approval gate.
Negatives are direct-executed (no approval needed; no spend at risk).

The previous Slack-post + pending-JSON workflow has been removed; the only
public entry point left is `_execute_negatives`, which is called from
`analysers/google_ads_audit_tasks.py` for both normal `add_neg` (wasted spend)
and `auto_neg` (always-negative policy matches).
"""
from __future__ import annotations


def _execute_negatives(add_neg: list[dict]) -> None:
    """Add wasted search terms as EXACT negative keywords at campaign level."""
    from executors.google_ads import add_negative_keywords

    # Group by (customer_id, campaign_resource)
    groups: dict[tuple, list[dict]] = {}
    for neg in add_neg:
        key = (neg.get("customer_id", ""), neg.get("campaign_resource", ""))
        if not key[0] or not key[1]:
            print(f"[keyword-approval] skipping negative '{neg.get('term','?')}' — missing resource info")
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
            try:
                from logs.activity_logger import log_activity_async
                log_activity_async(
                    role="keyword_management", action="negative_keywords_added",
                    channel="google_ads", rows_affected=len(batch),
                    details={"terms": [neg["term"] for neg in batch[:20]],
                             "campaign_resource": camp_rn},
                )
            except Exception:
                pass
        except Exception as e:
            print(f"[keyword-approval] add_negative_keywords failed for {camp_rn}: {e}")
