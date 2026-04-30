"""
executors/naming.py
===================
Shared campaign naming convention and enforcement for all channels.

!! LinkedIn UTM mapping is DIFFERENT from all other channels !!
  Other channels:  campaign name = utm_campaign
  LinkedIn (UI now matches Meta — Campaign / Ad Set / Ad):
    Campaign = utm_campaign   (e.g. LinkedIn_Invoice, LinkedIn_Bookkeeping)
    Ad Set   = utm_audience   (e.g. LinkedIn_LeadGen_AR_Interests)
    Ad       = utm_content    (e.g. LinkedIn_VideoV1_AR)

  Name accordingly:
    Campaign: LinkedIn_{Product}                          e.g. LinkedIn_Invoice
    Ad Set:   LinkedIn_{Type}_{Language}_{Audience}       e.g. LinkedIn_LeadGen_AR_Interests
    Ad:       LinkedIn_{CreativeVariant}                  e.g. LinkedIn_VideoV1_AR

Convention: {Channel}_{Type}_{Language}_{Product}_{Audience}

  Channel   : Meta | Google | Snapchat | LinkedIn | TikTok
  Type      : LeadGen | Awareness | Video | Remarketing | Conversion |
               Search | PMax | Display
  Language  : AR | EN | AREN
  Product   : Invoice | Bookkeeping | Qflavours | General | {SeasonalName}
  Audience  : Interests | Lookalike | Retargeting | Broad

Audience rules (enforced):
  - Retargeting campaigns use "Retargeting" — never "Prospecting"
  - Prospecting campaigns use "Interests" or "Lookalike" — "Prospecting" alone is invalid
  - Valid values: Interests | Lookalike | Retargeting | Broad | {custom seasonal}

Product normalization (enforced):
  - E-Invoice / einvoice / e_invoice / EInvoice  → Invoice
  - Qbookkeeping / qbookkeeping / bookkeeping    → Bookkeeping
  - qflavours / flavours                         → Qflavours
  - Seasonal campaign names are kept as-is (e.g. Ramadan, NationalDay)
"""
from __future__ import annotations

import re

# ── Product aliases ────────────────────────────────────────────────────────────

_PRODUCT_ALIASES: dict[str, str] = {}

for _alias in ["einvoice", "e-invoice", "e_invoice", "eInvoice", "EInvoice",
               "E-Invoice", "E_Invoice"]:
    _PRODUCT_ALIASES[_alias.lower()] = "Invoice"

for _alias in ["qbookkeeping", "bookkeeping", "Bookkeeping", "Qbookkeeping"]:
    _PRODUCT_ALIASES[_alias.lower()] = "Bookkeeping"

for _alias in ["qflavours", "flavours", "Flavours", "Qflavours"]:
    _PRODUCT_ALIASES[_alias.lower()] = "Qflavours"


def _normalize_product(segment: str) -> str:
    return _PRODUCT_ALIASES.get(segment.lower(), segment)


# ── Audience rules ─────────────────────────────────────────────────────────────

_VALID_AUDIENCES = {"Interests", "Lookalike", "Retargeting", "Broad"}

# "Prospecting" by itself is not a valid audience label.
# Valid prospecting audiences are Interests or Lookalike.
_PROSPECTING_INVALID = "Prospecting"


def _validate_audience(audience: str, parts: list[str]) -> str:
    """
    Validate and normalise the audience segment.
    Raises ValueError with an instructive message on violation.
    """
    if audience.lower() == "prospecting":
        raise ValueError(
            f"'Prospecting' is not a valid audience label. "
            f"Use 'Interests' or 'Lookalike' for prospecting campaigns, "
            f"or 'Retargeting' for retargeting campaigns. "
            f"Got name parts: {parts}"
        )
    # Retargeting campaigns must not contain the word Prospecting anywhere
    if audience.lower() == "retargeting":
        for p in parts:
            if p.lower() == "prospecting":
                raise ValueError(
                    f"Retargeting campaigns must not contain 'Prospecting' in the name. "
                    f"Got name parts: {parts}"
                )
    # Reject any audience not in the approved set
    if audience not in _VALID_AUDIENCES:
        raise ValueError(
            f"'{audience}' is not a valid audience. "
            f"Must be one of: {sorted(_VALID_AUDIENCES)}. "
            f"Got name parts: {parts}"
        )
    return audience


# ── Core builder ──────────────────────────────────────────────────────────────

def build_name(
    channel: str,
    type_: str,
    language: str,
    product: str,
    audience: str,
) -> str:
    """
    Build and validate a campaign name following the convention.

    Examples
    --------
    build_name("Meta", "LeadGen", "AR", "E-Invoice", "Interests")
    -> "Meta_LeadGen_AR_Invoice_Interests"

    build_name("Snapchat", "LeadGen", "AR", "Qbookkeeping", "Retargeting")
    -> "Snapchat_LeadGen_AR_Bookkeeping_Retargeting"

    build_name("LinkedIn", "LeadGen", "AR", "Invoice", "Prospecting")  # raises
    """
    product  = _normalize_product(product)
    parts    = [channel, type_, language, product, audience]
    audience = _validate_audience(audience, parts)
    return "_".join(parts)


# ── Prefix helper (used by executors) ────────────────────────────────────────

def prefixed(channel_prefix: str, name: str) -> str:
    """
    Ensure name starts with '{channel_prefix}_'. Idempotent.
    Also normalises product aliases inside the name.

    If the name already has 5 underscore-separated parts and starts with
    the correct channel prefix, we normalise the product segment and
    validate the audience segment in-place.
    """
    prefix = f"{channel_prefix}_"
    if not name.startswith(prefix):
        name = prefix + name

    parts = name.split("_")
    # Normalise product (index 3) and validate audience (index 4) when present
    if len(parts) >= 4:
        parts[3] = _normalize_product(parts[3])
    if len(parts) >= 5:
        parts[4] = _validate_audience(parts[4], parts)
    return "_".join(parts)
