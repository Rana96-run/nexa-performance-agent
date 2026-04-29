"""
Phase 3 — New campaign recommendations based on 90-day data gaps.
Run: python scripts/create_recommendation_tasks.py
"""
import sys
sys.path.insert(0, r"D:\Nexa Performance Agent")
from dotenv import load_dotenv
load_dotenv(override=True)

from executors.asana import create_task, get_client
import asana as _asana

# Use "Paid Growth Command (2.0 Q1_26 Scale)" since campaigns_hub GID is stale
_CAMPAIGNS_HUB_GID = "1212809922478291"


def create_task_direct(title, description, channel="", asset_level="campaign", action="launch"):
    """Create task directly in Paid Growth Command project, bypassing project_key routing."""
    from executors.asana import _task_footer, ASANA_ASSIGNEE_GID
    from datetime import datetime, timedelta, timezone
    from cache.cache_manager import task_is_new, record_task

    task_type = "Recommendation"
    full_title = f"[{task_type} | Launch] {title}"

    if not task_is_new(full_title, "campaigns_hub"):
        from cache.cache_manager import get_task_gid
        existing = get_task_gid(full_title, "campaigns_hub")
        print(f"[asana] skipped duplicate: {full_title[:60]!r} -> gid={existing}")
        return existing

    riyadh = timezone(timedelta(hours=3))
    due_date = (datetime.now(riyadh) + timedelta(days=1)).strftime("%Y-%m-%d")
    full_description = description + _task_footer(channel, asset_level, action, task_type)

    client = get_client()
    tasks_api = _asana.TasksApi(client)
    task_data = {
        "name": full_title,
        "notes": full_description,
        "projects": [_CAMPAIGNS_HUB_GID],
        "due_on": due_date,
    }
    from config import ASANA_ASSIGNEE_GID
    if ASANA_ASSIGNEE_GID:
        task_data["assignee"] = ASANA_ASSIGNEE_GID
    try:
        task = tasks_api.create_task({"data": task_data}, {})
        gid = task["gid"]
        record_task(full_title, "campaigns_hub", gid)
        print(f"[asana] created recommendation: {full_title[:60]!r}  gid={gid}")
        return gid
    except _asana.rest.ApiException as e:
        print(f"[asana] error: {e}")
        return None

# ── Analysis of what is performing and what is missing ───────────────────────
#
# WHAT'S WORKING (scale zone):
#   Snapchat Retargeting — CPQL $9.96 (best performer)
#   Snapchat Bookkeeping/Broad — CPQL $34.32
#   Snapchat Prospecting/Interest iOS — CPQL $37.89
#
# WHAT EXISTS but not tested on other channels:
#   Bookkeeping: only on Snapchat. Missing on Meta (has only Invoice/Generic), TikTok, LinkedIn, Google
#   Retargeting: working great on Snapchat. No dedicated Meta Retargeting for Invoice, no TikTok Retargeting
#   Lookalike: on Meta for Generic/Branding. No Lookalike for Bookkeeping on Snapchat
#   No TikTok campaigns at all (token expired — data gap, but account exists)
#   No LinkedIn campaigns in BQ data (zero spend tracked)
#
# GAPS IDENTIFIED:
# 1. Meta_LeadGen_AR_Bookkeeping_Interests — Bookkeeping works on Snapchat, missing on Meta
# 2. Meta_LeadGen_AR_Bookkeeping_Retargeting — retargeting Bookkeeping prospects on Meta
# 3. Snapchat_LeadGen_AR_Invoice_Lookalike — no Lookalike audience on Snapchat for Invoice
# 4. Snapchat_LeadGen_AR_Bookkeeping_Lookalike — scale from Interests to Lookalike
# 5. TikTok_LeadGen_AR_Invoice_Interests — Invoice not on TikTok (account exists, no active campaigns)
# 6. TikTok_LeadGen_AR_Bookkeeping_Interests — Bookkeeping not on TikTok
# 7. Google_Search_AR_Bookkeeping_Broad — Bookkeeping has zero Google Search coverage
# 8. LinkedIn_Invoice — LinkedIn has zero tracked spend; B2B SaaS audience is native here

recommendations = [
    {
        "name": "Meta_LeadGen_AR_Bookkeeping_Interests",
        "channel": "meta",
        "why": (
            "Bookkeeping is performing in the scale zone on Snapchat (CPQL $34.32, CPL $18.93, 55% qual rate). "
            "Meta has no active Bookkeeping Interests campaign — only Invoice and Generic branding. "
            "Meta's interest targeting (accounting software, bookkeeping, small business owners in SA) "
            "should be tested against the same ICP that is converting on Snapchat."
        ),
        "budget": "$50/day to start",
        "bid": "HIGHEST_VOLUME (max leads)",
        "creative": "Arabic video creative repurposed from best-performing Snapchat Bookkeeping creative. "
                    "Test 2 variants: feature walkthrough + ROI/time-saving angle.",
    },
    {
        "name": "Meta_LeadGen_AR_Bookkeeping_Retargeting",
        "channel": "meta",
        "why": (
            "Snapchat Retargeting is the single best-performing campaign in the entire account (CPQL $9.96, CPL $3.85). "
            "There is NO Meta Retargeting campaign for Bookkeeping. Meta pixel should have a large retargeting pool "
            "from Bookkeeping landing page visitors and video viewers. This is likely the highest-ROI campaign to launch."
        ),
        "budget": "$30/day",
        "bid": "HIGHEST_VOLUME",
        "creative": "Short 15-second recap of Bookkeeping key features. Add social proof / customer testimonial if available.",
    },
    {
        "name": "Snapchat_LeadGen_AR_Invoice_Lookalike",
        "channel": "snapchat",
        "why": (
            "Snapchat Invoice campaigns do not have a Lookalike audience variant. "
            "Snapchat Retargeting (CPQL $9.96) and Interests/iOS (CPQL $37.89) are both performing. "
            "Lookalike from current Invoice converters should extend reach efficiently. "
            "Meta has Lookalike running (CPQL $76.77 — needs optimization) but Snapchat Lookalike is untested."
        ),
        "budget": "$60/day",
        "bid": "$16 (MAX_BID in Snapchat terms)",
        "creative": "Repurpose best-performing Invoice Interests creative. Test iOS-specific variant given iOS audience success.",
    },
    {
        "name": "Snapchat_LeadGen_AR_Bookkeeping_Lookalike",
        "channel": "snapchat",
        "why": (
            "Bookkeeping Broad (CPQL $34.32) and Bookkeeping Interests Trial (CPQL $44.87) are both working. "
            "There is no Lookalike audience for Bookkeeping on Snapchat. "
            "Building a Lookalike from existing Bookkeeping SQL converters should deliver better CPQL than Broad."
        ),
        "budget": "$50/day",
        "bid": "$16 MAX_BID",
        "creative": "Use same creative as Bookkeeping Broad — best-performing format. Test new variant after 14 days.",
    },
    {
        "name": "TikTok_LeadGen_AR_Invoice_Interests",
        "channel": "tiktok",
        "why": (
            "TikTok has an active ad account (ID 7565475813811093521) but ZERO campaigns tracked in BQ in the last 90 days. "
            "Invoice is the core product with the most spend on all other channels. "
            "TikTok's Saudi Arabia reach (Gen Z + millennial SMB owners) complements Snapchat's iOS-heavy audience. "
            "Start with Invoice Interests to establish baseline CPQL before expanding."
        ),
        "budget": "$100/day",
        "bid": "$16 (deep funnel, INITIATE_CHECKOUT event via CRM pixel — enforced)",
        "creative": "Short UGC-style video (15-30 sec), Arabic, showing Invoice pain point resolved. "
                    "TikTok native format — avoid polished corporate creative.",
    },
    {
        "name": "TikTok_LeadGen_AR_Bookkeeping_Interests",
        "channel": "tiktok",
        "why": (
            "Bookkeeping is the second best-performing product on Snapchat. "
            "TikTok Bookkeeping campaign does not exist. "
            "Given TikTok's deep funnel optimization (CRM pixel / INITIATE_CHECKOUT), "
            "the algorithm can be trained on SQL-quality signals from day 1. "
            "Launch alongside Invoice to compare product-level performance."
        ),
        "budget": "$80/day",
        "bid": "$16 deep funnel MAX_BID",
        "creative": "Arabic UGC walkthrough of Bookkeeping dashboard. Show time-saving vs manual Excel.",
    },
    {
        "name": "Google_Search_AR_Bookkeeping_Broad",
        "channel": "google_ads",
        "why": (
            "Google Search campaigns cover Invoice extensively (Search_E-invoice_AR, PMax_AR_Invoice_FiveSectors, etc.) "
            "but there is ZERO Google Search coverage for Bookkeeping. "
            "Bookkeeping is performing on Snapchat (scale zone). High-intent search queries like "
            "'برنامج محاسبة', 'برنامج دفاتر', 'نظام محاسبة للشركات' have no campaign capturing them. "
            "This is a missed opportunity for bottom-of-funnel Bookkeeping leads."
        ),
        "budget": "$60/day",
        "bid": "MAXIMIZE_CONVERSIONS (target CPA ~$50 to start)",
        "creative": "RSA headlines: focus on Qoyod Bookkeeping features, Saudi compliance, free trial. "
                    "3 Arabic headline variants + 2 English for AREN split test.",
    },
    {
        "name": "LinkedIn_Invoice",
        "channel": "linkedin",
        "why": (
            "LinkedIn has ZERO tracked spend in 90 days — the channel is completely untested in this period. "
            "LinkedIn's B2B targeting (Finance Managers, CFOs, Accountants, Business Owners in SA) "
            "is the most precise for Qoyod's ICP. Invoice is the flagship product. "
            "LinkedIn CPL is typically higher but CPQL should be lower given role-based targeting. "
            "Start with a Lead Gen Form campaign to capture SQLs directly on platform."
        ),
        "budget": "$20/day (LinkedIn minimum)",
        "bid": "CPC — automated delivery to start",
        "creative": "Sponsored Content: case study or ROI proof point. Arabic copy. "
                    "Lead Gen Form with 4 questions: Name, Phone, Company, Job Title.",
    },
]

print(f"Creating {len(recommendations)} recommendation tasks...")
created_gids = {}

for rec in recommendations:
    desc = (
        f"**Why this campaign is recommended:**\n{rec['why']}\n\n"
        f"**Suggested setup:**\n"
        f"- Naming: {rec['name']}\n"
        f"- Daily budget: {rec['budget']}\n"
        f"- Bid strategy: {rec['bid']}\n"
        f"- Creative approach: {rec['creative']}\n\n"
        f"**Expected outcome:**\nBased on similar campaigns already running, "
        f"CPQL in $25–$60 range after 14-day learning period. "
        f"Monitor daily and pause if CPQL exceeds $80 after $200 spend.\n\n"
        f"---\n"
        f"When approved, reply ✅ to this task and I will create the campaign automatically."
    )

    gid = create_task_direct(
        title=f"New Campaign Recommendation: {rec['name']}",
        description=desc,
        channel=rec["channel"],
        asset_level="campaign",
        action="launch",
    )
    created_gids[rec["name"]] = gid
    print(f"[task] {rec['name']}: gid={gid}")

print("\n=== ALL RECOMMENDATION TASKS CREATED ===")
import json
print(json.dumps(created_gids, indent=2))
