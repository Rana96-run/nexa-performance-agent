"""Recreate all BQ views, skipping any that are materialised tables."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import (
    get_client,
    UTM_PAID_ATTRIBUTION_VIEW_SQL,
    V_ADSET_PERFORMANCE_SQL,
    V_AD_PERFORMANCE_SQL,
    V_KEYWORD_PERFORMANCE_SQL,
    V_LP_PERFORMANCE_WEEKLY_SQL,
    V_LP_WEEKLY_SUMMARY_SQL,
    CAMPAIGN_PERFORMANCE_VIEW_SQL,
    LEAD_UTM_PERFORMANCE_VIEW_SQL,
    LEAD_FUNNEL_BY_PIPELINE_VIEW_SQL,
)

client = get_client()

views = [
    (CAMPAIGN_PERFORMANCE_VIEW_SQL,    "campaign_performance"),
    (LEAD_UTM_PERFORMANCE_VIEW_SQL,    "lead_utm_performance"),
    (LEAD_FUNNEL_BY_PIPELINE_VIEW_SQL, "lead_funnel_by_pipeline"),
    (UTM_PAID_ATTRIBUTION_VIEW_SQL,    "utm_paid_attribution_daily"),
    (V_ADSET_PERFORMANCE_SQL,          "v_adset_performance"),
    (V_AD_PERFORMANCE_SQL,             "v_ad_performance"),
    (V_KEYWORD_PERFORMANCE_SQL,        "v_keyword_performance"),
    (V_LP_PERFORMANCE_WEEKLY_SQL,      "v_lp_performance_weekly"),
    (V_LP_WEEKLY_SUMMARY_SQL,          "v_lp_weekly_summary"),
]

for sql, name in views:
    try:
        client.query(sql).result()
        print(f"[OK]   {name}")
    except Exception as e:
        msg = str(e)
        if "is currently a TABLE" in msg:
            print(f"[SKIP] {name} — exists as materialised table (OK for utm_paid_attribution_daily)")
        else:
            print(f"[ERR]  {name}: {msg[:200]}")

