"""
Paid Channel Overview
─────────────────────
Hero KPIs · Channel scorecard · Spend vs Leads time series · Campaign leaderboard
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
from bq import query, fq

st.set_page_config(page_title="Paid Overview", page_icon="💰", layout="wide")
st.title("Paid Channel Overview")

# ── CPL / CPQL zone helpers ────────────────────────────────────────────────────
def cpl_emoji(v):
    if v is None or pd.isna(v):
        return "⚪"
    if v < 20:   return "🟢"
    if v < 28:   return "🟡"
    if v < 30:   return "🟠"
    return "🔴"

def cpql_emoji(v):
    if v is None or pd.isna(v):
        return "⚪"
    if v < 40:   return "🟢"
    if v < 65:   return "🟡"
    if v < 80:   return "🟠"
    return "🔴"

def fmt_usd(v):
    if v is None or pd.isna(v):
        return "—"
    return f"${float(v):,.2f}"

def fmt_int(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{int(v):,}"

def fmt_pct(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{float(v)*100:.1f}%"

# ── Filters ────────────────────────────────────────────────────────────────────
PAID_CHANNELS = [
    "Google Ads", "Meta Ads", "Snapchat Ads",
    "TikTok Ads", "LinkedIn Ads", "Microsoft Ads",
]

col1, col2, col3 = st.columns([2, 2, 4])
with col1:
    start_date = st.date_input("From", value=date.today() - timedelta(days=30))
with col2:
    end_date   = st.date_input("To",   value=date.today() - timedelta(days=1))
with col3:
    sel_channels = st.multiselect(
        "Channels", PAID_CHANNELS, default=PAID_CHANNELS
    )

if not sel_channels:
    st.warning("Select at least one channel.")
    st.stop()

channels_sql = ", ".join(f"'{c}'" for c in sel_channels)

# ── Hero metrics ───────────────────────────────────────────────────────────────
SQL_HERO = f"""
SELECT
  COALESCE(SUM(spend), 0)                                        AS total_spend,
  COALESCE(SUM(leads), 0)                                        AS total_leads,
  COALESCE(SUM(leads_qualified), 0)                              AS total_sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0))                 AS blended_cpl,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0))       AS blended_cpql,
  SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads), 0))       AS qual_rate
FROM {fq("utm_paid_attribution_daily")}
WHERE date BETWEEN '{start_date}' AND '{end_date}'
  AND channel_name IN ({channels_sql})
  AND utm_campaign != '__no_utm__'
"""

try:
    df_hero = query(SQL_HERO)
    row = df_hero.iloc[0] if not df_hero.empty else {}
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Spend",    fmt_usd(row.get("total_spend")))
    c2.metric("Total Leads",    fmt_int(row.get("total_leads")))
    c3.metric("Total SQLs",     fmt_int(row.get("total_sqls")))
    c4.metric("Blended CPL",    fmt_usd(row.get("blended_cpl")))
    c5.metric("Blended CPQL",   fmt_usd(row.get("blended_cpql")))
    c6.metric("Qual Rate",      fmt_pct(row.get("qual_rate")))
except Exception as e:
    st.warning(f"Hero metrics unavailable: {e}")

st.divider()

# ── Channel scorecard ──────────────────────────────────────────────────────────
st.subheader("Channel Scorecard")

SQL_SCORECARD = f"""
SELECT
  channel_name                                                    AS Channel,
  ROUND(SUM(spend), 2)                                           AS Spend,
  SUM(leads)                                                     AS Leads,
  SUM(leads_qualified)                                           AS SQLs,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)), 2)      AS CPL,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)),2) AS CPQL,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1) AS Qual_Pct
FROM {fq("utm_paid_attribution_daily")}
WHERE date BETWEEN '{start_date}' AND '{end_date}'
  AND channel_name IN ({channels_sql})
  AND utm_campaign != '__no_utm__'
GROUP BY 1
ORDER BY Spend DESC
"""

try:
    df_sc = query(SQL_SCORECARD)
    if df_sc.empty:
        st.info("No data for selected filters.")
    else:
        df_sc["CPL Zone"]  = df_sc["CPL"].apply(cpl_emoji)
        df_sc["CPQL Zone"] = df_sc["CPQL"].apply(cpql_emoji)
        cols_order = ["Channel", "CPL Zone", "CPQL Zone", "Spend", "Leads", "SQLs", "CPL", "CPQL", "Qual_Pct"]
        st.dataframe(df_sc[cols_order], use_container_width=True, hide_index=True)
except Exception as e:
    st.warning(f"Scorecard unavailable: {e}")

st.divider()

# ── Spend vs Leads time series ─────────────────────────────────────────────────
st.subheader("Spend vs Leads Over Time")

SQL_TS = f"""
SELECT
  date,
  ROUND(SUM(spend), 2)  AS spend,
  SUM(leads)            AS leads
FROM {fq("utm_paid_attribution_daily")}
WHERE date BETWEEN '{start_date}' AND '{end_date}'
  AND channel_name IN ({channels_sql})
  AND utm_campaign != '__no_utm__'
GROUP BY 1
ORDER BY 1
"""

try:
    df_ts = query(SQL_TS)
    if df_ts.empty:
        st.info("No time-series data.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_ts["date"], y=df_ts["spend"],
            name="Spend (USD)", marker_color="#003DA5", yaxis="y1",
        ))
        fig.add_trace(go.Scatter(
            x=df_ts["date"], y=df_ts["leads"],
            name="Leads", mode="lines+markers",
            line=dict(color="#F5A623", width=2), yaxis="y2",
        ))
        fig.update_layout(
            yaxis=dict(title="Spend (USD)", side="left"),
            yaxis2=dict(title="Leads", side="right", overlaying="y"),
            legend=dict(x=0, y=1.1, orientation="h"),
            height=380,
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Time series unavailable: {e}")

st.divider()

# ── Campaign leaderboard ───────────────────────────────────────────────────────
st.subheader("Campaign Leaderboard (Top 10 by Spend)")

SQL_CAMP = f"""
SELECT
  channel_name                                                     AS Channel,
  utm_campaign                                                     AS Campaign,
  ROUND(SUM(spend), 2)                                            AS Spend,
  SUM(leads)                                                      AS Leads,
  SUM(leads_qualified)                                            AS SQLs,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)), 2)       AS CPL,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)),2) AS CPQL,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100,1) AS Qual_Pct,
  ANY_VALUE(match_method) AS Match
FROM {fq("utm_paid_attribution_daily")}
WHERE date BETWEEN '{start_date}' AND '{end_date}'
  AND channel_name IN ({channels_sql})
  AND utm_campaign != '__no_utm__'
GROUP BY 1, 2
ORDER BY Spend DESC
LIMIT 10
"""

try:
    df_camp = query(SQL_CAMP)
    if df_camp.empty:
        st.info("No campaign data.")
    else:
        df_camp["CPL Zone"]  = df_camp["CPL"].apply(cpl_emoji)
        df_camp["CPQL Zone"] = df_camp["CPQL"].apply(cpql_emoji)
        cols_order = ["Channel", "Campaign", "CPL Zone", "CPQL Zone",
                      "Spend", "Leads", "SQLs", "CPL", "CPQL", "Qual_Pct", "Match"]
        st.dataframe(df_camp[cols_order], use_container_width=True, hide_index=True)
except Exception as e:
    st.warning(f"Campaign leaderboard unavailable: {e}")
