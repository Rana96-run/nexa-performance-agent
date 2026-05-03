"""
Shared channel page builder.
Each channel page imports this and calls render_channel_page(channel_slug, channel_label).
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from bq import query, fq


# ── Zone helpers ──────────────────────────────────────────────────────────────
def _cpl_emoji(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "⚪"
    v = float(v)
    if v < 20:  return "🟢"
    if v < 28:  return "🟡"
    if v < 30:  return "🟠"
    return "🔴"

def _cpql_emoji(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "⚪"
    v = float(v)
    if v < 40:  return "🟢"
    if v < 65:  return "🟡"
    if v < 80:  return "🟠"
    return "🔴"

def _fmt_usd(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "—"
    return f"${float(v):,.2f}"

def _fmt_int(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "—"
    return f"{int(v):,}"

def _fmt_pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return "—"
    return f"{float(v):.1f}%"

def _zone_col(df, col, fn):
    """Insert a zone emoji column before col."""
    if col in df.columns:
        idx = df.columns.get_loc(col)
        df.insert(idx, f"{col} Zone", df[col].apply(fn))
    return df


def render_channel_page(channel_slug: str, channel_label: str, has_keywords: bool = False):
    """
    Render a full channel deep-dive page.
    channel_slug: 'google_ads' | 'meta' | 'snapchat' | 'tiktok' | 'linkedin' | 'microsoft_ads'
    channel_label: 'Google Ads' | 'Meta Ads' etc.
    has_keywords: True only for Google Ads
    """
    # ── Date filter ───────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("From", value=date.today() - timedelta(days=30),
                                   key=f"start_{channel_slug}")
    with c2:
        end_date = st.date_input("To", value=date.today() - timedelta(days=1),
                                 key=f"end_{channel_slug}")

    sd, ed = str(start_date), str(end_date)

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    SQL_SUMMARY = f"""
    SELECT
      ROUND(SUM(spend), 2)                                                  AS Spend,
      SUM(leads)                                                             AS Leads,
      SUM(leads_qualified)                                                   AS SQLs,
      SUM(leads_disqualified)                                                AS Disqualified,
      ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),0)), 2)               AS CPL,
      ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 2)     AS CPQL,
      ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1) AS Qual_Pct
    FROM {fq("utm_paid_attribution_daily")}
    WHERE channel = '{channel_slug}'
      AND date BETWEEN '{sd}' AND '{ed}'
      AND utm_campaign != '__no_utm__'
    """
    try:
        row = query(SQL_SUMMARY).iloc[0]
        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        m1.metric("Spend (USD)",   _fmt_usd(row.get("Spend")))
        m2.metric("Leads",         _fmt_int(row.get("Leads")))
        m3.metric("SQLs",          _fmt_int(row.get("SQLs")))
        m4.metric("Disqualified",  _fmt_int(row.get("Disqualified")))
        m5.metric("CPL",           _fmt_usd(row.get("CPL")))
        m6.metric("CPQL",          _fmt_usd(row.get("CPQL")))
        m7.metric("Qual%",         _fmt_pct(row.get("Qual_Pct")))
    except Exception as e:
        st.warning(f"Summary KPIs unavailable: {e}")

    st.divider()

    # ── Sub-tabs: Campaigns / Ad Groups / Ads / Keywords ─────────────────────
    tab_labels = ["📋 Campaigns", "🗂 Ad Groups / Ad Sets", "🎨 Ads / Creatives"]
    if has_keywords:
        tab_labels.append("🔑 Keywords")

    tabs = st.tabs(tab_labels)

    # ── TAB 1: Campaigns ─────────────────────────────────────────────────────
    with tabs[0]:
        SQL_CAMPS = f"""
        SELECT
          utm_campaign                                                              AS Campaign,
          ROUND(SUM(spend), 2)                                                     AS Spend,
          SUM(leads)                                                                AS Leads,
          SUM(leads_qualified)                                                      AS SQLs,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),0)), 2)                  AS CPL,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 2)        AS CPQL,
          ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1)   AS `Qual%`,
          COUNTIF(match_method = 'unattributed')                                   AS Unattr_Leads,
          ANY_VALUE(match_method)                                                   AS Match_Method
        FROM {fq("utm_paid_attribution_daily")}
        WHERE channel = '{channel_slug}'
          AND date BETWEEN '{sd}' AND '{ed}'
        GROUP BY 1
        ORDER BY Spend DESC
        """
        try:
            df = query(SQL_CAMPS)
            if df.empty:
                st.info("No campaign data for this period.")
            else:
                # Surface no-UTM row clearly
                df["Campaign"] = df["Campaign"].replace(
                    "__no_utm__", "⚠️ (no UTM — click-ID only)"
                )
                df = _zone_col(df, "CPL", _cpl_emoji)
                df = _zone_col(df, "CPQL", _cpql_emoji)
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Campaigns table error: {e}")

    # ── TAB 2: Ad Groups / Ad Sets ────────────────────────────────────────────
    with tabs[1]:
        adset_label = "Ad Group" if channel_slug in ("google_ads", "microsoft_ads") else "Ad Set"
        SQL_ADSETS = f"""
        SELECT
          utm_campaign                                                              AS Campaign,
          IFNULL(utm_audience, '(none)')                                           AS `{adset_label}`,
          ROUND(SUM(spend), 2)                                                     AS Spend,
          SUM(leads)                                                                AS Leads,
          SUM(leads_qualified)                                                      AS SQLs,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),0)), 2)                  AS CPL,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 2)        AS CPQL,
          ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1)   AS `Qual%`
        FROM {fq("v_adset_performance")}
        WHERE channel = '{channel_slug}'
          AND date BETWEEN '{sd}' AND '{ed}'
        GROUP BY 1, 2
        ORDER BY Spend DESC
        """
        try:
            df = query(SQL_ADSETS)
            if df.empty:
                st.info(f"No {adset_label.lower()} data. Make sure utm_audience is populated in HubSpot.")
            else:
                df = _zone_col(df, "CPL", _cpl_emoji)
                df = _zone_col(df, "CPQL", _cpql_emoji)
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"{adset_label} table error: {e}")

    # ── TAB 3: Ads / Creatives ────────────────────────────────────────────────
    with tabs[2]:
        SQL_ADS = f"""
        SELECT
          utm_campaign                                                              AS Campaign,
          IFNULL(utm_audience, '(none)')                                           AS Ad_Group_Set,
          IFNULL(utm_content, '(none)')                                            AS Ad_Creative,
          ROUND(SUM(spend), 2)                                                     AS Spend,
          SUM(leads)                                                                AS Leads,
          SUM(leads_qualified)                                                      AS SQLs,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),0)), 2)                  AS CPL,
          ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 2)        AS CPQL,
          ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1)   AS `Qual%`
        FROM {fq("v_ad_performance")}
        WHERE channel = '{channel_slug}'
          AND date BETWEEN '{sd}' AND '{ed}'
        GROUP BY 1, 2, 3
        ORDER BY Spend DESC
        """
        try:
            df = query(SQL_ADS)
            if df.empty:
                st.info("No ad/creative data. Make sure utm_content is populated in HubSpot.")
            else:
                df = _zone_col(df, "CPL", _cpl_emoji)
                df = _zone_col(df, "CPQL", _cpql_emoji)
                st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Ads table error: {e}")

    # ── TAB 4: Keywords (Google Ads only) ─────────────────────────────────────
    if has_keywords and len(tabs) > 3:
        with tabs[3]:
            SQL_KW = f"""
            SELECT
              utm_campaign                                                          AS Campaign,
              IFNULL(utm_term, '(none)')                                           AS Keyword,
              ROUND(SUM(spend), 2)                                                 AS Spend,
              SUM(leads)                                                            AS Leads,
              SUM(leads_qualified)                                                  AS SQLs,
              ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads),0)), 2)              AS CPL,
              ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)), 2)    AS CPQL,
              ANY_VALUE(match_method)                                               AS Match
            FROM {fq("v_keyword_performance")}
            WHERE channel = '{channel_slug}'
              AND date BETWEEN '{sd}' AND '{ed}'
            GROUP BY 1, 2
            ORDER BY Spend DESC
            """
            try:
                df = query(SQL_KW)
                if df.empty:
                    st.info("No keyword data. Make sure utm_term is populated in HubSpot.")
                else:
                    df = _zone_col(df, "CPL", _cpl_emoji)
                    df = _zone_col(df, "CPQL", _cpql_emoji)
                    st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.warning(f"Keywords table error: {e}")
