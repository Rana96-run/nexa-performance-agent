"""
Looker Studio Report Setup for Qoyod Performance Agent
=======================================================
This script:
  1. Validates BigQuery connection + views exist
  2. Creates any missing enhanced views
  3. Prints the ready-made Looker Studio data source URLs
  4. Outputs the full report config JSON to looker/report_config.json

Run:  python looker/setup.py
"""
import os, json
from dotenv import load_dotenv
load_dotenv()

P = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
D = os.getenv("BQ_DATASET", "qoyod_marketing")

# ─────────────────────────────────────────────────────────────
# Enhanced views (Windsor-style additions on top of core views)
# ─────────────────────────────────────────────────────────────

ENHANCED_VIEWS = {

"v_kpi_scorecard": f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_kpi_scorecard` AS
-- Single-row 30-day KPI summary.
-- Uses CURRENT_DATE() as `date` anchor so Looker Studio can use it as
-- date range dimension without causing type errors.
-- All ratio fields (CPL, CPQL, ROAS) are correctly pre-calculated over
-- the full 30-day window — they must NOT be re-summed by Looker.
SELECT
  CURRENT_DATE()                                               AS date,
  CAST(ROUND(SUM(spend), 2) AS FLOAT64)                        AS total_spend,
  CAST(SUM(hs_leads) AS FLOAT64)                               AS total_leads,
  CAST(SUM(hs_qualified) AS FLOAT64)                           AS total_sqls,
  CAST(SUM(hs_disqualified) AS FLOAT64)                        AS total_disqualified,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(hs_leads)), 2)             AS blended_cpl,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(hs_qualified)), 2)         AS blended_cpql,
  ROUND(SAFE_DIVIDE(SUM(hs_qualified),SUM(hs_leads))*100, 1)   AS qual_rate_pct,
  ROUND(SAFE_DIVIDE(SUM(revenue_won), SUM(spend)), 2)          AS blended_roas,
  CAST(SUM(deals_won) AS FLOAT64)                              AS deals_won,
  CAST(ROUND(SUM(revenue_won), 2) AS FLOAT64)                  AS revenue_won,
  -- Lead Pipeline (accounting / e-invoice)
  CAST(SUM(leads_accounting) AS FLOAT64)                       AS leads_accounting,
  CAST(SUM(qualified_accounting) AS FLOAT64)                   AS sqls_accounting,
  CAST(SUM(disqualified_accounting) AS FLOAT64)                AS disqual_accounting,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(leads_accounting)), 2)     AS cpl_accounting,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(qualified_accounting)), 2) AS cpql_accounting,
  -- Bookkeeping Pipeline
  CAST(SUM(leads_bookkeeping) AS FLOAT64)                      AS leads_bookkeeping,
  CAST(SUM(qualified_bookkeeping) AS FLOAT64)                  AS sqls_bookkeeping,
  CAST(SUM(disqualified_bookkeeping) AS FLOAT64)               AS disqual_bookkeeping,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(leads_bookkeeping)), 2)    AS cpl_bookkeeping,
  ROUND(SAFE_DIVIDE(SUM(spend), SUM(qualified_bookkeeping)), 2) AS cpql_bookkeeping
FROM `{P}.{D}.channel_roas_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
""",

"v_channel_scorecard": f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_channel_scorecard` AS
-- Per-channel KPI card with WoW delta + two-pipeline breakdown
WITH cur AS (
  SELECT channel,
    SUM(spend)              AS spend,
    SUM(hs_leads)           AS leads,
    SUM(hs_qualified)       AS sqls,
    SUM(hs_disqualified)    AS disqualified,
    -- Lead Pipeline (accounting / e-invoice)
    SUM(leads_accounting)       AS leads_acct,
    SUM(qualified_accounting)   AS sqls_acct,
    SUM(disqualified_accounting) AS disqual_acct,
    -- Bookkeeping Pipeline
    SUM(leads_bookkeeping)      AS leads_book,
    SUM(qualified_bookkeeping)  AS sqls_book,
    SUM(disqualified_bookkeeping) AS disqual_book,
    SUM(revenue_won)        AS revenue_won,
    SAFE_DIVIDE(SUM(spend),SUM(hs_leads))       AS cpl,
    SAFE_DIVIDE(SUM(spend),SUM(hs_qualified))   AS cpql,
    SAFE_DIVIDE(SUM(hs_qualified),SUM(hs_leads))*100 AS qual_rate,
    SAFE_DIVIDE(SUM(revenue_won),SUM(spend))    AS roas
  FROM `{P}.{D}.channel_roas_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE(),INTERVAL 7 DAY) AND DATE_SUB(CURRENT_DATE(),INTERVAL 1 DAY)
  GROUP BY 1
),
prev AS (
  SELECT channel,
    SUM(spend)   AS spend,
    SUM(hs_leads) AS leads,
    SAFE_DIVIDE(SUM(spend),SUM(hs_leads))     AS cpl,
    SAFE_DIVIDE(SUM(spend),SUM(hs_qualified)) AS cpql
  FROM `{P}.{D}.channel_roas_daily`
  WHERE date BETWEEN DATE_SUB(CURRENT_DATE(),INTERVAL 14 DAY) AND DATE_SUB(CURRENT_DATE(),INTERVAL 8 DAY)
  GROUP BY 1
)
SELECT
  c.channel,
  -- ── Human-readable channel label (used as display name in dashboards) ──────
  CASE c.channel
    WHEN 'google_ads'     THEN 'Google Ads'
    WHEN 'meta'           THEN 'Meta Ads'
    WHEN 'snapchat'       THEN 'Snapchat Ads'
    WHEN 'tiktok'         THEN 'TikTok Ads'
    WHEN 'linkedin'       THEN 'LinkedIn Ads'
    WHEN 'microsoft_ads'  THEN 'Microsoft Ads'
    WHEN 'youtube'        THEN 'YouTube Ads'
    WHEN 'organic_search' THEN 'Organic Search'
    ELSE INITCAP(REPLACE(c.channel, '_', ' '))
  END AS channel_name,
  ROUND(c.spend,0)       AS spend_7d,
  c.leads                AS leads_7d,
  c.sqls                 AS sqls_7d,
  c.disqualified         AS disqualified_7d,
  -- ── Metrics with clean names for dashboard column headers ─────────────────
  ROUND(c.cpl,2)         AS CPL,
  ROUND(c.cpql,2)        AS CPQL,
  ROUND(c.qual_rate,1)   AS Qual_Rate_Pct,
  ROUND(c.roas,2)        AS roas_7d,
  -- Lead Pipeline columns
  c.leads_acct           AS leads_accounting_7d,
  c.sqls_acct            AS sqls_accounting_7d,
  c.disqual_acct         AS disqual_accounting_7d,
  ROUND(SAFE_DIVIDE(c.spend, c.leads_acct), 2)  AS cpl_accounting_7d,
  ROUND(SAFE_DIVIDE(c.spend, c.sqls_acct), 2)   AS cpql_accounting_7d,
  -- Bookkeeping Pipeline columns
  c.leads_book           AS leads_bookkeeping_7d,
  c.sqls_book            AS sqls_bookkeeping_7d,
  c.disqual_book         AS disqual_bookkeeping_7d,
  ROUND(SAFE_DIVIDE(c.spend, c.leads_book), 2)  AS cpl_bookkeeping_7d,
  ROUND(SAFE_DIVIDE(c.spend, c.sqls_book), 2)   AS cpql_bookkeeping_7d,
  -- WoW deltas (negative = improved for CPL/CPQL)
  ROUND(c.cpl - p.cpl, 2)    AS cpl_wow_delta,
  ROUND(c.cpql - p.cpql, 2)  AS cpql_wow_delta,
  ROUND(c.leads - p.leads, 0) AS leads_wow_delta,
  ROUND(SAFE_DIVIDE(c.spend - p.spend, p.spend)*100, 1) AS spend_wow_pct,
  -- Status badge
  CASE
    WHEN c.cpl < 20  THEN 'Scale'
    WHEN c.cpl <= 28 THEN 'On Target'
    WHEN c.cpl <= 30 THEN 'Warning'
    ELSE 'Pause Zone'
  END AS cpl_status
FROM cur c
LEFT JOIN prev p USING(channel)
""",

"v_daily_trend": f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_daily_trend` AS
-- 90-day daily trend for time series charts
SELECT
  date,
  channel,
  ROUND(spend,2)                                    AS spend,
  hs_leads                                          AS leads,
  hs_qualified                                      AS sqls,
  ROUND(cpl,2)                                      AS cpl,
  ROUND(cpql,2)                                     AS cpql,
  ROUND(qual_rate_pct,1)                            AS qual_rate_pct,
  ROUND(ctr,2)                                      AS ctr,
  ROUND(roas,2)                                     AS roas,
  cpl_zone,
  cpql_zone,
  -- 7-day rolling CPL (smoothed trend line)
  ROUND(AVG(cpl) OVER (
    PARTITION BY channel
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ),2) AS cpl_7d_avg,
  ROUND(AVG(cpql) OVER (
    PARTITION BY channel
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
  ),2) AS cpql_7d_avg
FROM `{P}.{D}.channel_roas_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
""",

"v_campaign_leaderboard": f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_campaign_leaderboard` AS
-- Top/bottom campaigns by CPL — last 14 days
SELECT
  campaign_name,
  channel,
  seasonal_tag,
  format_tag,
  ROUND(SUM(spend),0)                                      AS spend,
  SUM(platform_leads)                                      AS leads,
  ROUND(SAFE_DIVIDE(SUM(spend),SUM(platform_leads)),2)     AS cpl,
  ROUND(SUM(impressions)/1000,1)                           AS impressions_k,
  ROUND(AVG(ctr),2)                                        AS avg_ctr,
  CASE
    WHEN SAFE_DIVIDE(SUM(spend),SUM(platform_leads)) < 20  THEN 'Scale 🚀'
    WHEN SAFE_DIVIDE(SUM(spend),SUM(platform_leads)) <= 28 THEN 'On Target ✅'
    WHEN SAFE_DIVIDE(SUM(spend),SUM(platform_leads)) <= 30 THEN 'Warning ⚠️'
    WHEN SAFE_DIVIDE(SUM(spend),SUM(platform_leads)) IS NULL THEN 'No Leads'
    ELSE 'Pause Zone 🔴'
  END AS status
FROM `{P}.{D}.campaign_performance_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND spend > 0
GROUP BY 1,2,3,4
ORDER BY spend DESC
LIMIT 50
""",

"v_budget_pacing": f"""
CREATE OR REPLACE VIEW `{P}.{D}.v_budget_pacing` AS
-- Monthly budget pacing — actual vs expected spend this month
WITH daily_spend AS (
  SELECT
    channel,
    SUM(spend) AS month_to_date_spend,
    DATE_DIFF(CURRENT_DATE(), DATE_TRUNC(CURRENT_DATE(), MONTH), DAY) + 1 AS days_elapsed,
    DATE_DIFF(DATE_TRUNC(DATE_ADD(CURRENT_DATE(), INTERVAL 1 MONTH), MONTH),
              DATE_TRUNC(CURRENT_DATE(), MONTH), DAY) AS days_in_month
  FROM `{P}.{D}.campaigns_daily`
  WHERE DATE_TRUNC(date, MONTH) = DATE_TRUNC(CURRENT_DATE(), MONTH)
  GROUP BY 1
)
SELECT
  channel,
  ROUND(month_to_date_spend, 0) AS actual_spend,
  days_elapsed,
  days_in_month,
  ROUND(SAFE_DIVIDE(days_elapsed, days_in_month) * 100, 1) AS month_progress_pct,
  -- Expected vs actual pacing
  ROUND(SAFE_DIVIDE(month_to_date_spend, days_elapsed) * days_in_month, 0) AS projected_month_spend,
  CASE
    WHEN SAFE_DIVIDE(month_to_date_spend, days_elapsed) * days_in_month IS NULL THEN 'No Data'
    WHEN SAFE_DIVIDE(month_to_date_spend, days_elapsed) >
         SAFE_DIVIDE(month_to_date_spend, NULLIF(days_elapsed,0)) * 1.15 THEN 'Overpacing ⚠️'
    WHEN SAFE_DIVIDE(month_to_date_spend, days_elapsed) <
         SAFE_DIVIDE(month_to_date_spend, NULLIF(days_elapsed,0)) * 0.80 THEN 'Underpacing'
    ELSE 'On Pace ✅'
  END AS pacing_status
FROM daily_spend
""",
}


def validate_and_create_views():
    try:
        from collectors.bq_writer import get_client
        client = get_client()
        print(f"✅ Connected to BigQuery: {P}.{D}\n")

        for name, sql in ENHANCED_VIEWS.items():
            try:
                client.query(sql).result()
                print(f"  ✅ View ready: {name}")
            except Exception as e:
                print(f"  ❌ Failed: {name}: {e}")

        print(f"\n✅ {len(ENHANCED_VIEWS)} enhanced views created/updated.")
    except Exception as e:
        print(f"[ERROR] BQ connection failed: {e}")
        print("   -> Make sure bigquery-key.json is in place and BQ_PROJECT_ID is set.")


def print_datasource_urls():
    base = "https://lookerstudio.google.com/datasources/create"
    views = [
        ("v_kpi_scorecard",          "Qoyod — KPI Scorecard"),
        ("v_channel_scorecard",      "Qoyod — Channel Scorecard"),
        ("v_daily_trend",            "Qoyod — Daily Trend"),
        ("v_campaign_leaderboard",   "Qoyod — Campaign Leaderboard"),
        ("v_budget_pacing",          "Qoyod — Budget Pacing"),
        ("channel_roas_daily",       "Qoyod — Channel ROAS Daily"),
        ("channel_roas_monthly",     "Qoyod — Channel ROAS Monthly"),
        ("campaign_performance_daily","Qoyod — Campaign Performance"),
        ("disqualification_matrix",  "Qoyod — Disqualification Matrix"),
        ("pipeline_funnel",          "Qoyod — Pipeline Funnel"),
    ]

    print("\n" + "="*60)
    print("LOOKER STUDIO — DATA SOURCES TO ADD")
    print("="*60)
    print(f"\nProject:  {P}")
    print(f"Dataset:  {D}\n")
    for table, label in views:
        print(f"  {label}")
        print(f"  Table: {table}\n")
    print("-> In Looker Studio: Add data source -> BigQuery -> select each table above")
    print("="*60)


def export_report_config():
    config = {
        "report_name": "Qoyod Performance Dashboard",
        "theme": {
            "background": "#FFFFFF",
            "primary":    "#1A1A2E",
            "accent":     "#6C63FF",
            "positive":   "#00C48C",
            "warning":    "#FFB800",
            "negative":   "#FF4D4F",
            "text":       "#2D2D2D",
            "text_light": "#8C8C8C",
            "channels": {
                "google_ads": "#4285F4",
                "meta":       "#1877F2",
                "snapchat":   "#FFFC00",
                "tiktok":     "#010101",
                "microsoft":  "#00A4EF",
            }
        },
        "pages": [
            {
                "name": "1 — Executive Overview",
                "layout": "full_width",
                "components": [
                    {
                        "type": "scorecard_row",
                        "source": "v_kpi_scorecard",
                        "cards": [
                            {"metric": "total_spend",    "label": "Total Spend",    "format": "SAR #,###", "comparison": None},
                            {"metric": "total_leads",    "label": "Total Leads",    "format": "#,###",     "comparison": None},
                            {"metric": "total_sqls",     "label": "Total SQLs",     "format": "#,###",     "comparison": None},
                            {"metric": "blended_cpl",    "label": "Blended CPL",    "format": "SAR #.##",  "color_rules": [{"max":20,"color":"positive"},{"max":28,"color":"warning"},{"min":30,"color":"negative"}]},
                            {"metric": "blended_cpql",   "label": "Blended CPQL",   "format": "SAR #.##",  "color_rules": [{"max":40,"color":"positive"},{"max":65,"color":"warning"},{"min":80,"color":"negative"}]},
                            {"metric": "qual_rate_pct",  "label": "Qual Rate",      "format": "#.#%"},
                            {"metric": "blended_roas",   "label": "Blended ROAS",   "format": "#.##x"},
                            {"metric": "revenue_won",    "label": "Revenue Won",    "format": "SAR #,###"},
                        ]
                    },
                    {
                        "type": "time_series",
                        "source": "v_daily_trend",
                        "title": "CPL & CPQL Trend (7-day rolling)",
                        "x": "date",
                        "series": [
                            {"metric": "cpl_7d_avg",  "label": "CPL (7d avg)",  "color": "#6C63FF", "line_style": "solid"},
                            {"metric": "cpql_7d_avg", "label": "CPQL (7d avg)", "color": "#FF4D4F", "line_style": "dashed"},
                        ],
                        "reference_lines": [
                            {"value": 30, "label": "CPL Pause Zone",  "color": "#FF4D4F"},
                            {"value": 80, "label": "CPQL Pause Zone", "color": "#FF4D4F"},
                        ],
                        "filters": ["channel"],
                        "date_range_control": True,
                    },
                    {
                        "type": "bar_chart_grouped",
                        "source": "v_channel_scorecard",
                        "title": "Channel Performance — This Week",
                        "dimension": "channel",
                        "metrics": ["spend_7d", "leads_7d", "sqls_7d"],
                        "colors": "channel_map",
                        "show_data_labels": True,
                    },
                    {
                        "type": "table_with_heatmap",
                        "source": "v_channel_scorecard",
                        "title": "Channel KPIs + WoW",
                        "columns": [
                            "channel", "spend_7d", "leads_7d", "sqls_7d",
                            "CPL", "CPQL", "Qual_Rate_Pct", "roas_7d",
                            "cpl_wow_delta", "cpql_wow_delta", "cpl_status"
                        ],
                        "heatmap_cols": ["CPL", "CPQL"],
                        "color_rules": {
                            "cpl_status": {
                                "Scale 🚀":      "#00C48C",
                                "On Target ✅":  "#52C41A",
                                "Warning ⚠️":   "#FFB800",
                                "Pause Zone 🔴": "#FF4D4F",
                            }
                        }
                    }
                ]
            },
            {
                "name": "2 — CPL & CPQL Deep Dive",
                "components": [
                    {
                        "type": "time_series",
                        "source": "v_daily_trend",
                        "title": "Daily CPL by Channel (90 days)",
                        "x": "date",
                        "breakdown": "channel",
                        "metric": "cpl",
                        "reference_lines": [{"value": 28, "label": "Warning", "color": "#FFB800"},
                                             {"value": 30, "label": "Pause", "color": "#FF4D4F"}],
                        "color_map": "channel_colors",
                    },
                    {
                        "type": "time_series",
                        "source": "v_daily_trend",
                        "title": "Daily CPQL by Channel (90 days)",
                        "x": "date",
                        "breakdown": "channel",
                        "metric": "cpql",
                        "reference_lines": [{"value": 65, "label": "Warning", "color": "#FFB800"},
                                             {"value": 80, "label": "Pause", "color": "#FF4D4F"}],
                    },
                    {
                        "type": "scatter_plot",
                        "source": "v_channel_scorecard",
                        "title": "CPL vs Qualification Rate",
                        "x": "CPL",
                        "y": "Qual_Rate_Pct",
                        "size": "spend_7d",
                        "color": "channel",
                        "tooltip": ["channel", "spend_7d", "leads_7d"],
                    }
                ]
            },
            {
                "name": "3 — Campaign Leaderboard",
                "components": [
                    {
                        "type": "table_sortable",
                        "source": "v_campaign_leaderboard",
                        "title": "Top Campaigns — Last 14 Days",
                        "columns": ["campaign_name","channel","format_tag","seasonal_tag",
                                     "spend","leads","cpl","avg_ctr","status"],
                        "default_sort": "spend DESC",
                        "row_color_by": "status",
                        "filters": ["channel", "format_tag", "seasonal_tag"],
                        "search": True,
                    },
                    {
                        "type": "bar_chart_horizontal",
                        "source": "v_campaign_leaderboard",
                        "title": "CPL by Campaign (Top 15)",
                        "dimension": "campaign_name",
                        "metric": "cpl",
                        "color_by": "status",
                        "limit": 15,
                        "reference_line": {"value": 30, "label": "Pause threshold"},
                    }
                ]
            },
            {
                "name": "4 — Budget & Pacing",
                "components": [
                    {
                        "type": "bullet_chart",
                        "source": "v_budget_pacing",
                        "title": "Month-to-Date Budget Pacing by Channel",
                        "dimension": "channel",
                        "metric": "actual_spend",
                        "target": "projected_month_spend",
                        "color_by": "pacing_status",
                    },
                    {
                        "type": "time_series",
                        "source": "channel_roas_daily",
                        "title": "Daily Spend by Channel (this month)",
                        "x": "date",
                        "breakdown": "channel",
                        "metric": "spend",
                        "chart_type": "area_stacked",
                        "date_filter": "current_month",
                    }
                ]
            },
            {
                "name": "5 — Pipeline & Funnel",
                "components": [
                    {
                        "type": "funnel_chart",
                        "source": "pipeline_funnel",
                        "title": "Lead-to-Deal Funnel by Channel",
                        "stages": ["leads_total","leads_qualified","leads_open","leads_disqualified"],
                        "breakdown": "qoyod_source",
                        "filters": ["month", "pipeline"],
                    },
                    {
                        "type": "table_sortable",
                        "source": "disqualification_matrix",
                        "title": "Disqualification Reasons",
                        "columns": ["date","qoyod_source","pipeline","top_disqual_reason","disqualified_count"],
                        "default_sort": "disqualified_count DESC",
                    },
                    {
                        "type": "bar_chart",
                        "source": "channel_roas_monthly",
                        "title": "Monthly ROAS by Channel",
                        "x": "month",
                        "breakdown": "channel",
                        "metric": "roas",
                        "reference_line": {"value": 1, "label": "Break-even"},
                    }
                ]
            },
            {
                "name": "6 — Channel Deep Dive",
                "components": [
                    {
                        "type": "filter_control",
                        "dimension": "channel",
                        "style": "tab_selector",
                    },
                    {
                        "type": "scorecard_row",
                        "source": "v_channel_scorecard",
                        "filter_by": "channel",
                        "cards": ["spend_7d","leads_7d","sqls_7d","CPL","CPQL","roas_7d"],
                    },
                    {
                        "type": "time_series",
                        "source": "v_daily_trend",
                        "title": "CPL Trend — Selected Channel",
                        "filter_by": "channel",
                        "x": "date",
                        "metric": "cpl",
                    },
                    {
                        "type": "table_sortable",
                        "source": "campaign_performance_daily",
                        "title": "Campaign Breakdown",
                        "filter_by": "channel",
                        "columns": ["campaign_name","spend","platform_leads","platform_cpl","format_tag","status"],
                    }
                ]
            }
        ]
    }

    out_path = os.path.join(os.path.dirname(__file__), "report_config.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report config saved -> {out_path}")
    return config


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd in ("all", "views"):
        validate_and_create_views()

    if cmd in ("all", "urls"):
        print_datasource_urls()

    if cmd in ("all", "config"):
        export_report_config()
