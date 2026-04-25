"""
Dry-run: generate a sample report HTML from mock data and open it in the browser.
Usage: python tests/dry_run_report.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from reports.render import render_html, save_report
from pathlib import Path

mock_channel = {
    "channel": "google_ads",
    "label":   "Google Ads",
    "color":   "#4285F4",
    "window_days": 7,
    "narrative": (
        "Google Ads delivered solid lead volume this week, CPL inside the SCALE threshold. "
        "The top campaign Qoyod_Brand_SA_2025 contributed 62% of leads. "
        "Pause Generic_KW_broad — zero leads against $480 spend this week."
    ),
    "kpis": {
        "spend": 9820.50, "leads": 312, "qualified": 48, "disqualified": 81,
        "deals": 7, "deal_amount": 43200.00,
        "cpl": 31.47, "cpql": 204.59, "roas": 4.40,
        "cpl_zone": "scale", "cpql_zone": "acceptable",
    },
    "campaigns": [
        {"campaign": "Qoyod_Brand_SA_2025",      "cost": 3200, "leads": 194, "qualified": 32, "disqualified": 40, "cpl": 16.49, "cpql": 100.00, "deals": 5, "deal_amount": 28000, "roas": 8.75, "cpl_zone": "scale",     "cpql_zone": "scale"},
        {"campaign": "Qoyod_NonBrand_Accounting", "cost": 2800, "leads":  90, "qualified": 14, "disqualified": 28, "cpl": 31.11, "cpql": 200.00, "deals": 2, "deal_amount": 12000, "roas": 4.29, "cpl_zone": "scale",     "cpql_zone": "acceptable"},
        {"campaign": "Generic_KW_broad",          "cost":  480, "leads":   0, "qualified":  0, "disqualified":  0, "cpl": None,  "cpql": None,   "deals": 0, "deal_amount":     0, "roas": None, "cpl_zone": "pause_zone", "cpql_zone": "no_data"},
    ],
    "utm_campaign": [
        {"label": "brand_sa_exact",       "cost": 3200, "leads": 194, "qualified": 32, "disqualified": 40, "qual_rate": 0.165, "deals": 5, "deal_amount": 28000, "cpl": 16.49, "cpql": 100.00, "roas": 8.75, "cpl_zone": "scale",     "cpql_zone": "scale"},
        {"label": "nonbrand_accounting",  "cost": 2800, "leads":  90, "qualified": 14, "disqualified": 28, "qual_rate": 0.156, "deals": 2, "deal_amount": 12000, "cpl": 31.11, "cpql": 200.00, "roas": 4.29, "cpl_zone": "scale",     "cpql_zone": "acceptable"},
        {"label": "generic_broad_test",   "cost":  480, "leads":   0, "qualified":  0, "disqualified":  0, "qual_rate": None,  "deals": 0, "deal_amount":     0, "cpl": None,  "cpql": None,   "roas": None, "cpl_zone": "pause_zone", "cpql_zone": "no_data"},
    ],
    "utm_audience": [
        {"label": "sme_owners",    "cost": 3800, "leads": 180, "qualified": 30, "disqualified": 50, "qual_rate": 0.167, "deals": 5, "deal_amount": 30000, "cpl": 21.11, "cpql": 126.67, "roas": 7.89, "cpl_zone": "scale",     "cpql_zone": "scale"},
        {"label": "accountants",   "cost": 2700, "leads": 100, "qualified": 15, "disqualified": 25, "qual_rate": 0.150, "deals": 2, "deal_amount": 10000, "cpl": 27.00, "cpql": 180.00, "roas": 3.70, "cpl_zone": "scale",     "cpql_zone": "acceptable"},
        {"label": "broad_prosp",   "cost": 1200, "leads":  18, "qualified":  2, "disqualified": 10, "qual_rate": 0.111, "deals": 0, "deal_amount":     0, "cpl": 66.67, "cpql": 600.00, "roas": None, "cpl_zone": "warning",    "cpql_zone": "pause_zone"},
    ],
    "utm_content": [
        {"label": "free_trial_v3", "cost": 4200, "leads": 220, "qualified": 38, "disqualified": 55, "qual_rate": 0.173, "deals": 6, "deal_amount": 38000, "cpl": 19.09, "cpql": 110.53, "roas": 9.05, "cpl_zone": "scale",     "cpql_zone": "scale"},
        {"label": "demo_cta_v1",   "cost": 3100, "leads":  70, "qualified":  8, "disqualified": 22, "qual_rate": 0.114, "deals": 1, "deal_amount":  5000, "cpl": 44.29, "cpql": 387.50, "roas": 1.61, "cpl_zone": "acceptable", "cpql_zone": "warning"},
        {"label": "webinar_cta",   "cost":  800, "leads":  12, "qualified":  1, "disqualified":  4, "qual_rate": 0.083, "deals": 0, "deal_amount":     0, "cpl": 66.67, "cpql": 800.00, "roas": None, "cpl_zone": "warning",    "cpql_zone": "pause_zone"},
    ],
    "disq_reasons": [
        {"reason": "Not the decision maker",       "count": 35, "share": 0.432},
        {"reason": "Outside Saudi Arabia",         "count": 22, "share": 0.272},
        {"reason": "Already using competitor",     "count": 14, "share": 0.173},
        {"reason": "Too small (< 3 employees)",    "count": 10, "share": 0.123},
    ],
    "ad_groups": {"available": False, "note": "adgroups_daily collector not yet built — next sprint"},
    "ads":       {"available": False, "note": "ads_daily collector not yet built — next sprint"},
}

meta_channel = dict(mock_channel, channel="meta", label="Meta", color="#1877F2",
    narrative="Meta delivered 98 leads this week at $28.50 CPL, inside acceptable range. "
              "Retargeting audiences are efficient; broad prospecting qual rate fell to 9%. "
              "Recommend pausing the broad prospecting adset and refreshing the demo creative — it is 42 days old.",
    kpis=dict(mock_channel["kpis"], spend=2793, leads=98, cpl=28.50, cpql=232.75,
              roas=2.1, cpl_zone="scale", cpql_zone="warning"),
)

mock_report = {
    "generated_at":  "2026-04-25 08:00 Riyadh",
    "report_date":   "2026-04-24",
    "cadence":       "daily",
    "permalink":     "/reports/latest",
    "hero": {
        "date":      "2026-04-24",
        "spend":     {"value": 2430.50, "delta_pct": -4.2},
        "leads":     {"value": 87,      "delta_pct": 11.5},
        "sql":       {"value": 14,      "delta_pct": 7.7},
        "cpl":       {"value": 27.94,   "delta_pct": -14.2, "zone": "scale"},
        "cpql":      {"value": 173.61,  "delta_pct": -11.3, "zone": "acceptable"},
        "qual_rate": {"value": 0.161,   "delta_pct": 2.5},
    },
    "headline": "CPL hit $27.94 yesterday — best day in 3 weeks — driven by Google Ads brand campaigns at $16.49 CPL.",
    "what_changed": [
        "Google Ads CPL dropped 14% WoW to $27.94, entering the SCALE zone.",
        "Meta qual rate fell to 11.4% (from 16.2%) — utm_content demo_cta_v1 is the drag.",
        "Snapchat spend outpaced leads by 2x; no SQLs generated in 7 days.",
        "HubSpot shows 35 leads disqualified as 'not decision maker' — review targeting.",
    ],
    "why": (
        "Brand search volume spiked this week, pulling CPL into the scale zone on Google Ads. "
        "The efficiency gain is partly structural — brand keywords carry inherently lower CPL — "
        "and partly the new free_trial_v3 creative, which lifted qual rate to 17.3% versus 11.4% on demo_cta_v1.\n\n"
        "Meta performance is bifurcated: retargeting audiences deliver at acceptable CPL, while broad prospecting "
        "is dragging qual rate below target. A creative refresh is overdue — the active set is 42 days old.\n\n"
        "Snapchat continues with zero SQL attribution this week. Recommend a 7-day pause to isolate whether "
        "the issue is audience quality or CRM pipeline attribution."
    ),
    "trends_30d": [
        {"date": f"2026-03-{d:02d}", "channel": ch, "spend": s, "leads": l, "cpl": round(s/l, 2) if l else None}
        for d, ch, s, l in [
            (26, "google_ads", 1820, 62), (26, "meta", 980, 31), (26, "snapchat", 420, 8),
            (27, "google_ads", 1950, 71), (27, "meta", 1020, 35), (27, "snapchat", 410, 7),
            (28, "google_ads", 2100, 78), (28, "meta", 1100, 38), (28, "snapchat", 430, 9),
            (29, "google_ads", 2200, 83), (29, "meta", 1050, 36), (29, "snapchat", 440, 8),
            (30, "google_ads", 2310, 85), (30, "meta", 1080, 37), (30, "snapchat", 450, 10),
            (31, "google_ads", 2050, 80), (31, "meta", 990,  33), (31, "snapchat", 420, 7),
        ]
    ] + [
        {"date": f"2026-04-{d:02d}", "channel": ch, "spend": s, "leads": l, "cpl": round(s/l, 2) if l else None}
        for d, ch, s, l in [
            (1,  "google_ads", 1900, 72), (1,  "meta", 950, 30), (1,  "snapchat", 400, 6),
            (5,  "google_ads", 2100, 79), (5,  "meta", 1010, 34), (5,  "snapchat", 430, 8),
            (10, "google_ads", 2250, 85), (10, "meta", 1060, 36), (10, "snapchat", 440, 9),
            (15, "google_ads", 2400, 90), (15, "meta", 1100, 39), (15, "snapchat", 460, 10),
            (20, "google_ads", 2350, 88), (20, "meta", 1080, 37), (20, "snapchat", 450, 9),
            (24, "google_ads", 2430, 87), (24, "meta", 1020, 35), (24, "snapchat", 440, 8),
        ]
    ],
    "windows": {
        "yesterday": [mock_channel, meta_channel],
        "last_7d":   [mock_channel, meta_channel],
        "last_30d":  [mock_channel, meta_channel],
    },
    "channels": [mock_channel, meta_channel],
    "decisions": [
        {"channel": "Google Ads", "action": "pause", "campaign": "Generic_KW_broad", "reason": "Zero leads, $480 spend this week."},
    ],
    "approvals_pending": [],
    "tasks_created": [
        "Google Ads — Pause Generic_KW_broad (zero leads, $480 spend)",
        "Meta — Refresh prospecting creative (42 days old, qual rate 9%)",
    ],
    "thresholds": {
        "cpl":  {"scale": 25, "acceptable": 35, "warning": 50},
        "cpql": {"scale": 150, "acceptable": 220, "warning": 300},
        "qual_rate_target": 0.15,
    },
}

if __name__ == "__main__":
    path = save_report(mock_report)
    print(f"Report saved → {path}")
    print(f"File size:     {path.stat().st_size / 1024:.0f} KB")
    import webbrowser
    webbrowser.open(path.as_uri())
