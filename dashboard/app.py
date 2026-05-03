"""
Qoyod Performance Agent — Dashboard Landing Page

Shows blended KPI overview cards for the last 7 days and
provides a cache-clear button so analysts can force a data refresh.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from bq import query, fq
import pandas as pd

st.set_page_config(
    page_title="Qoyod Performance Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("Qoyod Performance Dashboard")
st.caption("Powered by Google BigQuery · Data refreshes every 6 hours · UI cache: 1 hour")

# ── Cache control ──────────────────────────────────────────────────────────────
col_btn, col_ts = st.columns([1, 5])
with col_btn:
    if st.button("Force Refresh Cache"):
        st.cache_data.clear()
        st.success("Cache cleared — next query will fetch fresh data.")

# ── 7-day blended KPI cards ────────────────────────────────────────────────────
st.subheader("Last 7 Days — Blended KPIs")

SQL_7D = f"""
SELECT
  COALESCE(SUM(spend), 0)                                        AS total_spend,
  COALESCE(SUM(leads), 0)                                        AS total_leads,
  COALESCE(SUM(leads_qualified), 0)                              AS total_sqls,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0))                 AS blended_cpl,
  SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified), 0))       AS blended_cpql,
  SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads), 0)) * 100 AS qual_pct
FROM {fq("utm_paid_attribution_daily")}
WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
                AND DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  AND utm_campaign != '__no_utm__'
"""

try:
    df = query(SQL_7D)
    row = df.iloc[0] if not df.empty else {}

    def _fmt_currency(v):
        if v is None or (hasattr(v, "__float__") and pd.isna(float(v))):
            return "—"
        return f"${float(v):,.2f}"

    def _fmt_int(v):
        if v is None or (hasattr(v, "__float__") and pd.isna(float(v))):
            return "—"
        return f"{int(v):,}"

    def _fmt_pct(v):
        if v is None or (hasattr(v, "__float__") and pd.isna(float(v))):
            return "—"
        return f"{float(v):.1f}%"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Spend (USD)",  _fmt_currency(row.get("total_spend")))
    c2.metric("Total Leads",        _fmt_int(row.get("total_leads")))
    c3.metric("Total SQLs",         _fmt_int(row.get("total_sqls")))
    c4.metric("Blended CPL",        _fmt_currency(row.get("blended_cpl")))
    c5.metric("Blended CPQL",       _fmt_currency(row.get("blended_cpql")))
    c6.metric("Qual Rate",          _fmt_pct(row.get("qual_pct")))

except Exception as e:
    st.warning(f"Could not load blended KPIs: {e}")

# ── Channel snapshot ───────────────────────────────────────────────────────────
st.subheader("Last 7 Days — Channel Snapshot")

SQL_CHANNELS = f"""
SELECT
  channel_name,
  ROUND(SUM(spend), 2)                                           AS spend,
  SUM(leads)                                                     AS leads,
  SUM(leads_qualified)                                           AS sqls,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads), 0)), 2)      AS CPL,
  ROUND(SAFE_DIVIDE(SUM(spend), NULLIF(SUM(leads_qualified),0)),2) AS CPQL,
  ROUND(SAFE_DIVIDE(SUM(leads_qualified), NULLIF(SUM(leads),0))*100, 1) AS qual_pct
FROM {fq("utm_paid_attribution_daily")}
WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
                AND DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  AND utm_campaign != '__no_utm__'
GROUP BY 1
ORDER BY spend DESC
"""

try:
    df_ch = query(SQL_CHANNELS)
    if df_ch.empty:
        st.info("No channel data found for the last 7 days.")
    else:
        st.dataframe(df_ch, use_container_width=True, hide_index=True)
except Exception as e:
    st.warning(f"Could not load channel snapshot: {e}")

# ── Navigation hint ────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
**Pages available in the sidebar:**

📊 **Overview**
- **1 · Paid Overview** — channel scorecards, campaign leaderboard, spend vs leads trend
- **2 · Organic Overview** — organic leads by source, funnel, top content

📡 **Channel Deep Dives** — each has: Summary · Campaigns · Ad Groups/Sets · Ads/Creatives (+ Keywords for Google)
- **3 · Google Ads** 🔵
- **4 · Meta Ads** 🟦
- **5 · Snapchat Ads** 🟡
- **6 · TikTok Ads** ⬛
- **7 · LinkedIn Ads** 🔷
- **8 · Microsoft Ads** 🟩

🔬 **Analysis**
- **9 · Leads Funnel** — qualification funnel, disqual reasons, pipeline split
- **10 · Insights & Recommendations** — automated pause / scale / optimize signals

🎨 **Creative**
- **11 · Active Ads Preview** — live ads with rendered previews (Meta iframe / Snap / TikTok) + 14-day CPL/CPQL per ad
""")
