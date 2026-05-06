"""
executors/keyword_policy.py
============================
Single source of truth for Google Ads keyword policy.

All call sites (nightly audit, bulk_keywords manual tool, ad-hoc scripts)
import these patterns + helpers so the rules stay in lockstep.

Three buckets:
  1. ALWAYS_NEGATIVE  — direct-execute as negative, never proposed as a keyword.
  2. BRAND_ONLY       — only allowed in campaigns whose name contains "Brand".
                         Outside Brand campaigns: drop from add_kw, route to pause-watch.
  3. NEVER_NEGATIVE   — competitor brands; never excluded, but pause if not converting.

Pattern matching is case-insensitive substring.
"""
from __future__ import annotations


# ── 1. ALWAYS NEGATIVE ────────────────────────────────────────────────────────
# Terms matching ANY of these are excluded immediately, never shown as expansion
# candidates. Add a term here only when it has zero chance of being qualified
# intent — accountancy software for SMB owners has nothing to do with these.
ALWAYS_NEGATIVE_PATTERNS: list[str] = [
    # Existing accounts / login flows — the user is already a customer
    "sign in", "signin", "log in", "login",
    "تسجيل الدخول", "تسجيل دخول", "تسجيل  دخول",
    # Free / promo seekers — won't pay for SaaS
    "مجاني", "مجانا", "مجانية", "مجانى", "مجانًا",
    "free",
    # Course / training intent — they want to learn accounting, not buy software
    "دورة", "دورات", "كورس", "كورسات",
    "course", "courses", "training",
    # Download intent — looking for cracked software / pirated PDFs
    "تحميل", "تنزيل",
    "download",
    # Loan / financing — wrong intent entirely
    "قرض", "قروض", "قرضي",
    "تمويل", "تمويلي", "تمويلات",
    "loan", "loans", "financing",
    # Job seekers — not SMB owners
    "وظيفة", "وظائف", "توظيف",
    "فرص عمل", "فرصة عمل",
    "job", "jobs", "career", "careers", "hiring",
]


# ── 2. BRAND-ONLY (قيود + variants) ───────────────────────────────────────────
# These appear in our brand campaigns. Outside a Brand campaign we do NOT bid
# on them — drop from add_kw expansion candidates and route to pause-watch
# instead so a human reviews.
#
# IMPORTANT — Arabic ambiguity: "قيود" in Saudi Arabic has TWO meanings:
#   (a) the company name "Qoyod" — brand reference
#   (b) the accounting term "journal entries" — generic SaaS feature term
# We disambiguate by accounting modifiers: when the term ALSO contains
# "محاسبية" / "المحاسبة" / "يومية" / "اليومية" it is meaning (b) — a feature
# keyword like "قيود محاسبية" or "قيود المحاسبة". Those are allowed in any
# bookkeeping/accounting campaign and treated as normal keywords.
BRAND_ONLY_PATTERNS: list[str] = [
    "قيود",
    "qoyod",
]

# If a "قيود"-containing term ALSO matches any of these, it is the accounting
# noun (entries / journal entries) and should be treated as a normal feature
# keyword — NOT brand-only.
QIYUD_FEATURE_MODIFIERS: list[str] = [
    "محاسبية",
    "المحاسبة",
    "محاسبه",      # without diacritic
    "اليومية",
    "يومية",
    "journal",
    "accounting entries",
]


# ── 3. NEVER NEGATIVE (competitors) ───────────────────────────────────────────
# Competitor brand names — we want our ad to show alongside theirs. Never add
# as a negative; if not converting after 14 days, pause the keyword instead.
NEVER_NEGATIVE_PATTERNS: list[str] = [
    "zoho", "quickbooks", "odoo", "xero", "sage", "wave",
    "منافس", "منافسين",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def matches_any(term: str, patterns: list[str]) -> bool:
    """Case-insensitive substring check against a list of patterns."""
    t = (term or "").lower()
    return any(p.lower() in t for p in patterns)


def is_brand_campaign(campaign_name: str) -> bool:
    """A campaign is a Brand campaign iff 'brand' appears in its name (case-insensitive).
    Matches our naming convention `{Channel}_{Type}_{Language}_Brand[_v2]`.
    """
    return "brand" in (campaign_name or "").lower()


def classify_term(term: str, campaign_name: str) -> str:
    """
    Returns one of:
      - "always_negative"  → execute as negative immediately (no approval)
      - "brand_only_block" → قيود/qoyod term in non-brand campaign — drop, pause-watch
      - "brand_allowed"    → قيود/qoyod term in a Brand campaign — allow as keyword
      - "never_negative"   → competitor — pause-watch only, never exclude
      - "normal"           → no policy match; route by performance

    Special case: "قيود" + accounting modifier (محاسبية / المحاسبة / يومية)
    is treated as the accounting NOUN (journal entries), not the brand name,
    and falls through to "normal".
    """
    if matches_any(term, ALWAYS_NEGATIVE_PATTERNS):
        return "always_negative"
    if matches_any(term, BRAND_ONLY_PATTERNS):
        # قيود + accounting modifier = feature keyword, not brand reference.
        if matches_any(term, QIYUD_FEATURE_MODIFIERS):
            return "normal"
        return "brand_allowed" if is_brand_campaign(campaign_name) else "brand_only_block"
    if matches_any(term, NEVER_NEGATIVE_PATTERNS):
        return "never_negative"
    return "normal"
