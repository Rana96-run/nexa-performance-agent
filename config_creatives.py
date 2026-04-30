"""
config_creatives.py
====================
Central registry for creatives, forms, pixels, and landing pages.

Add new forms / URLs here — executors (snapchat.py, meta.py) read from this
file. Never hardcode IDs inside executor logic.

Product key normalisation (matches executors/naming.py):
  "invoice"     — E-Invoice / Electronic Invoicing / General SaaS
  "bookkeeping" — Q Bookkeeping
  "qflavours"   — Q Flavours / F&B product
  "generic"     — fallback / brand / multi-product

Snapchat account keys:
  "2025" → SNAPCHAT_AD_ACCOUNT_2025
  "2024" → SNAPCHAT_AD_ACCOUNT_2024
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── Snapchat ─────────────────────────────────────────────────────────────────

# Self Service Pixel — active on both accounts (used for WEB_FORM campaigns)
SNAPCHAT_PIXEL_ID = "a6ed1404-e115-4993-82e0-ba26a6e6f870"
SNAPCHAT_PIXEL_NAME = "Qoyod Self Service Pixel"

# Instant form IDs per account × product
# Key: (account_key, product_key)  →  {"name": str, "id": str}
SNAPCHAT_FORMS: dict[tuple[str, str], dict] = {
    # ── Qoyod 2024 account ────────────────────────────────────────────────────
    ("2024", "generic"):     {"name": "Snapchat_LeadGenForm_Generic",
                              "id":   "8f7ac7b2-5b07-46b1-9494-25d5e83f2ad3"},
    ("2024", "invoice"):     {"name": "Snapchat_LeadGenForm_Generic",
                              "id":   "8f7ac7b2-5b07-46b1-9494-25d5e83f2ad3"},
    ("2024", "qflavours"):   {"name": "Snapchat_LeadGen_QFlavours_2024",
                              "id":   "5d99d72c-9532-4496-b994-1955780c4607"},
    # ── Qoyod 2025 account ────────────────────────────────────────────────────
    ("2025", "generic"):     {"name": "Snapchat_Generic_Form_New_Account",
                              "id":   "63b24ba3-60d0-49b7-a28d-c87f96e0cb01"},
    ("2025", "invoice"):     {"name": "Snapchat_Generic_Form_New_Account",
                              "id":   "63b24ba3-60d0-49b7-a28d-c87f96e0cb01"},
    ("2025", "bookkeeping"): {"name": "Bookkeeping2026_NewAcc",
                              "id":   "630ce234-1219-4dfc-8cec-654227175c73"},
}

# Account GID → key mapping (resolves env var → "2024" / "2025")
_ACCT_2025 = os.getenv("SNAPCHAT_AD_ACCOUNT_2025", "")
_ACCT_2024 = os.getenv("SNAPCHAT_AD_ACCOUNT_2024", "")

def snapchat_account_key(account_id: str) -> str:
    """Return '2025' or '2024' for a given account GID."""
    if account_id == _ACCT_2025:
        return "2025"
    if account_id == _ACCT_2024:
        return "2024"
    return "2025"  # default


def snapchat_form(account_id: str, product: str) -> dict:
    """
    Return {"name": ..., "id": ...} for the correct lead gen form.

    Falls back:  product → "invoice" → "generic"
    account fallback: 2024 account Bookkeeping → uses 2025 form
    """
    key = snapchat_account_key(account_id)
    prod = _normalise_product(product)

    form = SNAPCHAT_FORMS.get((key, prod))
    if form:
        return form

    # Cross-account fallback (e.g. bookkeeping on 2024 → use 2025 form)
    for alt_key in ("2025", "2024"):
        form = SNAPCHAT_FORMS.get((alt_key, prod))
        if form:
            return form

    # Final fallback: generic on same account
    return SNAPCHAT_FORMS.get((key, "generic"),
           SNAPCHAT_FORMS[("2025", "generic")])


# ─── Meta ─────────────────────────────────────────────────────────────────────

# Pixels — available on both Meta accounts
META_CRM_PIXEL_ID   = "1782671302631317"   # Qoyod_CRM_PIXEL  (primary — all web form campaigns)
META_WEB_PIXEL_ID   = "3036579196577051"   # Qoyod_Web_PIXEL  (secondary / backup)
META_CRM_PIXEL_NAME = "Qoyod_CRM_PIXEL"

# Instant form names per product (IDs resolved at runtime via Meta API)
# Where multiple forms exist, first entry is the primary (higher intent).
META_FORMS: dict[str, list[str]] = {
    "generic":     ["Meta_LeadGen_Form_CallTimeAdded"],
    "invoice":     ["Meta_LeadGen_Form_CallTimeAdded"],
    "bookkeeping": ["Meta_Bookkeeping_HigherIntent", "Meta_Bookkeeping_MoreVolume"],
    "qflavours":   ["Meta_LeadGen_Form_CallTimeAdded"],  # no dedicated form yet
}


def meta_form_name(product: str, intent: str = "higher") -> str:
    """
    Return Meta instant form name for product.
    intent: "higher" → first form in list (higher intent)
            "volume"  → last form (more volume / lighter)
    """
    prod  = _normalise_product(product)
    forms = META_FORMS.get(prod, META_FORMS["generic"])
    if intent == "volume" and len(forms) > 1:
        return forms[-1]
    return forms[0]


# ─── Web form landing pages ───────────────────────────────────────────────────

# Primary landing page per product (first URL is preferred)
WEB_FORM_URLS: dict[str, list[str]] = {
    "generic":     [
        "https://campaigns.qoyod.com/ar/new-form-free-trial",
        "https://lp.qoyod.com/accounting/",
    ],
    "invoice":     [
        "https://campaigns.qoyod.com/ar/electronic-invoicing",
        "https://campaigns.qoyod.com/ar/new-form-free-trial",
    ],
    "bookkeeping": [
        "https://campaigns.qoyod.com/ar/qoyod-bookkeeping",
    ],
    "qflavours":   [
        "https://lp.qoyod.com/Qflavours",
    ],
}


def web_form_url(product: str, variant: int = 0) -> str:
    """
    Return landing page URL for product.
    variant=0 → primary, variant=1 → alternative (if available).
    """
    prod = _normalise_product(product)
    urls = WEB_FORM_URLS.get(prod, WEB_FORM_URLS["generic"])
    return urls[min(variant, len(urls) - 1)]


# ─── Product key normalisation ────────────────────────────────────────────────

_PRODUCT_ALIASES: dict[str, str] = {
    # Invoice / E-Invoice
    "invoice":          "invoice",
    "e-invoice":        "invoice",
    "einvoice":         "invoice",
    "e_invoice":        "invoice",
    "electronicinvoice": "invoice",
    "electronic-invoice": "invoice",
    # Bookkeeping
    "bookkeeping":      "bookkeeping",
    "qbookkeeping":     "bookkeeping",
    "q_bookkeeping":    "bookkeeping",
    # Qflavours
    "qflavours":        "qflavours",
    "q_flavours":       "qflavours",
    "flavours":         "qflavours",
    # Generic / feature / brand
    "generic":          "generic",
    "general":          "generic",
    "feature":          "generic",
    "brand":            "generic",
    "saas":             "generic",
}


def _normalise_product(product: str) -> str:
    return _PRODUCT_ALIASES.get(product.lower().strip(), "generic")


def normalise_product(product: str) -> str:
    """Public alias for external callers."""
    return _normalise_product(product)
