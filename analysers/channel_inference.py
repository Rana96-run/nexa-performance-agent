"""
analysers/channel_inference.py
==============================
Single source of truth for "what channel does this lead/deal belong to?"
when the explicit qoyod_source field is missing or set to 'Other'.

Used by the HubSpot leads + deals collectors at write time, by the reporter,
and by the spike detector.

────────────────────────────────────────────────────────────────────────────
HubSpot Lead-module -> Contact-module property sync (verified by Amar):

| Lead module property                          | Synced from Contact module |
|-----------------------------------------------|----------------------------|
| lead_original_traffic_source                  | hs_analytics_source        |
| lead_latest_traffic_source                    | hs_latest_source           |
| lead_original_traffic_source_drilldown_1      | hs_analytics_source_data_1 |
| lead_latest_traffic_source_drilldown_1        | hs_latest_source_data_1    |
| lead_original_traffic_source_drilldown_2      | hs_analytics_source_data_2 |
| lead_latest_traffic_source_drilldown_2        | hs_latest_source_data_2    |
| lead_utm_campaign  ≡ deal_utm_campaign ≡ campaign_name |              |

The two `*_traffic_source` properties hold HubSpot's high-level enum
(PAID_SEARCH / PAID_SOCIAL / ORGANIC_SEARCH / ...).  They give the *source
type*, NOT the campaign name.

The two `*_drilldown_1` properties usually hold the CAMPAIGN NAME — that's
where the keyword-pattern matching runs to disambiguate Google vs Microsoft,
Meta vs TikTok vs Snapchat vs LinkedIn.

The two `*_drilldown_2` properties may hold the utm_audience or another
campaign-name reference.

────────────────────────────────────────────────────────────────────────────
Resolver order (first hit wins):

  1. Explicit `qoyod_source` (HubSpot label like 'Google Ads')

  2. `lead_*_traffic_source` enum + drilldown disambiguation:
     - If PAID_SEARCH and drilldown_1 contains "bing" -> microsoft_ads
       else -> google_ads
     - If PAID_SOCIAL -> check drilldown_1 keywords
       (meta / tiktok / snapchat / linkedin)
     - If ORGANIC_SEARCH or drilldown_1 == "Unknown keywords (SSL)"
       -> organic_search
     - If ORGANIC_SOCIAL -> organic_social
     - If DIRECT_TRAFFIC -> direct
     - etc.

  3. Keyword pattern match against `lead_utm_campaign`

  4. Keyword pattern match against `lead_utm_audience`,
     `lead_utm_content`, `lead_utm_medium` (last-resort signals)

  5. Keyword pattern match against `*_drilldown_1` and `*_drilldown_2`
     in case the campaign name lives there

  6. None of the above -> returns None.  Collector buckets it as 'Other'
     (HubSpot's own classification) — NEVER silently as another channel.
────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Optional

# ─── Channel keyword rules ────────────────────────────────────────────────────
# Order matters: more specific keywords first (e.g. 'bing' must beat 'search').
CAMPAIGN_NAME_PATTERNS: list[tuple[str, list[str]]] = [
    # Qoyod-specific organic naming conventions (highest priority)
    ("organic_social",  ["auto_social"]),
    ("organic_search",  ["auto_organic"]),

    # Microsoft (Bing) — same naming structure as Google but with bing prefix
    # Example: 'search_ar_brand' = Google Ads,
    #          'bing_search_ar_brand' = Microsoft Ads
    ("microsoft_ads",   ["bing"]),

    # Other paid platforms (single-word match)
    ("meta",            ["meta", "facebook", "instagram"]),
    ("tiktok",          ["tiktok"]),
    ("snapchat",        ["snapchat", "snap"]),
    ("linkedin",        ["linkedin"]),
    ("youtube",         ["youtube"]),

    # Google Ads — broadest match goes last
    ("google_ads",      ["google", "search", "impressionshare",
                         "demandgen", "websitetraffic"]),
]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def channel_from_keywords(*candidates: str) -> Optional[str]:
    """
    Return the first channel slug whose keyword appears in any candidate
    string.  Used to scan multiple text fields (campaign name, audience,
    content, drilldowns) in one pass.
    """
    blob = " ".join(_norm(c) for c in candidates if c)
    if not blob:
        return None
    for channel_slug, keywords in CAMPAIGN_NAME_PATTERNS:
        for kw in keywords:
            if kw in blob:
                return channel_slug
    return None


# Back-compat alias (older code calls channel_from_campaign_name)
def channel_from_campaign_name(campaign_name: str) -> Optional[str]:
    return channel_from_keywords(campaign_name)


# ─── HubSpot qoyod_source label ↔ channel slug ────────────────────────────────
QOYOD_SOURCE_TO_CHANNEL: dict[str, str] = {
    # paid
    # Exact HubSpot lead_qoyod_source internal names — verified 2026-05-11
    # Source: HubSpot property editor → Lead → lead_qoyod_source dropdown
    # NEVER change these strings without updating them in HubSpot first.
    "Google Ads":    "google_ads",
    "Microsoft Ads": "microsoft_ads",
    "Meta Ads":      "meta",
    "Snapchat Ads":  "snapchat",
    "Tiktok Ads":    "tiktok",   # HubSpot internal name: lowercase 'i' (not TikTok)
    "LinkedIn Ads":  "linkedin",
    # organic / direct / other
    "Direct Traffic":  "direct",
    "Organic Search":  "organic_search",
    "Organic Social":  "organic_social",
    "Email Marketing": "email",
    "Offline":         "offline",
    "Other":           "other",
    "Referrals":       "referral",
}

CHANNEL_TO_QOYOD_SOURCE: dict[str, str] = {
    v: k for k, v in QOYOD_SOURCE_TO_CHANNEL.items()
}


def channel_from_qoyod_source(qoyod_source: str) -> Optional[str]:
    return QOYOD_SOURCE_TO_CHANNEL.get(qoyod_source) if qoyod_source else None


# ─── HubSpot traffic-source enum (lead_*_traffic_source) ──────────────────────
# These are the high-level SOURCE TYPE values, not channels.  We need to
# disambiguate paid_* with the drilldown.
HUBSPOT_TRAFFIC_SOURCE_ENUMS = {
    # The actual API values — uppercased
    "PAID_SEARCH":              "paid_search",      # Google or Microsoft
    "PAID_SOCIAL":              "paid_social",      # Meta, TikTok, Snap, LinkedIn
    "ORGANIC_SEARCH":           "organic_search",
    "ORGANIC_SOCIAL":           "organic_social",
    "DIRECT_TRAFFIC":           "direct",
    "REFERRALS":                "referral",
    "EMAIL_MARKETING":          "email",
    "OTHER_CAMPAIGNS":          "other",
    "OFFLINE":                  "offline",
}


def _normalise_enum(value: str) -> str:
    return (value or "").strip().upper().replace("-", "_").replace(" ", "_")


# Specific magic value HubSpot writes when a search keyword is hidden by
# SSL referrer stripping.  Means organic search (per Amar).
SSL_UNKNOWN_KEYWORDS = "Unknown keywords (SSL)"


# ─── The full fallback chain ─────────────────────────────────────────────────

def resolve_channel(
    *,
    qoyod_source: str = "",
    campaign_name: str = "",
    lead_utm_campaign: str = "",
    lead_utm_source: str = "",   # raw utm_source value (e.g. "tiktok", "meta")
    lead_original_traffic_source: str = "",
    lead_latest_traffic_source: str = "",
    lead_original_traffic_source_drilldown_1: str = "",
    lead_latest_traffic_source_drilldown_1: str = "",
    lead_original_traffic_source_drilldown_2: str = "",
    lead_latest_traffic_source_drilldown_2: str = "",
    lead_utm_audience: str = "",
    lead_utm_content: str = "",
    lead_utm_medium: str = "",
) -> Optional[str]:
    """
    Return our channel slug using the full fallback chain documented above.
    Returns None only if every signal is empty / unknown — caller should
    bucket as 'Other'.
    """
    # campaign_name and lead_utm_campaign are synonyms — accept either kwarg
    campaign_name = campaign_name or lead_utm_campaign

    # 1. Explicit qoyod_source label
    # "direct" is NOT treated as final here — a lead tagged Direct Traffic
    # in HubSpot may still have a paid original_traffic_source (e.g. PAID_SOCIAL).
    # We fall through to step 2 so the paid signal can override the direct tag.
    # All other explicit labels (Google Ads, Meta Ads, etc.) are trusted.
    ch = channel_from_qoyod_source(qoyod_source)
    if ch and ch not in ("other", "direct"):
        return ch

    # Pre-compute drilldown-blob for keyword detection
    drilldowns = (
        lead_original_traffic_source_drilldown_1,
        lead_latest_traffic_source_drilldown_1,
        lead_original_traffic_source_drilldown_2,
        lead_latest_traffic_source_drilldown_2,
    )

    # 2. HubSpot traffic-source enum + drilldown disambiguation
    for src_value in (lead_original_traffic_source, lead_latest_traffic_source):
        norm = _normalise_enum(src_value)
        bucket = HUBSPOT_TRAFFIC_SOURCE_ENUMS.get(norm)
        if not bucket:
            continue

        if bucket == "paid_search":
            # 'bing' in any drilldown -> Microsoft Ads, otherwise Google Ads
            if any("bing" in _norm(d) for d in drilldowns):
                return "microsoft_ads"
            return "google_ads"

        if bucket == "paid_social":
            # Check utm_source first (raw value like "tiktok"), then campaign
            # name, then creative fields, then drilldowns.
            ch_kw = channel_from_keywords(
                lead_utm_source,
                campaign_name,
                lead_utm_content,
                lead_utm_audience, lead_utm_medium,
                *drilldowns,
            )
            if ch_kw in ("meta", "tiktok", "snapchat", "linkedin"):
                return ch_kw
            return "meta"  # Most paid_social is Meta in this account

        if bucket == "organic_search":
            return "organic_search"
        if bucket == "organic_social":
            return "organic_social"
        if bucket == "direct":
            return "direct"
        if bucket == "referral":
            return "referral"
        if bucket == "email":
            return "email"
        if bucket == "offline":
            return "offline"

    # 2b. Special: drilldown_1 == "Unknown keywords (SSL)" -> organic search
    for d in drilldowns[:2]:  # only the _data_1 drilldowns carry this signal
        if d and d.strip() == SSL_UNKNOWN_KEYWORDS:
            return "organic_search"

    # 3-5. Keyword pattern match across every text signal we have.
    # Priority order (documented in module header):
    #   a. utm_source (raw value — e.g. "tiktok", "meta")
    #   b. utm_campaign / campaign_name (naming convention includes channel)
    #   c. utm_content (creative naming often includes channel)
    #   d. utm_audience, utm_medium (lower-confidence signals)
    #   e. HubSpot drilldown_1 / drilldown_2 (last resort)
    ch = channel_from_keywords(
        lead_utm_source,
        campaign_name,
        lead_utm_content,
        lead_utm_audience, lead_utm_medium,
        *drilldowns,
    )
    return ch
