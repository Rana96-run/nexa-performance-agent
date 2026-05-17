"""Create Asana drilldown tasks for campaigns with ad-level pause candidates.

One task per campaign, listing the top 5 worst ads (by reason severity + spend).
The team reviews + approves via Slack ✅ in the nightly #approvals digest;
these tasks just surface the work in Asana.
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from analysers.campaign_health import _campaigns_with_ad_pause_candidates
from executors.asana import create_task
from collectors.bq_writer import get_client

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

cands = _campaigns_with_ad_pause_candidates(days=14)
print(f"Found {len(cands)} campaigns with ad-level pause candidates\n")

if not cands:
    print("Nothing to surface.")
    sys.exit(0)

# Look up campaign metadata (name + channel) in one query
camp_ids = list(cands.keys())
sql = f"""
SELECT campaign_id, ANY_VALUE(campaign_name) AS campaign_name,
       ANY_VALUE(channel) AS channel
FROM `{proj}.{ds}.campaigns_daily`
WHERE campaign_id IN UNNEST(@ids)
  AND date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
GROUP BY 1
"""
from google.cloud import bigquery
job = c.query(sql, job_config=bigquery.QueryJobConfig(
    query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", camp_ids)]
))
camp_meta = {str(r.campaign_id): (r.campaign_name, r.channel) for r in job.result()}

created = 0
for cid, ads in cands.items():
    name, channel = camp_meta.get(cid, (f"Campaign {cid}", "general"))

    # Sort: zero_conv worst, then high_cpl, then junk_lead; tiebreak by spend desc
    severity = lambda a: (
        0 if "zero_conv" in a["reasons"] else
        1 if "high_cpl"  in a["reasons"] else 2,
        -a["spend"],
    )
    top_ads = sorted(ads, key=severity)[:5]

    total_bad_spend = sum(a["spend"] for a in ads)
    body_lines = [
        f"Campaign hit pause-zone CPL but has {len(ads)} ad(s) eligible for ad-level pause.",
        f"Pause-precedence rule: clean up the bad ads FIRST — campaign-pause is blocked until then.",
        "",
        f"Total bad-ad spend (14d): ${total_bad_spend:.2f}",
        "",
        "Ads to pause (worst first):",
    ]
    for a in top_ads:
        reasons_str = ", ".join({
            "zero_conv": "zero conversions",
            "high_cpl":  "CPL > $50",
            "junk_lead": "junk leads ≥60%",
        }.get(r, r) for r in a["reasons"])
        cpl_str = f"CPL ${a['cpl']:.2f}" if a['cpl'] is not None else "no leads"
        body_lines.append(
            f"  • {a['ad_name']}  —  ${a['spend']:.0f} over {a['days']}d  "
            f"({cpl_str}, {reasons_str})"
        )

    body_lines += [
        "",
        "Action: pause each ad listed above via scripts/bulk_ads.py or the platform UI.",
        "Re-evaluate the campaign after 7 days — if CPL still > $50, escalate to campaign-pause.",
    ]
    description = "\n".join(body_lines)
    title = f"Pause bad ads first in {name}"

    gid = create_task(
        title=title,
        description=description,
        project_key="optimization",
        task_type="Recommendation",
        channel=channel,
        asset_level="ad",
        action="pause",
    )
    if gid:
        print(f"✓ Created task for {name} ({channel}): {gid}  ({len(top_ads)} ads, ${total_bad_spend:.0f} spend)")
        created += 1
    else:
        print(f"✗ Skipped {name} ({channel}) — duplicate or routing failure")

print(f"\n{created}/{len(cands)} drilldown tasks created.")
