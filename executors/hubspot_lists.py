"""
executors/hubspot_lists.py
==========================
Create / get HubSpot Lists via the v3 API.

Used for:
- Lookalike seed audiences (push to LinkedIn Matched / Meta CAPI / Google CM)
- Exclusion lists (don't pay to acquire existing customers)
- Re-engagement audiences (60d+ disqualified-by-timing)
- Sales-handoff alerting (qualified lead, no contact in 14d)

API: HubSpot Lists v3 — https://developers.hubspot.com/docs/reference/api/crm/lists/lists
Auth: HUBSPOT_ACCESS_TOKEN (private app token already in .env)
"""
from __future__ import annotations

import os
import requests
from typing import Optional

BASE = "https://api.hubapi.com"

OBJECT_CONTACT = "0-1"
OBJECT_DEAL    = "0-3"


def _headers() -> dict:
    # Read at call-time so dotenv has a chance to populate the env first.
    return {
        "Authorization": f"Bearer {os.getenv('HUBSPOT_ACCESS_TOKEN', '')}",
        "Content-Type":  "application/json",
    }


def find_list_by_name(name: str, object_type: str = OBJECT_CONTACT) -> Optional[dict]:
    """Return existing list dict if a list with this name exists, else None."""
    r = requests.post(
        f"{BASE}/crm/v3/lists/search",
        headers=_headers(),
        json={
            "query":            name,
            "objectTypeId":     object_type,
            "additionalProperties": ["hs_list_size"],
        },
        timeout=15,
    )
    if r.status_code >= 400:
        print(f"[hs-lists] search error {r.status_code}: {r.text[:200]}")
        return None
    for it in r.json().get("lists", []):
        if (it.get("name") or "").strip().lower() == name.strip().lower():
            return it
    return None


def create_list(name: str, filter_branch: dict, *,
                object_type: str = OBJECT_CONTACT,
                dynamic: bool = True) -> Optional[dict]:
    """
    Create a HubSpot list.  Returns the created list dict, or None on failure.
    If a list with this name already exists, returns the existing one.
    """
    existing = find_list_by_name(name, object_type=object_type)
    if existing:
        print(f"[hs-lists] '{name}' already exists (listId={existing.get('listId')})")
        return existing

    body = {
        "name":           name,
        "objectTypeId":   object_type,
        "processingType": "DYNAMIC" if dynamic else "MANUAL",
        "filterBranch":   filter_branch,
    }
    r = requests.post(f"{BASE}/crm/v3/lists",
                      headers=_headers(), json=body, timeout=20)
    if r.status_code >= 400:
        print(f"[hs-lists] create '{name}' failed {r.status_code}: {r.text[:300]}")
        return None
    out = r.json().get("list", {}) or r.json()
    print(f"[hs-lists] created '{name}' (listId={out.get('listId')})")
    return out


# ─── Filter builders for the standard segments ──────────────────────────────

def _and(*filters):
    return {"filterBranchType": "AND", "filters": list(filters)}


def _or(*branches):
    return {"filterBranchType": "OR", "filterBranches": list(branches)}


def _prop_in(prop: str, values: list[str]) -> dict:
    """HubSpot Lists v3 filter: property is one of N enum values."""
    return {
        "filterType": "PROPERTY",
        "property":   prop,
        "operation": {
            "operationType": "ENUMERATION",
            "operator":      "IS_ANY_OF",
            "values":        values,
        },
    }


def _prop_eq(prop: str, value: str) -> dict:
    return _prop_in(prop, [value])


# ─── The 5 standard segments ────────────────────────────────────────────────

LOOKALIKE_SEED_NAME = "LIST_won_deals_lookalike_seed"
LOOKALIKE_SEED_FILTERS = _or(
    {"filterBranchType": "AND", "filters": [
        _prop_in("lifecyclestage", ["customer", "evangelist"])
    ]},
)


CUSTOMER_EXCLUDE_NAME = "LIST_existing_customers_exclude"
CUSTOMER_EXCLUDE_FILTERS = _or(
    {"filterBranchType": "AND", "filters": [
        _prop_in("lifecyclestage", ["customer", "evangelist"])
    ]},
)


def create_lookalike_seed_list() -> Optional[dict]:
    return create_list(LOOKALIKE_SEED_NAME, LOOKALIKE_SEED_FILTERS, dynamic=True)


def create_customer_exclude_list() -> Optional[dict]:
    return create_list(CUSTOMER_EXCLUDE_NAME, CUSTOMER_EXCLUDE_FILTERS, dynamic=True)


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from dotenv import load_dotenv
    load_dotenv()
    print("Creating HubSpot lookalike-seed and customer-exclude lists…")
    a = create_lookalike_seed_list()
    b = create_customer_exclude_list()
    print()
    print(f"  Lookalike seed:    {a.get('listId') if a else 'FAILED'}")
    print(f"  Customer exclude:  {b.get('listId') if b else 'FAILED'}")
