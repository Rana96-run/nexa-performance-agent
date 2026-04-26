"""
analysers/channel_inference.py
==============================
Single source of truth for "what channel does this lead/deal belong to?"
when the explicit qoyod_source field is missing or set to 'none'.

Used as a fallback chain by the reporter, the spike detector, and the
attribution joins so we never lose a lead just because a UTM was dropped.

Lookup priority (first hit wins):
    1. Explicit qoyod_source from HubSpot Lead module        ('Google Ads', 'Meta Ads', ...)
    2. Property: lead_original_traffic_source                 (HubSpot original source)
    3. Property: lead_latest_traffic_source                   (HubSpot latest source)
    4. Pattern match on lead_utm_campaign (= deal_utm_campaign = campaign_name)
        → see CAMPAIGN_NAME_PATTERNS below

Confirmed by Amar (2026-04-26):
    campaign_name == utm_campaign == lead_utm_campaign == deal_utm_campaign
    (HubSpot syncs all four from the original platform property)
"""
from __future__ import annotations

import re
from typing import Optional

# ─── Campaign-name → channel rules ────────────────────────────────────────────
# Order matters: more specific keywords first (e.g. "bing_search_*" must match
# 'microsoft_ads' before the generic 'search' keyword bumps it to 'google_ads').
CAMPAIGN_NAME_PATTERNS: list[tuple[str, list[str]]] = [
    # auto_* prefixes are Qoyod's own naming for non-paid sources
    ("organic_social",  ["auto_social"]),
    ("organic_search",  ["auto_organic"]),

    # Microsoft (Bing) — same naming structure as Google but with bing prefix.
    # Example: 'search_ar_brand' = Google Ads, 'bing_search_ar_brand' = Bing.
    ("microsoft_ads",   ["bing"]),

    # Meta / TikTok / Snapchat / LinkedIn — single-word match
    ("meta",            ["meta", "facebook", "instagram"]),
    ("tiktok",          ["tiktok"]),
    ("snapchat",        ["snapchat", "snap"]),
    ("linkedin",        ["linkedin"]),

    # YouTube is owned by Google but tracked separately when the campaign
    # name explicitly says youtube
    ("youtube",         ["youtube"]),

    # Google Ads — the broadest set goes last so more specific rules above win.
    # These keywords appear in Qoyod's Google Ads campaign naming convention.
    ("google_ads",      ["google", "search", "impressionshare",
                         "demandgen", "websitetraffic"]),
]


def _norm(s: str) -> str:
    """Lowercase and strip; preserves underscores for prefix matching."""
    return (s or "").strip().lower()


def channel_from_campaign_name(campaign_name: str) -> Optional[str]:
    """
    Return our channel slug ('google_ads', 'meta', ...) inferred from the
    campaign name. Returns None if no rule matches.
    """
    name = _norm(campaign_name)
    if not name:
        return None
    for channel_slug, keywords in CAMPAIGN_NAME_PATTERNS:
        for kw in keywords:
            # Match as a whole word OR substring — Qoyod's naming uses
            # underscores so we match 'bing_search' as 'bing'.
            if kw in name:
                return channel_slug
    return None


# ─── Mapping from HubSpot's qoyod_source label → our channel slug ────────────
# Verified live HubSpot values (Apr 2026).  These are the labels HubSpot
# writes for the qoyod_source property.
QOYOD_SOURCE_TO_CHANNEL: dict[str, str] = {
    # paid
    "Google Ads":    "google_ads",
    "Meta Ads":      "meta",
    "Snapchat Ads":  "snapchat",
    "Tiktok Ads":    "tiktok",
    "TikTok Ads":    "tiktok",     # capitalisation tolerant
    "LinkedIn Ads":  "linkedin",
    "Microsoft Ads": "microsoft_ads",

    # organic / direct / other
    "Direct Traffic":  "direct",
    "Organic Search":  "organic_search",
    "Email Marketing": "email",
    "Offline":         "offline",
    "Other":           "other",
}

# Inverse mapping for cross-table joins (channel slug → HubSpot label)
CHANNEL_TO_QOYOD_SOURCE: dict[str, str] = {
    v: k for k, v in QOYOD_SOURCE_TO_CHANNEL.items()
}


def channel_from_qoyod_source(qoyod_source: str) -> Optional[str]:
    """Map a HubSpot qoyod_source label to our channel slug."""
    if not qoyod_source:
        return None
    return QOYOD_SOURCE_TO_CHANNEL.get(qoyod_source)


# ─── HubSpot traffic-source property helpers ─────────────────────────────────
# When qoyod_source is missing/None, HubSpot keeps the raw traffic-source
# values in two enum properties.  They use HubSpot's internal labels.
HUBSPOT_TRAFFIC_SOURCE_TO_CHANNEL: dict[str, str] = {
    # Paid search → Google Ads (Microsoft Ads must be detected from the
    # campaign name, not from this property).
    "PAID_SEARCH":              "google_ads",
    "PAID_SOCIAL":              "meta",   # default; overridden by name match
    "ORGANIC_SEARCH":           "organic_search",
    "ORGANIC_SOCIAL":           "organic_social",
    "DIRECT_TRAFFIC":           "direct",
    "REFERRALS":                "referral",
    "EMAIL_MARKETING":          "email",
    "OTHER_CAMPAIGNS":          "other",
    "OFFLINE":                  "offline",
    # Some accounts use lowercase / dashed variants — normalise on read
}


def channel_from_hubspot_traffic_source(value: str) -> Optional[str]:
    """Map HubSpot's enum value (e.g. 'PAID_SEARCH') to our channel slug."""
    if not value:
        return None
    key = value.strip().upper().replace("-", "_").replace(" ", "_")
    return HUBSPOT_TRAFFIC_SOURCE_TO_CHANNEL.get(key)


# ─── The full fallback chain ─────────────────────────────────────────────────

def resolve_channel(
    qoyod_source: str = "",
    campaign_name: str = "",
    lead_original_traffic_source: str = "",
    lead_latest_traffic_source: str = "",
) -> Optional[str]:
    """
    Return our channel slug using the full fallback chain.  Returns None
    only if every signal is empty / unknown.

    Use this from the reporter, spike detector, and any join code that
    needs to attribute a lead/deal to a channel.
    """
    # 1. Explicit qoyod_source label (the most authoritative signal)
    ch = channel_from_qoyod_source(qoyod_source)
    if ch:
        return ch

    # 2. HubSpot original traffic-source property
    ch = channel_from_hubspot_traffic_source(lead_original_traffic_source)
    # If it's a paid social value, the campaign name disambiguates the platform.
    if ch == "meta":
        ch_name = channel_from_campaign_name(campaign_name)
        if ch_name in ("meta", "tiktok", "snapchat", "linkedin"):
            return ch_name
        return "meta"
    if ch:
        # If paid search but campaign name says bing, override to Microsoft.
        if ch == "google_ads":
            ch_name = channel_from_campaign_name(campaign_name)
            if ch_name == "microsoft_ads":
                return "microsoft_ads"
        return ch

    # 3. HubSpot latest traffic-source property
    ch = channel_from_hubspot_traffic_source(lead_latest_traffic_source)
    if ch:
        return ch

    # 4. Pattern match on the campaign name itself
    ch = channel_from_campaign_name(campaign_name)
    return ch
