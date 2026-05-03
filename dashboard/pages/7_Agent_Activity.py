"""
Agent Activity Dashboard
========================
Page 7 — shows everything the agent has done and the workflow behind each role.

Left panel  : recent activity timeline from BQ (agent_activity_log)
Right panel : clickable role cards — click any role to expand its full
              Mermaid flowchart. Workflows auto-update from data/workflows.py;
              no Miro edits needed.

Auto-refreshes every 5 minutes.
"""
import os
import sys
from pathlib import Path

import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

# ── Path setup so we can import from project root ────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows import WORKFLOWS

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agent Activity",
    page_icon="🤖",
    layout="wide",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Role card hover */
div[data-testid="stExpander"] > div:first-child {
    background: #1e1e2e;
    border-radius: 8px;
    border-left: 4px solid #7c3aed;
    padding: 4px 8px;
}
/* Status badges */
.badge-success   { background:#166534; color:#bbf7d0; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-failed    { background:#7f1d1d; color:#fecaca; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-pending   { background:#78350f; color:#fde68a; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-approved  { background:#14532d; color:#bbf7d0; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-rejected  { background:#450a0a; color:#fecaca; padding:2px 8px; border-radius:12px; font-size:12px; }
.badge-skipped   { background:#1e293b; color:#94a3b8; padding:2px 8px; border-radius:12px; font-size:12px; }
/* Timeline row */
.timeline-row    { border-bottom: 1px solid #1e293b; padding: 6px 0; }
/* Mermaid container */
.mermaid-wrap    { background:#0f172a; border-radius:8px; padding:16px; margin-top:8px; }
</style>
""", unsafe_allow_html=True)


# ── BQ helper ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)   # re-fetch every 5 minutes
def load_activity(hours: int = 48) -> pd.DataFrame:
    """Pull last N hours from agent_activity_log."""
    try:
        from collectors.bq_writer import get_client
        project = os.getenv("BQ_PROJECT_ID")
        dataset = os.getenv("BQ_DATASET", "qoyod_marketing")
        client  = get_client()
        sql = f"""
            SELECT
                ts, role, action, status,
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
        # Convert to Riyadh time for display
        df["ts_riyadh"] = df["ts"].dt.tz_convert("Asia/Riyadh")
        return df
    except Exception as e:
        st.warning(f"Could not load activity log: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_role_summary() -> pd.DataFrame:
    """Count actions per role in last 7 days."""
    try:
        from collectors.bq_writer import get_client
        project = os.getenv("BQ_PROJECT_ID")
        dataset = os.getenv("BQ_DATASET", "qoyod_marketing")
        client  = get_client()
        sql = f"""
            SELECT role, action, status, COUNT(*) as n
            FROM `{project}.{dataset}.agent_activity_log`
            WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 168 HOUR)
            GROUP BY role, action, status
            ORDER BY n DESC
        """
        return client.query(sql).to_dataframe()
    except Exception:
        return pd.DataFrame()


# ── Status badge helper ───────────────────────────────────────────────────────
STATUS_EMOJI = {
    "success":          "✅",
    "failed":           "❌",
    "pending_approval": "⏳",
    "approved":         "✅",
    "rejected":         "🚫",
    "skipped":          "⏭️",
}

ROLE_COLORS = {
    "daily_digest":     "#7c3aed",
    "bq_refresh":       "#0ea5e9",
    "pause_watcher":    "#ef4444",
    "junk_leads":       "#f59e0b",
    "slack_approvals":  "#10b981",
    "airbyte_normalizer":"#3b82f6",
    "campaign_creator": "#8b5cf6",
    "asana_creator":    "#f97316",
}


# ── Mermaid renderer ──────────────────────────────────────────────────────────
def render_mermaid(diagram: str, height: int = 420):
    """Render a Mermaid diagram using the CDN library via st.components."""
    import streamlit.components.v1 as components
    escaped = diagram.replace("`", "\\`")
    html = f"""
    <div class="mermaid-wrap">
        <div class="mermaid" id="mermaid-{abs(hash(diagram)) % 999999}">
{diagram}
        </div>
    </div>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {{
                primaryColor: '#1e1e2e',
                primaryTextColor: '#cdd6f4',
                primaryBorderColor: '#7c3aed',
                lineColor: '#a6adc8',
                secondaryColor: '#181825',
                tertiaryColor: '#11111b',
            }}
        }});
        await mermaid.run();
    </script>
    """
    components.html(html, height=height, scrolling=True)


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🤖 Agent Activity")
st.caption("Everything the agent does — live from BigQuery. Workflows auto-update when code changes.")

# Filters row
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])
with col_f1:
    hours_back = st.selectbox("Show last", [6, 12, 24, 48, 168], index=2,
                               format_func=lambda h: f"{h}h" if h < 48 else f"{h//24}d")
with col_f2:
    role_filter = st.selectbox(
        "Role",
        ["All"] + sorted({w["id"] for w in WORKFLOWS}),
    )
with col_f3:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
with col_f4:
    st.metric("Auto-refresh", "5 min")

st.divider()

# ── Two-column layout ─────────────────────────────────────────────────────────
col_left, col_right = st.columns([5, 4], gap="large")

# ════════════════════════════════════════════════════════════════════
# LEFT: Activity Timeline
# ════════════════════════════════════════════════════════════════════
with col_left:
    st.subheader("📅 Activity Timeline", anchor=False)

    df = load_activity(hours=hours_back)

    if df.empty:
        st.info("No activity recorded yet. The agent will start logging once it runs.")
    else:
        if role_filter != "All":
            df = df[df["role"] == role_filter]

        if df.empty:
            st.info(f"No activity for role '{role_filter}' in the last {hours_back}h.")
        else:
            # Summary metrics
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Total actions", len(df))
            mc2.metric("✅ Success",  (df["status"] == "success").sum())
            mc3.metric("⏳ Pending",  df["status"].str.startswith("pending").sum())
            mc4.metric("❌ Failed",   (df["status"] == "failed").sum())

            st.markdown("---")

            # Timeline table
            for _, row in df.iterrows():
                ts_str = row["ts_riyadh"].strftime("%b %d %H:%M")
                emoji  = STATUS_EMOJI.get(row["status"], "•")
                color  = ROLE_COLORS.get(row["role"], "#64748b")
                role_badge = f'<span style="color:{color};font-weight:600">{row["role"]}</span>'
                action_str = row["action"].replace("_", " ")
                channel_str = f' · {row["channel"]}' if pd.notna(row.get("channel")) and row["channel"] else ""
                campaign_str = f'<br><small style="color:#94a3b8">↳ {row["campaign_name"]}</small>' if pd.notna(row.get("campaign_name")) and row["campaign_name"] else ""
                dur_str = f' <small style="color:#64748b">({row["duration_s"]:.1f}s)</small>' if pd.notna(row.get("duration_s")) and row["duration_s"] else ""

                st.markdown(
                    f'<div class="timeline-row">'
                    f'<small style="color:#64748b">{ts_str}</small> '
                    f'{emoji} {role_badge} · {action_str}{channel_str}{dur_str}'
                    f'{campaign_str}'
                    f'</div>',
                    unsafe_allow_html=True
                )

# ════════════════════════════════════════════════════════════════════
# RIGHT: Workflow Cards
# ════════════════════════════════════════════════════════════════════
with col_right:
    st.subheader("⚙️ Workflows", anchor=False)
    st.caption("Click any role to see its full workflow. Updates automatically when code changes — no Miro needed.")

    # Load 7-day summary for hit counts
    summary_df = load_role_summary()
    role_counts = {}
    if not summary_df.empty:
        role_counts = (
            summary_df[summary_df["status"] == "success"]
            .groupby("role")["n"].sum().to_dict()
        )

    for wf in WORKFLOWS:
        wf_id    = wf["id"]
        count    = role_counts.get(wf_id, 0)
        color    = ROLE_COLORS.get(wf_id, "#64748b")
        count_str = f" · {count} runs (7d)" if count else ""

        with st.expander(f"{wf['emoji']} **{wf['role']}**{count_str}", expanded=False):
            st.markdown(f"**Trigger:** {wf['trigger']}")
            st.markdown(f"_{wf['description']}_")

            # Steps list
            with st.container():
                steps_md = "\n".join(f"{i+1}. {s}" for i, s in enumerate(wf["steps"]))
                st.markdown(f"**Steps:**\n{steps_md}")

            # Mermaid diagram
            st.markdown("**Flow:**")
            render_mermaid(wf["mermaid"].strip(), height=380)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Last loaded: {datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d %H:%M')} Riyadh · "
    "Auto-refreshes every 5 min · Powered by BigQuery agent_activity_log"
)
