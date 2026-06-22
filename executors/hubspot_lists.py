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


def _prop_recent_days(prop: str, days: int) -> dict:
    """HubSpot Lists v3 filter: datetime property within last N days.
    Uses IS_BETWEEN with rolling lower bound + NOW upper bound."""
    return {
        "filterType": "PROPERTY",
        "property":   prop,
        "operation": {
            "operationType": "TIME_RANGED",
            "operator":      "IS_BETWEEN",
            "lowerBoundTimePoint": {
                "timeType":             "ROLLING_DATE",
                "rollingDateDirection": "PAST",
                "rollingDateUnit":      "DAY",
                "rollingDateValue":     days,
            },
            "upperBoundTimePoint": {
                "timePointType": "NOW",
            },
        },
    }


def _prop_string_eq(prop: str, value: str) -> dict:
    """HubSpot Lists v3 filter: string property equals value."""
    return {
        "filterType": "PROPERTY",
        "property":   prop,
        "operation": {
            "operationType": "STRING",
            "operator":      "IS_EQUAL_TO",
            "value":         value,
        },
    }


def _prop_in_list(list_id: int) -> dict:
    """HubSpot Lists v3 filter: contact is a member of the given list_id.
    Used to compose exclusion stacks."""
    return {
        "filterType": "IN_LIST",
        "listId":     list_id,
    }


def _assoc_branch(*, object_type_id: str,
                  association_type_id: int,
                  property_filters: list[dict],
                  association_category: str = "HUBSPOT_DEFINED") -> dict:
    """HubSpot Lists v3 — filter contacts by their associated object's properties.

    Use cases:
        - Customer seeds: filter contacts whose associated Deal is in a given
          pipeline + Closed Won stage. object_type_id='0-3', association_type_id=4
        - SQL seeds: filter contacts whose associated Lead is in a given
          pipeline + Qualified stage. object_type_id='0-136', association_type_id=579

    Notes (discovered the hard way 2026-05-17):
        - Root filterBranch MUST be OR; wrapping AND must contain this ASSOCIATION
          branch inside its `filterBranches` array (not `filters`).
        - `operator` field MUST be 'IN_LIST' — misleading name, doesn't mean
          membership in a HubSpot list. It just means "associated objects match
          the property filters below."
        - The ASSOCIATION branch uses `filters` (a flat list of PROPERTY filters)
          directly, NOT a nested AND branch.
    """
    return {
        "filterBranchType":     "ASSOCIATION",
        "filterBranchOperator": "AND",
        "objectTypeId":         object_type_id,
        "operator":             "IN_LIST",
        "associationCategory":  association_category,
        "associationTypeId":    association_type_id,
        "filterBranches":       [],
        "filters":              property_filters,
    }


def _wrap_root(branch: dict) -> dict:
    """Root filterBranch must be OR > AND > [branch]. This wraps any branch."""
    return {
        "filterBranchType": "OR",
        "filterBranches": [
            {
                "filterBranchType": "AND",
                "filterBranches":   [branch],
                "filters":          [],
            }
        ],
    }


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


# ─── Product-segmented Lookalike seeds + exclusions (2026-05-17) ────────────
#
# Built after the May 2026 audit identified the need for product-clean
# Lookalike audiences. Each seed filters contacts by lifecyclestage AND
# `what_kind_of_service_are_you_interested_in` so the Lookalike Meta/Snap
# builds from is not contaminated across products.
#
# LIMITATION: the service-interest property is filled at lead-form time.
# Contacts who became customers via offline channels (referral, partner)
# may not have it set. v2 should switch to an ASSOCIATION-based filter
# using the deal's pipeline (Bookkeeping pipeline id=509382644, Qflavours
# id=3464043709, default = Invoice/Accounting).

# Product → which service_interest values map to this product
PRODUCT_SERVICE_MAP = {
    "Invoice":     ["E-Invoice Integration", "Accountin Software"],
    "Bookkeeping": ["Bookkeeping"],
    "Qflavours":   ["Q.flavours (F&B)"],
}

# Lifecycle stage internal names (HubSpot standard)
LCS_CUSTOMERS = ["customer", "evangelist"]
LCS_SQLS      = ["salesqualifiedlead", "opportunity"]
LCS_OPEN      = ["subscriber", "lead", "marketingqualifiedlead",
                 "salesqualifiedlead", "opportunity"]


def _product_sql_filter_legacy(product: str) -> dict:
    """LEGACY (deprecated 2026-05-17) — used contact-level property which
    is unfilled on 100% of customers. Kept only for reference."""
    return _and(
        _prop_in("lifecyclestage", LCS_SQLS),
        _prop_in("what_kind_of_service_are_you_interested_in",
                 PRODUCT_SERVICE_MAP[product]),
    )


def _open_leads_filter() -> dict:
    """Anyone whose lifecycle stage is below 'customer' — used as exclusion
    on prospecting campaigns to stop us re-marketing to active funnel leads."""
    return _and(
        _prop_in("lifecyclestage", LCS_OPEN),
    )


# ── Product → Deal pipeline + Closed Won stage mapping (Customer seeds) ─────
# Discovered 2026-05-17 by introspecting HubSpot pipelines API.

DEAL_PRODUCT_MAP: dict[str, dict[str, list[str]]] = {
    "Invoice": {
        "pipelines":   ["default", "453612238"],   # Sales Pipeline + Direct Purchase
        "won_stages":  ["closedwon", "696011984", "696011985"],
    },
    "Bookkeeping": {
        "pipelines":   ["509382644", "815011043", "3099025633"],
        "won_stages":  ["772726757", "1160293594", "4244565226"],
    },
    "Qflavours": {
        "pipelines":   ["3464043709"],
        "won_stages":  ["4739518652"],
    },
}

# Product → Lead pipeline + Qualified/Connected stage mapping (SQL seeds)
# The Lead object (objectTypeId 0-136) has its own pipelines. The user's
# manual reference list "LIST_LAL_Seed_SQLs_Bookkeeping" (639 contacts) uses
# Lead Pipeline "خدمة المحاسبة عن بعد" + stage "Qualified" — that's what
# we replicate here.

LEAD_PRODUCT_MAP: dict[str, dict[str, list[str]]] = {
    "Invoice": {
        # "Lead pipeline" (id=lead-pipeline-id, created 2024-07-23).
        # HubSpot uses human-readable string IDs for this pipeline — these
        # ARE the real IDs (confirmed via GET /crm/v3/pipelines/0-136 on 2026-06-22).
        "pipelines":  ["lead-pipeline-id"],
        "qualified":  ["qualified-stage-id", "connected-stage-id"],
    },
    "Bookkeeping": {
        # "خدمة المحاسبة عن بعد" pipeline
        "pipelines":  ["2004465911"],
        "qualified":  ["2739057856"],   # Qualified only — no separate Connected
    },
    "Qflavours": {
        "pipelines":  ["3463476418"],
        "qualified":  ["4739501271", "4739501270"],  # Qualified + Connected
    },
}


def _product_customer_filter(product: str) -> dict:
    """Customer LAL seed for one product. Filters contacts whose associated
    Deal is in the product's pipeline(s) and Closed Won. Matches the working
    manual reference list (LIST_LAL_Seed_Customers_Bookkeeping = ~673)."""
    cfg = DEAL_PRODUCT_MAP[product]
    return _assoc_branch(
        object_type_id="0-3",
        association_type_id=4,    # contact → deal (HUBSPOT_DEFINED)
        property_filters=[
            {
                "filterType": "PROPERTY",
                "property":   "pipeline",
                "operation": {
                    "operationType": "ENUMERATION",
                    "operator":      "IS_ANY_OF",
                    "values":        cfg["pipelines"],
                },
            },
            {
                "filterType": "PROPERTY",
                "property":   "dealstage",
                "operation": {
                    "operationType": "ENUMERATION",
                    "operator":      "IS_ANY_OF",
                    "values":        cfg["won_stages"],
                },
            },
        ],
    )


def _product_sql_filter(product: str) -> dict:
    """SQL LAL seed for one product. Filters contacts whose associated Lead
    is in the product's Lead pipeline + at Qualified/Connected stage. Matches
    the working manual reference list (LIST_LAL_Seed_SQLs_Bookkeeping = ~639).
    """
    cfg = LEAD_PRODUCT_MAP[product]
    return _assoc_branch(
        object_type_id="0-136",
        association_type_id=579,    # contact → lead (Primary Contact)
        property_filters=[
            {
                "filterType": "PROPERTY",
                "property":   "hs_pipeline",
                "operation": {
                    "operationType": "ENUMERATION",
                    "operator":      "IS_ANY_OF",
                    "values":        cfg["pipelines"],
                },
            },
            {
                "filterType": "PROPERTY",
                "property":   "hs_pipeline_stage",
                "operation": {
                    "operationType": "ENUMERATION",
                    "operator":      "IS_ANY_OF",
                    "values":        cfg["qualified"],
                },
            },
        ],
    )


def create_product_segmented_seeds() -> dict[str, Optional[dict]]:
    """Create the 9 product-segmented lists. Customer seeds use Deal-association
    filter; SQL seeds use Lead-association filter. Idempotent — re-running
    returns existing lists where they already exist."""
    out: dict[str, Optional[dict]] = {}

    # Customer LAL seeds — one per product, via associated Deal pipeline+won
    for product in DEAL_PRODUCT_MAP:
        name = f"[Nexa Agent] LAL Seed - Customers {product}"
        out[name] = create_list(name, _wrap_root(_product_customer_filter(product)),
                                dynamic=True)

    # SQL LAL seeds — one per product, via associated Lead pipeline+qualified
    for product in LEAD_PRODUCT_MAP:
        name = f"[Nexa Agent] LAL Seed - SQLs {product}"
        out[name] = create_list(name, _wrap_root(_product_sql_filter(product)),
                                dynamic=True)

    # Exclusions (contact-level — simple filters, no association needed)
    out["[Nexa Agent] Exclude - All Customers"] = create_list(
        "[Nexa Agent] Exclude - All Customers",
        _or(_and(_prop_in("lifecyclestage", LCS_CUSTOMERS))),
        dynamic=True,
    )
    out["[Nexa Agent] Exclude - Open Leads"] = create_list(
        "[Nexa Agent] Exclude - Open Leads",
        _or(_open_leads_filter()),
        dynamic=True,
    )
    out["[Nexa Agent] Exclude - Qoyod Employees"] = create_list(
        "[Nexa Agent] Exclude - Qoyod Employees",
        _or(_and(_prop_string_eq("hs_email_domain", "qoyod.com"))),
        dynamic=True,
    )

    return out


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
