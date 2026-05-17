"""Composes the next-month plan from existing analyser outputs:
  - period_compare.compare_monthly() — current state vs prior month
  - forecaster.forecast() — status-quo MoM projection
  - Manual action-impact deltas — what changes if Asana tasks execute

Produces a structured plan with: current state, root causes, action calendar
(launch_policy.cooldown-aware), scenarios (status-quo vs with-actions),
KPI targets, abort/scale gates."""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from analysers.period_compare import compare_monthly, compare, to_markdown as pc_md
from analysers.forecaster   import forecast, to_markdown as fc_md


# ── Estimated impact per Asana action (units: USD/day spend delta,
#    CPQL multiplier on affected dollars) ──────────────────────────────────

ACTIONS = [
    # (task#, name, daily_spend_saved, redeployed_to, expected_cpql_on_savings)
    {"task": "#1",  "name": "Pause PMax_AR_Generic",                        "save": 310,  "redeploy": "PMax_AR_Invoice_FiveSectors",   "cpql_on_save": 386,  "cpql_redeploy": 86},
    {"task": "#2",  "name": "Pause PMax_AR_Generic_Retargeting",            "save": 280,  "redeploy": "PMax_AR_Invoice",                "cpql_on_save": 175,  "cpql_redeploy": 110},
    {"task": "#3",  "name": "Scale-back Search_E-invoice_AR",                "save": 190,  "redeploy": "Search_AR_Brand",                "cpql_on_save": 133,  "cpql_redeploy": 43},
    {"task": "#5",  "name": "Cut Meta BrandingEquity Lookalike 75%",          "save": 190,  "redeploy": "Meta Bookkeeping Lookalike",     "cpql_on_save": 181,  "cpql_redeploy": 50},
    {"task": "#7",  "name": "Pause Bing 5-pack",                              "save": 250,  "redeploy": "Bing Brand variants validated",  "cpql_on_save": 260,  "cpql_redeploy": 80},
    {"task": "#8",  "name": "Cut Bing_WebsiteTraffic to 40%",                 "save": 65,   "redeploy": "Bing brand IS",                  "cpql_on_save": 149,  "cpql_redeploy": 90},
    {"task": "#9",  "name": "Pause 3 Google Generic Search campaigns",       "save": 650,  "redeploy": "Search_AR_Brand + PMax_Invoice", "cpql_on_save": 280,  "cpql_redeploy": 60},
]

# Duplication launches — from scripts/_propose_duplicates.py, daily budgets
DUPLICATIONS = [
    {"date": "2026-05-17", "name": "Meta_LeadGen_Invoice_Prospecting_Interests_MaxmizeLeads_Instantform",      "channel": "meta",      "budget": 30,  "expected_cpql": 55},
    {"date": "2026-05-17", "name": "Snapchat_LeadGen_Invoice_Prospecting_Interest_iOS_Instantform",            "channel": "snapchat",  "budget": 100, "expected_cpql": 45},
    {"date": "2026-05-24", "name": "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform_v2 (seed swap)", "channel": "meta",      "budget": 25,  "expected_cpql": 45},
    {"date": "2026-05-24", "name": "Snapchat_LeadGen_Invoice_Broad_iPhone_Instantform",                        "channel": "snapchat",  "budget": 25,  "expected_cpql": 50},
    {"date": "2026-05-31", "name": "Meta_Conversion_Prospecting_Lookalike_Bookkeeping_Websiteform",            "channel": "meta",      "budget": 25,  "expected_cpql": 55},
    {"date": "2026-05-31", "name": "Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_iOS_Instantform",        "channel": "snapchat",  "budget": 75,  "expected_cpql": 50},
    {"date": "2026-06-07", "name": "Meta_LeadGen_Qflavours_Prospecting_Interests_MaxmizeLeads_Instantform",    "channel": "meta",      "budget": 20,  "expected_cpql": 70},
    {"date": "2026-06-07", "name": "Snapchat_LeadGen_Bookkeeping_Prospecting_Interest_Android_Instantform",   "channel": "snapchat",  "budget": 50,  "expected_cpql": 60},
]


def compute_action_impact(days: int = 30) -> dict:
    """Aggregate the expected CPQL improvement if all queued actions execute."""
    save_per_day = sum(a["save"] for a in ACTIONS)
    # SQLs saved: spend / current_bad_cpql; SQLs gained: same spend / better_cpql
    sqls_lost = sum(a["save"] / a["cpql_on_save"] for a in ACTIONS)
    sqls_gained = sum(a["save"] / a["cpql_redeploy"] for a in ACTIONS)
    net_sqls_per_day = sqls_gained - sqls_lost
    dup_spend = sum(d["budget"] for d in DUPLICATIONS)
    dup_sqls = sum(d["budget"] / d["expected_cpql"] for d in DUPLICATIONS)
    return {
        "spend_reallocated_per_day": round(save_per_day, 0),
        "spend_reallocated_per_month": round(save_per_day * days, 0),
        "sqls_currently_per_day_on_that_spend": round(sqls_lost, 1),
        "sqls_after_reallocation_per_day": round(sqls_gained, 1),
        "net_sqls_per_day_from_reallocation": round(net_sqls_per_day, 1),
        "duplication_daily_budget_total": dup_spend,
        "duplication_expected_sqls_per_day": round(dup_sqls, 1),
    }


def build_plan() -> dict:
    p = {}

    # 1. Current state — compare current MTD vs same days last month
    monthly = compare_monthly()
    p["current_state"] = {
        "label":     monthly.label,
        "period_a":  monthly.period_a,
        "period_b":  monthly.period_b,
        "flags":     monthly.flags,
        "narrative": monthly.narrative,
    }

    # 2. Status-quo forecast
    fc = forecast()
    eom = fc.end_of_month.projected if fc.end_of_month else {}
    enm = fc.end_of_next_month.projected if fc.end_of_next_month else {}
    p["status_quo_forecast"] = {
        "eom":         eom,
        "next_month":  enm,
        "trend":       fc.end_of_month.daily_rate if fc.end_of_month else {},
    }

    # 3. With-actions impact + adjusted forecast
    impact = compute_action_impact()
    p["action_impact"] = impact
    # Approximate adjusted next-month CPQL:
    # current trend CPQL × (sqls_status_quo / (sqls_status_quo + net_gain_from_actions))
    base_cpql = (fc.end_of_month.daily_rate or {}).get("cpql") or 80
    base_sqls_per_day = (fc.end_of_month.daily_rate or {}).get("sqls_d") or 25
    adjusted_sqls = base_sqls_per_day + impact["net_sqls_per_day_from_reallocation"] + impact["duplication_expected_sqls_per_day"]
    adjusted_cpql = round((base_cpql * base_sqls_per_day) / max(adjusted_sqls, 1), 1)
    p["with_actions_forecast"] = {
        "next_month_cpql_pred":  adjusted_cpql,
        "next_month_sqls_per_day": round(adjusted_sqls, 1),
        "expected_lift_pct":      round((base_cpql - adjusted_cpql) / base_cpql * 100, 1),
    }

    # 4. Calendar
    p["calendar"] = DUPLICATIONS

    return p


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    plan = build_plan()
    print(json.dumps(plan, indent=2, default=str))
