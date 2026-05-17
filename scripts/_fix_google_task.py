"""Correct the misrouted Google Ads task to a keyword+LP review."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
import asana
from executors.asana import get_client

TASK_GID = "1214866740565892"  # [Pause] Pause bad ads first in ImpressionShare_Search_AR_Invoice

new_title = "[Recommendation | Drilldown] Review keywords + landing page in ImpressionShare_Search_AR_Invoice"
new_notes_lines = [
    "Search-channel optimization hierarchy: keyword → landing page → ad → campaign.",
    "For Google + Microsoft Ads, ad-level pause is the WRONG first step.",
    "",
    "Specific keywords flagged for pause in this campaign (14d):",
]
# Pull the actual keyword candidates for this campaign
from analysers.campaign_health import _campaigns_with_keyword_pause_candidates
kw_cands = _campaigns_with_keyword_pause_candidates(days=14)
# Look up campaign_id from name
from collectors.bq_writer import get_client
c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]
sql = f"""
SELECT DISTINCT campaign_id FROM `{proj}.{ds}.campaigns_daily`
WHERE LOWER(campaign_name) = 'impressionshare_search_ar_invoice'
LIMIT 5
"""
ids = [str(r.campaign_id) for r in c.query(sql).result()]
bad_kws = []
for cid in ids:
    bad_kws.extend(kw_cands.get(cid, []))

if bad_kws:
    bad_kws = sorted(bad_kws, key=lambda k: (0 if "zero_conv" in k["reasons"] else 1, -k["spend"]))
    for k in bad_kws[:5]:
        cpl_s = f"CPL ${k['cpl']:.2f}" if k['cpl'] else "no conversions"
        reasons_s = ", ".join({"zero_conv": "0 conv", "high_cpl": "CPL>$80"}.get(r, r) for r in k["reasons"])
        new_notes_lines.append(
            f"  • {k['keyword']}  in  {k['adgroup']}  —  ${k['spend']:.0f} over {k['days']}d  ({cpl_s}, {reasons_s})"
        )
else:
    new_notes_lines.append("  (no keyword candidates flagged — go straight to step 2)")

new_notes_lines += [
    "",
    "Investigation order:",
    "  1. Pause the keywords listed above (or run scripts/audit.py keywords to expand).",
    "  2. Visit the destination landing page for the campaign's main ad:",
    "     - Does the LP load fast (<3s)?",
    "     - Does the form actually submit?",
    "     - Is the message aligned with the keyword intent?",
    "     - LP issue → fix the LP, NOT the ad/keyword.",
    "  3. Only after keyword + LP cleanup, if the campaign still underperforms,",
    "     escalate to ad-level review or campaign-pause.",
    "",
    "Originally surfaced as ad-level pause (incorrect for search channels).",
    "Auto-corrected 2026-05-17.",
    "",
    "Created: 2026-05-17",
    "Due: 2026-05-18",
    "Priority: High",
    "Type: Recommendation",
    "Channel: google_ads",
    "Asset level: keyword",
    "Action: drilldown",
]
new_notes = "\n".join(new_notes_lines)

import requests
from config import ASANA_TOKEN
r = requests.put(
    f"https://app.asana.com/api/1.0/tasks/{TASK_GID}",
    headers={"Authorization": f"Bearer {ASANA_TOKEN}", "Content-Type": "application/json"},
    json={"data": {"name": new_title, "notes": new_notes}},
    timeout=15,
)
r.raise_for_status()
print(f"✓ Updated task {TASK_GID}")
print(f"  New title: {r.json()['data']['name']}")
