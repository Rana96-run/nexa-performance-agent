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

# Common spellings + typos in production campaign names that should normalise
# to one of the four canonical audience tokens. Updated 2026-05-17 after
# auditing existing campaign names — production reality uses 6-7 token names
# with audience tokens that don't always live at position 4.
_AUDIENCE_ALIASES = {
    # canonical → itself (lowercased for lookup)
    "interests":   "Interests",
    "interest":    "Interests",     # singular — production uses both
    "intersts":    "Interests",     # typo seen in live data
    "lookalike":   "Lookalike",
    "lookalikes":  "Lookalike",
    "lal":         "Lookalike",
    "retargeting": "Retargeting",
    "rtg":         "Retargeting",
    "broad":       "Broad",
}


def _find_audience_token(parts: list[str]) -> tuple[int | None, str | None]:
    """Scan parts for a token that matches a valid audience (or alias).
    Returns (index, canonical_audience) or (None, None) if not found."""
    for i, p in enumerate(parts):
        canonical = _AUDIENCE_ALIASES.get(p.lower())
        if canonical:
            return i, canonical
    return None, None


def _validate_audience(audience: str, parts: list[str]) -> str:
    """
    Validate and normalise an audience segment that's already been identified
    (caller has determined which token is the audience). Raises ValueError
    with an instructive message on violation.
    """
    if audience.lower() == "prospecting":
        raise ValueError(
            f"'Prospecting' is not a valid audience label. "
            f"Use 'Interests' or 'Lookalike' for prospecting campaigns, "
            f"or 'Retargeting' for retargeting campaigns. "
            f"Got name parts: {parts}"
        )
    # Normalise via aliases (handles 'Interest', 'Intersts', etc.)
    canonical = _AUDIENCE_ALIASES.get(audience.lower(), audience)
    # Retargeting campaigns must not contain the word Prospecting anywhere
    if canonical.lower() == "retargeting":
        for p in parts:
            if p.lower() == "prospecting":
                raise ValueError(
                    f"Retargeting campaigns must not contain 'Prospecting' in the name. "
                    f"Got name parts: {parts}"
                )
    if canonical not in _VALID_AUDIENCES:
        raise ValueError(
            f"'{audience}' is not a valid audience. "
            f"Must be one of: {sorted(_VALID_AUDIENCES)} "
            f"(aliases: {sorted(set(_AUDIENCE_ALIASES.keys()) - {a.lower() for a in _VALID_AUDIENCES})}). "
            f"Got name parts: {parts}"
        )
    return canonical


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
    Also normalises product aliases + audience tokens inside the name.

    Production campaign names use a variable token count (5-9 tokens),
    e.g. `Meta_LeadGen_Bookkeeping_Prospecting_Intersts_MaxmizeLeads_Instantform`.
    This validator scans for the audience token *anywhere* in the name
    and normalises it (canonicalising aliases / typos like `Intersts` → `Interests`).

    If no audience token is found, the name is left as-is — we don't reject
    legacy/variant names from being prefixed. To enforce strict 5-token
    structure on a fresh build, use `build_name()` instead.
    """
    prefix = f"{channel_prefix}_"
    if not name.startswith(prefix):
        name = prefix + name

    parts = name.split("_")

    # Normalise product (typically index 3 in 5-token form, but may be elsewhere
    # for 6-7 token variants). Apply normalisation to all interior tokens that
    # match a product alias.
    for i in range(2, min(len(parts), 5)):  # search positions 2..4
        normalised = _normalize_product(parts[i])
        if normalised != parts[i]:
            parts[i] = normalised
            break  # only normalise the first product hit

    # Find the audience token anywhere in the name and normalise/validate it.
    idx, canonical = _find_audience_token(parts)
    if idx is not None:
        parts[idx] = _validate_audience(canonical, parts)
    else:
        # No valid audience token found — that's fine for legacy names UNLESS
        # the name contains 'Prospecting'. Prospecting must always be paired
        # with an explicit audience (Interests / Lookalike) per CLAUDE.md.
        if any(p.lower() == "prospecting" for p in parts):
            raise ValueError(
                f"'Prospecting' is present but no audience token (Interests / "
                f"Lookalike / Retargeting / Broad) was found in the name. "
                f"Per CLAUDE.md, Prospecting must be paired with an explicit "
                f"audience. Got name parts: {parts}"
            )

    return "_".join(parts)
