"""
executors/keyword_policy.py
============================
Single source of truth for Google Ads keyword policy.

All call sites (nightly audit, bulk_keywords manual tool, ad-hoc scripts)
import these patterns + helpers so the rules stay in lockstep.

Buckets:
  1. ALWAYS_NEGATIVE  — direct-execute as negative, never proposed as a keyword.
  2. BRAND_ONLY       — only allowed in campaigns whose name contains "Brand"
                         (with an exception for the Arabic accounting noun
                         "قيود محاسبية" / "قيود المحاسبة" — see QIYUD_FEATURE_MODIFIERS).
  3. COMPETITOR       — competitor brand names; ONLY allowed in campaigns
                         whose name contains "Competitor". Never excluded.
                         In any other campaign → pause-watch (move or pause).

Cross-cutting rules:
  4. Language match — AR keyword cannot live in `_EN_` campaign (and vice versa).
  5. Never remove a keyword with non-zero historical spend — only pause.
  6. Wasted spend ≥ $80 in 7 days → pause the keyword (don't add as negative).
"""
from __future__ import annotations

import re


# ── 1. ALWAYS NEGATIVE ────────────────────────────────────────────────────────
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
# IMPORTANT — Arabic ambiguity: "قيود" in Saudi Arabic has TWO meanings:
#   (a) the company name "Qoyod" — brand reference
#   (b) the accounting term "journal entries" — generic SaaS feature term
# We disambiguate by accounting modifiers — when the term ALSO contains
# "محاسبية" / "المحاسبة" / "يومية" / "اليومية" it is meaning (b) — a feature
# keyword like "قيود محاسبية". Those are allowed in any campaign as normal.
BRAND_ONLY_PATTERNS: list[str] = [
    "قيود",
    "qoyod",
]

QIYUD_FEATURE_MODIFIERS: list[str] = [
    "محاسبية",
    "المحاسبة",
    "محاسبه",
    "اليومية",
    "يومية",
    "journal",
    "accounting entries",
]


# ── 3. COMPETITORS ────────────────────────────────────────────────────────────
# Competitor brand names. ONLY allowed in campaigns whose name contains
# "Competitor". In any other campaign:
#   - Don't add as keyword (drop from add_kw)
#   - Don't add as negative (we still want to bid on these — just in the right
#     campaign)
#   - Pause-watch the keyword that triggered the search → human moves or pauses.
COMPETITOR_PATTERNS: list[str] = [
    # Foodics (point-of-sale / restaurants)
    "foodics", "فودكس", "فوديكس",
    # Daftra (accounting)
    "daftra", "دفترة", "دفتره",
    # Manager.io
    "manager io", "manager.io", "managerio",
    "الاستاذ المحاسبي", "الأستاذ المحاسبي", "الاستاذ المحاسبه",   # Al-Ostaz (full phrase only —
    # bare الاستاذ / الأستاذ means "teacher/Mr." in Arabic and would false-positive)
    # Wafeq (use only distinct spellings; bare "وافق" / "وفق" mean "agreed/in accordance with")
    "wafeq", "وافيق",
    # International accounting SaaS
    "zoho", "quickbooks", "odoo", "اودو", "أودو",
    "xero", "sage", "wave",
    # Generic competitor noun
    "منافس", "منافسين",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def matches_any(term: str, patterns: list[str]) -> bool:
    """Case-insensitive substring check against a list of patterns."""
    t = (term or "").lower()
    return any(p.lower() in t for p in patterns)


def is_brand_campaign(campaign_name: str) -> bool:
    """Campaign name contains 'brand' (case-insensitive). Matches our naming
    convention `{Channel}_{Type}_{Language}_Brand[_v2]`.
    """
    return "brand" in (campaign_name or "").lower()


def is_competitor_campaign(campaign_name: str) -> bool:
    """Campaign name contains 'competitor' (case-insensitive). Matches our
    naming convention `{...}_Competitor[_AccN]` for competitor-targeting
    campaigns where bidding on rival brand names is expected.
    """
    return "competitor" in (campaign_name or "").lower()


# ── Language detection ────────────────────────────────────────────────────────
_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")
_LATIN_RE  = re.compile(r"[A-Za-z]")


def detect_text_language(text: str) -> str:
    """Returns 'ar' / 'en' / 'mixed' / 'none' based on character ranges.
    Numbers and punctuation are ignored. A term with both Arabic letters
    and Latin letters returns 'mixed' — we treat that as no clear mismatch
    (it's typically a transliterated brand inside an Arabic phrase).
    """
    has_ar = bool(_ARABIC_RE.search(text or ""))
    has_en = bool(_LATIN_RE.search(text or ""))
    if has_ar and has_en: return "mixed"
    if has_ar:            return "ar"
    if has_en:            return "en"
    return "none"


def extract_campaign_language(campaign_name: str) -> str | None:
    """Pulls `_AR_` / `_EN_` from a campaign name. Returns 'ar' / 'en' / None.
    Matches the naming convention `{Channel}_{Type}_{Language}_{Product}_{Audience}`.
    """
    name = (campaign_name or "").upper()
    if "_AR_" in f"_{name}_" or name.endswith("_AR") or name.startswith("AR_"):
        return "ar"
    if "_EN_" in f"_{name}_" or name.endswith("_EN") or name.startswith("EN_"):
        return "en"
    return None


def is_language_mismatch(term: str, campaign_name: str) -> bool:
    """True if the keyword/search-term language doesn't match the campaign's
    declared language. Mixed-script terms are tolerated (transliterated brand
    inside an Arabic phrase is common). Campaigns without a clear `_AR_`/`_EN_`
    token are skipped (no false positives).
    """
    term_lang = detect_text_language(term)
    camp_lang = extract_campaign_language(campaign_name)
    if camp_lang is None or term_lang in ("none", "mixed"):
        return False
    return term_lang != camp_lang


# ── Top-level classifier ──────────────────────────────────────────────────────

def classify_term(term: str, campaign_name: str) -> str:
    """
    Returns one of:
      - "always_negative"           → execute as negative immediately (no approval)
      - "brand_only_block"          → قيود/qoyod term in non-brand campaign — drop
      - "brand_allowed"             → قيود/qoyod in a Brand campaign — allow
      - "competitor_in_competitor"  → competitor term in a Competitor campaign — IGNORE
      - "competitor_in_generic"     → competitor term in any other campaign — pause-watch
      - "language_mismatch"         → language doesn't match campaign — pause-watch
      - "normal"                    → no policy match; route by performance

    Precedence: ALWAYS_NEGATIVE wins over everything (login intent in Brand
    campaign is still login intent). Competitor wins over language. Language
    mismatch is a fallback flag for otherwise-normal terms.
    """
    if matches_any(term, ALWAYS_NEGATIVE_PATTERNS):
        return "always_negative"

    # Brand-only check (with accounting-noun exception)
    if matches_any(term, BRAND_ONLY_PATTERNS):
        if matches_any(term, QIYUD_FEATURE_MODIFIERS):
            pass  # fall through to language / normal
        else:
            return "brand_allowed" if is_brand_campaign(campaign_name) else "brand_only_block"

    # Competitor: only valid in a Competitor campaign
    if matches_any(term, COMPETITOR_PATTERNS):
        if is_competitor_campaign(campaign_name):
            return "competitor_in_competitor"
        return "competitor_in_generic"

    # Language match (last — lowest priority)
    if is_language_mismatch(term, campaign_name):
        return "language_mismatch"

    return "normal"


# ── Age guard ─────────────────────────────────────────────────────────────────
# A non-converting keyword must be active for ≥ MIN_KEYWORD_AGE_DAYS before
# being eligible for performance-based pause/delete (Rule A in config:
# spend>$80 0-conv, OR QS<5 + lost-IS>80%). Always-negative policy violations
# (login / دورة / تحميل / etc.) are paused immediately regardless of age —
# those should never be a keyword at any age.

def keyword_first_impression_dates(client, customer_id: str,
                                    criterion_resources: list[str]
                                    ) -> dict[str, str]:
    """
    For each criterion resource, returns the first segments.date with
    impressions > 0 in the past 365 days (or '' if never impressed).

    Used as a proxy for "active since" — Google Ads doesn't expose criterion
    creation date in v23 directly, but first impression is a tighter signal
    (a keyword that's been added but never served traffic isn't really old).
    """
    if not criterion_resources:
        return {}
    ga = client.get_service("GoogleAdsService")
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=365)

    # Extract criterion_ids from resource names like
    # "customers/{cid}/adGroupCriteria/{ag_id}~{criterion_id}"
    crit_ids = []
    for rn in criterion_resources:
        try:
            crit_ids.append(rn.rsplit("~", 1)[1])
        except Exception:
            continue
    if not crit_ids:
        return {}

    ids_clause = ", ".join(crit_ids)
    q = f"""
      SELECT
        ad_group_criterion.resource_name,
        ad_group_criterion.criterion_id,
        segments.date
      FROM keyword_view
      WHERE segments.date BETWEEN '{start}' AND '{end}'
        AND ad_group_criterion.criterion_id IN ({ids_clause})
        AND metrics.impressions > 0
      ORDER BY segments.date
    """
    first: dict[str, str] = {}
    try:
        for r in ga.search(customer_id=customer_id, query=q):
            rn = r.ad_group_criterion.resource_name
            if rn not in first:   # ORDER BY date ASC, take first
                first[rn] = r.segments.date
    except Exception as e:
        print(f"[age-helper] first-impression query failed for {customer_id}: {e}")
    return first


def days_since(yyyy_mm_dd: str | None) -> int:
    """Days between yyyy-mm-dd and today. Returns 0 if missing/never."""
    if not yyyy_mm_dd:
        return 0
    from datetime import date, datetime
    try:
        d = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return 0


# ── Backwards-compat shim ─────────────────────────────────────────────────────
# Old name used elsewhere in the codebase. Keep importable.
NEVER_NEGATIVE_PATTERNS = COMPETITOR_PATTERNS
