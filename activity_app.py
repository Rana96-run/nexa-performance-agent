"""
Nexa Agent Activity Dashboard
==============================
Standalone Streamlit app — separate from the paid channels dashboard.

Shows:
  Left  — Live activity timeline from BigQuery (agent_activity_log)
  Right — Clickable workflow cards with GraphViz diagrams

Start command (Railway service or local):
    streamlit run activity_app.py --server.port $PORT --server.address 0.0.0.0

Auto-refreshes every 5 minutes via st.rerun().
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import streamlit as st
import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows import WORKFLOWS

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Nexa Agent Activity",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

RIYADH = timezone(timedelta(hours=3))

# ── Status display helpers ────────────────────────────────────────────────────
STATUS_EMOJI = {
    "success":          "✅",
    "failed":           "❌",
    "pending_approval": "⏳",
    "approved":         "✅",
    "rejected":         "🚫",
    "skipped":          "⏭️",
}

ROLE_COLORS = {
    "daily_digest":      "#7c3aed",
    "bq_refresh":        "#0ea5e9",
    "pause_watcher":     "#ef4444",
    "junk_leads":        "#f59e0b",
    "slack_approvals":   "#10b981",
    "airbyte_normalizer":"#3b82f6",
    "campaign_creator":  "#8b5cf6",
    "asana_creator":     "#f97316",
}


# ── BQ data loaders ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_activity(hours: int = 24) -> pd.DataFrame:
    try:
        from collectors.bq_writer import get_client
        project = os.getenv("BQ_PROJECT_ID")
        dataset = os.getenv("BQ_DATASET", "qoyod_marketing")
        client  = get_client()
        sql = f"""
            SELECT ts, role, action, status,
                   channel, campaign_name, details,
                   rows_affected, duration_s, session_id
            FROM `{project}.{dataset}.agent_activity_log`
            WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
            ORDER BY ts DESC
            LIMIT 500
        """
        df = client.query(sql).to_dataframe()
        if df.empty:
            return pd.DataFrame()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df["ts_riyadh"] = df["ts"].dt.tz_convert(RIYADH)
        return df
    except Exception as e:
        st.warning(f"Could not load activity log: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_role_counts() -> dict:
    """Runs-per-role in the last 7 days (successes only)."""
    try:
        from collectors.bq_writer import get_client
        project = os.getenv("BQ_PROJECT_ID")
        dataset = os.getenv("BQ_DATASET", "qoyod_marketing")
        client  = get_client()
        sql = f"""
            SELECT role, COUNT(*) AS n
            FROM `{project}.{dataset}.agent_activity_log`
            WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 168 HOUR)
              AND status = 'success'
            GROUP BY role
        """
        df = client.query(sql).to_dataframe()
        return dict(zip(df["role"], df["n"])) if not df.empty else {}
    except Exception:
        return {}


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🤖 Nexa Agent Activity")
st.caption("Live log of everything the agent does · Workflows update automatically from code")

# Controls
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    hours_back = st.selectbox(
        "Show last",
        [6, 12, 24, 48, 168],
        index=2,
        format_func=lambda h: f"{h} hours" if h < 48 else f"{h // 24} days",
    )
with c2:
    role_opts = ["All roles"] + [f"{w['emoji']} {w['role']}" for w in WORKFLOWS]
    role_sel  = st.selectbox("Filter by role", role_opts)
    role_id   = None
    if role_sel != "All roles":
        label = role_sel.split(" ", 1)[1]   # strip emoji
        role_id = next((w["id"] for w in WORKFLOWS if w["role"] == label), None)
with c3:
    st.write("")
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
left, right = st.columns([5, 4], gap="large")

# ══════════════════════════════════════════════════════
# LEFT — Activity Timeline
# ══════════════════════════════════════════════════════
with left:
    st.subheader("Activity Timeline")

    df = load_activity(hours=hours_back)
    if role_id:
        df = df[df["role"] == role_id] if not df.empty else df

    if df.empty:
        st.info("No activity recorded yet. The agent will start logging on its next run.")
    else:
        # Summary row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total",    len(df))
        m2.metric("Success",  int((df["status"] == "success").sum()))
        m3.metric("Pending",  int(df["status"].str.startswith("pending").sum()))
        m4.metric("Failed",   int((df["status"] == "failed").sum()))

        st.divider()

        # Timeline — native st.dataframe with column config
        display = df[["ts_riyadh", "role", "action", "status", "channel",
                       "campaign_name", "rows_affected", "duration_s"]].copy()
        display.columns = ["Time (Riyadh)", "Role", "Action", "Status",
                           "Channel", "Campaign", "Rows", "Duration (s)"]
        display["Time (Riyadh)"] = display["Time (Riyadh)"].dt.strftime("%b %d %H:%M")
        display["Action"] = display["Action"].str.replace("_", " ")
        display["Status"] = display["Status"].map(
            lambda s: f"{STATUS_EMOJI.get(s, '•')} {s}"
        )

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Time (Riyadh)": st.column_config.TextColumn(width="small"),
                "Role":          st.column_config.TextColumn(width="medium"),
                "Action":        st.column_config.TextColumn(width="medium"),
                "Status":        st.column_config.TextColumn(width="small"),
                "Channel":       st.column_config.TextColumn(width="small"),
                "Campaign":      st.column_config.TextColumn(width="large"),
                "Rows":          st.column_config.NumberColumn(width="small"),
                "Duration (s)":  st.column_config.NumberColumn(format="%.1f", width="small"),
            },
            height=560,
        )

# ══════════════════════════════════════════════════════
# RIGHT — Workflow Cards
# ══════════════════════════════════════════════════════
with right:
    st.subheader("Workflows")
    st.caption("Edit workflows.py → dashboard auto-reflects. No Miro needed.")

    role_counts = load_role_counts()

    for wf in WORKFLOWS:
        count     = role_counts.get(wf["id"], 0)
        count_str = f"  ·  {count} runs (7d)" if count else ""

        with st.expander(f"{wf['emoji']} **{wf['role']}**{count_str}"):
            st.caption(f"**Trigger:** {wf['trigger']}")
            st.write(wf["description"])

            st.write("**Steps:**")
            for i, step in enumerate(wf["steps"], 1):
                st.write(f"{i}. {step}")

            st.write("**Flow:**")
            st.graphviz_chart(wf["graphviz"], use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
now_riyadh = datetime.now(RIYADH).strftime("%Y-%m-%d %H:%M")
st.caption(f"Last loaded: {now_riyadh} Riyadh  ·  Refreshes every 5 min  ·  Source: BQ agent_activity_log")

# ── Auto-refresh every 5 minutes ─────────────────────────────────────────────
time.sleep(300)
st.rerun()
