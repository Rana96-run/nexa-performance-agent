"""
Active Ads Preview
──────────────────
Shows currently ACTIVE ads on social channels with:
  • Ad preview (iframe for Meta, thumbnail for Snap/TikTok/LinkedIn)
  • Performance stats from BQ (Spend, Leads, SQLs, CPL, CPQL) — last 14 days
  • CPL / CPQL zone color indicators
  • Filter by channel and campaign
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from datetime import date, timedelta
from bq import query, fq

st.set_page_config(page_title="Active Ads Preview", page_icon="🎨", layout="wide")
st.title("🎨 Active Ads Preview")
st.caption("Live ads from social platforms · Performance stats from BQ (last 14 days)")

DAYS = 14

# ── Zone helpers ───────────────────────────────────────────────────────────────
def _cpl_color(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "#888"
    v = float(v)
    if v < 20:  return "#28A745"
    if v < 28:  return "#FFC107"
    if v < 30:  return "#FF8C00"
    return "#DC3545"

def _cpql_color(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "#888"
    v = float(v)
    if v < 40:  return "#28A745"
    if v < 65:  return "#FFC107"
    if v < 80:  return "#FF8C00"
    return "#DC3545"

def _fmt(v, prefix="$"):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "—"
    return f"{prefix}{float(v):,.2f}" if prefix else f"{float(v):,.0f}"


# ── BQ: pull performance for active ads (last 14 days) ───────────────────────
@st.cache_data(ttl=3600)
def _bq_ad_perf(channel: str) -> pd.DataFrame:
    sql = f"""
    SELECT
      utm_content                                                              AS ad_name,
      utm_campaign                                                             AS campaign,
      utm_audience                                                             AS ad_set,
      ROUND(SUM(spend), 2)                                                    AS spend,
      SUM(leads)                                                               AS leads,
      SUM(leads_qualified)                                                     AS sqls,
      ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),0)), 2)                 AS cpl,
      ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 2)       AS cpql,
      ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1)  AS qual_pct
    FROM {fq("v_ad_performance")}
    WHERE channel = '{channel}'
      AND date >= DATE_SUB(CURRENT_DATE(), INTERVAL {DAYS} DAY)
      AND utm_content IS NOT NULL AND utm_content != ''
    GROUP BY 1, 2, 3
    ORDER BY spend DESC
    """
    try:
        return query(sql)
    except Exception:
        return pd.DataFrame()


# ── Meta: fetch active ads with creative thumbnails ───────────────────────────
@st.cache_data(ttl=900)
def _meta_active_ads() -> list[dict]:
    token    = os.getenv("META_ACCESS_TOKEN", "")
    acct_ids = os.getenv("META_ACCOUNT_IDS", "")
    if not token or not acct_ids:
        return []

    ads = []
    for raw_acct in acct_ids.split(","):
        acct = raw_acct.strip()
        if not acct.startswith("act_"):
            acct = f"act_{acct}"
        try:
            url = f"https://graph.facebook.com/v19.0/{acct}/ads"
            params = {
                "access_token": token,
                "effective_status": '["ACTIVE"]',
                "fields": (
                    "id,name,campaign_id,adset_id,"
                    "creative{id,thumbnail_url,image_url,title,body},"
                    "adset{name},campaign{name}"
                ),
                "limit": 50,
            }
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            for ad in resp.json().get("data", []):
                creative = ad.get("creative") or {}
                ads.append({
                    "channel":    "meta",
                    "ad_id":      ad.get("id"),
                    "ad_name":    ad.get("name", ""),
                    "campaign":   (ad.get("campaign") or {}).get("name", ""),
                    "ad_set":     (ad.get("adset") or {}).get("name", ""),
                    "creative_id": creative.get("id"),
                    "thumbnail":  creative.get("thumbnail_url") or creative.get("image_url"),
                    "title":      creative.get("title", ""),
                    "body":       creative.get("body", ""),
                })
        except Exception as e:
            st.warning(f"Meta API error ({acct}): {e}")
    return ads


@st.cache_data(ttl=1800)
def _meta_ad_preview_html(creative_id: str) -> str | None:
    """Fetch the actual rendered ad HTML from Meta's adpreviews endpoint."""
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not token or not creative_id:
        return None
    try:
        url = f"https://graph.facebook.com/v19.0/{creative_id}/previews"
        params = {
            "access_token": token,
            "ad_format": "DESKTOP_FEED_STANDARD",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            return data[0].get("body", "")
    except Exception:
        pass
    return None


# ── Snapchat: fetch active ads ────────────────────────────────────────────────
@st.cache_data(ttl=900)
def _snap_active_ads() -> list[dict]:
    token  = os.getenv("SNAPCHAT_ACCESS_TOKEN", "")
    org_id = os.getenv("SNAPCHAT_ORGANIZATION_ID", "")
    if not token or not org_id:
        return []
    ads = []
    try:
        # Get ad accounts
        r = requests.get(
            f"https://adsapi.snapchat.com/v1/organizations/{org_id}/adaccounts",
            headers={"Authorization": f"Bearer {token}"}, timeout=15,
        )
        r.raise_for_status()
        for acct in r.json().get("adaccounts", []):
            acct_id = acct["adaccount"]["id"]
            # Get active ads
            r2 = requests.get(
                f"https://adsapi.snapchat.com/v1/adaccounts/{acct_id}/ads",
                headers={"Authorization": f"Bearer {token}"},
                params={"status": "ACTIVE"}, timeout=15,
            )
            r2.raise_for_status()
            for item in r2.json().get("ads", []):
                ad = item.get("ad", {})
                ads.append({
                    "channel":   "snapchat",
                    "ad_id":     ad.get("id"),
                    "ad_name":   ad.get("name", ""),
                    "campaign":  ad.get("campaign_id", ""),
                    "ad_set":    ad.get("ad_squad_id", ""),
                    "thumbnail": None,  # Snap requires separate creative fetch
                })
    except Exception as e:
        st.warning(f"Snapchat API error: {e}")
    return ads


# ── TikTok: fetch active ads ─────────────────────────────────────────────────
@st.cache_data(ttl=900)
def _tiktok_active_ads() -> list[dict]:
    token   = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    adv_ids = os.getenv("TIKTOK_ADVERTISER_IDS", "")
    if not token or not adv_ids:
        return []
    ads = []
    for adv_id in adv_ids.split(","):
        adv_id = adv_id.strip()
        try:
            resp = requests.get(
                "https://business-api.tiktok.com/open_api/v1.3/ad/get/",
                headers={"Access-Token": token},
                params={
                    "advertiser_id": adv_id,
                    "page_size": 50,
                    "fields": '["ad_id","ad_name","campaign_id","adgroup_id","image_ids","video_id","status","preview_url"]',
                },
                timeout=15,
            )
            resp.raise_for_status()
            for ad in resp.json().get("data", {}).get("list", []):
                if ad.get("status") != "ACTIVE":
                    continue
                ads.append({
                    "channel":    "tiktok",
                    "ad_id":      str(ad.get("ad_id", "")),
                    "ad_name":    ad.get("ad_name", ""),
                    "campaign":   str(ad.get("campaign_id", "")),
                    "ad_set":     str(ad.get("adgroup_id", "")),
                    "thumbnail":  None,
                    "preview_url": ad.get("preview_url"),
                })
        except Exception as e:
            st.warning(f"TikTok API error ({adv_id}): {e}")
    return ads


# ── Ad card renderer ──────────────────────────────────────────────────────────
def _render_ad_card(ad: dict, perf: dict | None):
    """Render a single ad as a styled card with preview + performance."""
    spend  = perf.get("spend")  if perf else None
    leads  = perf.get("leads")  if perf else None
    sqls   = perf.get("sqls")   if perf else None
    cpl    = perf.get("cpl")    if perf else None
    cpql   = perf.get("cpql")   if perf else None
    qpct   = perf.get("qual_pct") if perf else None

    cpl_c  = _cpl_color(cpl)
    cpql_c = _cpql_color(cpql)

    with st.container():
        col_preview, col_stats = st.columns([1, 2])

        with col_preview:
            channel = ad.get("channel", "")

            # Meta: try to show actual rendered preview iframe
            if channel == "meta" and ad.get("creative_id"):
                preview_html = _meta_ad_preview_html(ad["creative_id"])
                if preview_html:
                    components.html(preview_html, height=400, scrolling=False)
                elif ad.get("thumbnail"):
                    st.image(ad["thumbnail"], use_container_width=True)
                else:
                    st.markdown("_No preview available_")

            # Snap / TikTok / LinkedIn: thumbnail or preview URL
            elif ad.get("preview_url"):
                components.html(
                    f'<iframe src="{ad["preview_url"]}" width="100%" height="400" '
                    f'frameborder="0" allow="autoplay"></iframe>',
                    height=420,
                )
            elif ad.get("thumbnail"):
                st.image(ad["thumbnail"], use_container_width=True)
            else:
                icon = {"meta": "📘", "snapchat": "👻", "tiktok": "🎵", "linkedin": "💼"}.get(channel, "🖼")
                st.markdown(
                    f"""<div style="
                        background:#f0f2f6; border-radius:8px; padding:40px;
                        text-align:center; font-size:48px;
                        color:#888; min-height:180px; display:flex;
                        align-items:center; justify-content:center;">
                        {icon}
                    </div>""",
                    unsafe_allow_html=True,
                )

        with col_stats:
            ch_label = {
                "meta": "Meta Ads", "snapchat": "Snapchat Ads",
                "tiktok": "TikTok Ads", "linkedin": "LinkedIn Ads",
            }.get(ad.get("channel", ""), ad.get("channel", ""))

            st.markdown(f"**{ad.get('ad_name', '—')}**")
            st.caption(f"{ch_label} · {ad.get('campaign', '—')} · {ad.get('ad_set', '—')}")

            if perf:
                m1, m2, m3 = st.columns(3)
                m1.metric("Spend", _fmt(spend))
                m2.metric("Leads", _fmt(leads, prefix=""))
                m3.metric("SQLs",  _fmt(sqls,  prefix=""))

                m4, m5, m6 = st.columns(3)
                m4.metric("CPL",    _fmt(cpl),  help="Cost per Lead")
                m5.metric("CPQL",   _fmt(cpql), help="Cost per Qualified Lead")
                m6.metric("Qual%",  f"{qpct:.0f}%" if qpct is not None else "—")

                # Zone bar
                st.markdown(
                    f"""<div style="display:flex;gap:8px;margin-top:4px;">
                        <span style="background:{cpl_c};color:#fff;border-radius:4px;
                            padding:2px 10px;font-size:12px;font-weight:600;">
                            CPL {_fmt(cpl)}
                        </span>
                        <span style="background:{cpql_c};color:#fff;border-radius:4px;
                            padding:2px 10px;font-size:12px;font-weight:600;">
                            CPQL {_fmt(cpql)}
                        </span>
                    </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("_No BQ performance data for this creative (last 14d)_")

        st.divider()


# ── Channel selector ──────────────────────────────────────────────────────────
CHANNELS = {
    "Meta Ads":      ("meta",     _meta_active_ads),
    "Snapchat Ads":  ("snapchat", _snap_active_ads),
    "TikTok Ads":    ("tiktok",   _tiktok_active_ads),
}

sel = st.selectbox("Channel", list(CHANNELS.keys()))
channel_slug, fetch_fn = CHANNELS[sel]

# ── Load ads from platform API ────────────────────────────────────────────────
with st.spinner(f"Loading active {sel} ads…"):
    live_ads = fetch_fn()

if not live_ads:
    st.warning(
        f"No active ads found for {sel}. "
        "Check that the platform token is set in Railway environment variables."
    )
    st.stop()

# ── Load BQ performance ───────────────────────────────────────────────────────
df_perf = _bq_ad_perf(channel_slug)
perf_map: dict[str, dict] = {}
if not df_perf.empty:
    for _, row in df_perf.iterrows():
        key = (str(row.get("ad_name", "")).strip().lower())
        perf_map[key] = row.to_dict()

# ── Campaign filter ───────────────────────────────────────────────────────────
campaigns = sorted({a.get("campaign", "") for a in live_ads if a.get("campaign")})
sel_camp = st.multiselect("Filter by Campaign", campaigns, default=campaigns)
filtered_ads = [a for a in live_ads if a.get("campaign", "") in sel_camp]

st.markdown(f"**{len(filtered_ads)} active ad(s)** — performance stats from last {DAYS} days")
st.divider()

# ── Render each ad ────────────────────────────────────────────────────────────
for ad in filtered_ads:
    ad_key = ad.get("ad_name", "").strip().lower()
    perf   = perf_map.get(ad_key)
    _render_ad_card(ad, perf)
