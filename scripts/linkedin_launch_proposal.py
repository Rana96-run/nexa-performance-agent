"""
Build the LinkedIn launch proposal as an Asana task.

Inputs (from BQ):
- LinkedIn has been dark for 90+ days (0 spend, only 2 organic-attributed leads)
- Best-converting audiences across other channels (qual_rate signal)
- Deal-value distribution by source (where the high-value deals come from)

Output:
- ONE detailed Asana task in LinkedIn Ads Optimization > Campaign section
- Foundational task to re-mint LinkedIn token with proper scopes
- HubSpot segment-list spec for the lookalike seed audience
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from executors.asana import create_task

# ─── 1. LinkedIn launch proposal ─────────────────────────────────────────────
proposal = """
LinkedIn has been dark since ~Jan 2026 (0 spend, only 2 organic-attributed leads in the last 90 days). Recommend a fresh 4-week pilot.

**WHY LINKEDIN NOW**
- Last 60d: Offline + Other channels closed $913K in deals (avg $1,700/deal) — these are sales-led, finance-manager / SMB-owner conversations
- Google Ads: 963 deals at $366 avg — high volume, low ticket
- Meta Ads: 51 deals at $330 avg — same pattern
- LinkedIn natively reaches the people closing the high-ticket deals: CFO, Finance Manager, Accountant, SMB Owner. The expected CPL is higher (LinkedIn norm: $80–$150) but qualified-lead value justifies it.

---

**1. AUDIENCE STRATEGY**

3 audience tiers (one campaign each):

**A. Lookalike seed — Won-deal audience**
- Source: HubSpot dynamic list "Won deals — paid + offline (last 12 months)"
- Filter: pipeline_stage = closedwon AND amount_won > 1000 (avoid in-app micro-purchases)
- Sync to LinkedIn as "Matched Audience" → use as 1% lookalike seed
- This is THE audience LinkedIn is built for — Saudi B2B decision makers similar to people who actually paid

**B. Job-function targeting — Finance & Accounting**
- Country: Saudi Arabia
- Industries: Construction, Retail, F&B, Real Estate, Professional Services, Manufacturing (the verticals where Google PMax converts at 64-75% qual rate)
- Job functions: Accounting, Finance, Operations, Information Technology, Administrative
- Seniority: Manager, Director, Owner, CXO, VP
- Company size: 10–500 employees (SMB sweet spot)
- Skills: Bookkeeping, Accounting, ERP, Financial Reporting, VAT, Tax Compliance

**C. Retargeting — Website visitors + matched contacts**
- Source 1: LinkedIn Insight Tag visitors (last 90d)
- Source 2: HubSpot list "Disqualified - bad timing" (those who showed interest but timing wasn't right; re-engage 60d+)
- Source 3: HubSpot list "Open leads, no contact in 14 days" (sales handoff gap)

---

**2. CAMPAIGN STRUCTURE**

Campaign Group: "Qoyod Q2 2026 Launch"

| Campaign | Audience | Objective | Budget/day | Daily Budget Cap |
|---|---|---|---|---|
| LI_Lookalike_Seed_Q2 | A. Won-deal lookalike | Lead Gen (Lead Gen Form) | $40 | $50 |
| LI_FinanceManagers_KSA | B. Job-function targeting | Lead Gen (Lead Gen Form) | $40 | $50 |
| LI_Retargeting_v1 | C. Retargeting | Lead Gen (Lead Gen Form) | $25 | $30 |

**Total daily budget: $105/day (~$3,150/month) for the pilot.**

Why all three on Lead Gen Form (not website conversion):
- LinkedIn LGF auto-fills name, email, job title, company → 30%+ form completion rate vs. 8–12% for website forms
- Removes the friction step of redirecting to qoyod.com
- Maps cleanly to HubSpot via the existing Zapier integration

---

**3. BIDDING**

Pilot: **Manual CPL bidding** with a hard cap.

| Campaign | Initial bid | Why |
|---|---|---|
| LI_Lookalike_Seed_Q2 | $90 max CPL | Highest-intent audience; willing to pay premium |
| LI_FinanceManagers_KSA | $75 max CPL | Cold targeting; need lower bid to discover |
| LI_Retargeting_v1 | $60 max CPL | Warm audience; cheaper |

Switch to "Maximize Leads" bidding only after each campaign has 50+ conversions and the CPL is stable. Manual first → understand the auction before we hand control to LinkedIn's algorithm.

---

**4. CREATIVE — what's been winning elsewhere, translated for LinkedIn**

Best-performing patterns from Meta/Snap (last 30d, 55%+ qualification rate):
- **Retargeting + Branding equity** = highest qual rate (Meta_LeadGen_Retargeting_PageEngagement_BrandingEquity 71%)
- **Vertical-specific messaging** wins on Google PMax (Services 75%, RealEstate 65%, Retail 64%)
- **E-Invoice topic** is the dominant winner (Google_Pmax_E-Invoice_Phase2: 167 leads / 99 qual / 59% rate)

Recommended LinkedIn creative mix:

**Image ads (3 variants)**
- "Compliance done in 5 minutes" — solo-image, ZATCA-aligned, calm professional voice
- "How [retail / F&B / services] owners run their books in 2026" — vertical-tailored
- Customer logo wall (with permission) — social proof for B2B trust

**Video ads (2 variants, 15–30s)**
- "Day in the life of a Qoyod-using finance manager" — UGC style
- E-invoice demo — actual screen capture, no narration, just captions in Arabic + English

Sizes per creative:
- Single image: 1200×628 (1.91:1) and 1080×1080 (square)
- Video: 16:9 landscape and 1:1 square

Brief Donia in Asana > Optimization once approved.

---

**5. LEAD GEN FORM STRUCTURE**

Form fields (in order — fewer fields = higher completion rate):
1. **Full name** (auto-filled by LinkedIn)
2. **Work email** (auto-filled — DO NOT use personal email pre-fill; quality drops)
3. **Company name** (auto-filled)
4. **Job title** (auto-filled)
5. **Phone** (manual — but LinkedIn often pre-fills if user has it on profile)
6. **Custom: Company size** (dropdown: 1-10 / 11-50 / 51-200 / 200+)
7. **Custom: Primary need** (dropdown: E-invoicing / Bookkeeping / VAT / POS / Multiple)

Privacy policy URL: https://qoyod.com/privacy
Thank-you message: "Thanks {first_name}. Our team will reach out within 24 hours."

**HubSpot routing:**
- Form submission → Zapier → HubSpot Contact create with `qoyod_source = "LinkedIn Ads"` and `lead_utm_campaign = {campaign_name}`
- The agent now correctly attributes via the channel_inference fallback chain
- Sales handoff: assign to "LinkedIn Pilot" Asana queue, SLA 24h

---

**6. TRACKING**

- Install LinkedIn Insight Tag on qoyod.com (if not already)
- Set up Conversion API (CAPI) sendback for `lead`, `qualified`, `closedwon` events from HubSpot → LinkedIn
- UTM tagging: `utm_source=linkedin&utm_medium=cpl&utm_campaign={campaign_name}&utm_content={ad_name}&utm_audience={audience_name}`
- The agent's daily nightly cycle will automatically pick up LinkedIn data once campaigns are live (collector already wired into `reporting_scheduler`)

---

**7. SUCCESS CRITERIA (4-week pilot)**

| Week | Goal |
|---|---|
| 1 | All 3 campaigns live, 1 ad set per campaign, no IS optimization yet |
| 2 | 50+ leads total. Identify which audience converts best on qualification rate |
| 3 | Pause underperforming, scale winner (raise budget +30%) |
| 4 | Decide: continue, scale further, or pause and re-brief |

**Kill switches** (per Media Buyer playbook):
- Any campaign with CPL > $150 for 4+ days → pause
- Any campaign with CPQL > $250 for 4+ days → pause
- All 3 campaigns under $50 CPL → scale across the board

---

**WHAT YOU NEED TO DO**
1. Approve this plan or push back on what's wrong
2. Confirm budget ($3,150/month for 4-week pilot = $4,200 total, with 33% buffer)
3. The agent will create the HubSpot segment lists once you approve (separate Asana task tracks this)
4. The agent CANNOT create LinkedIn campaigns directly (requires write-scope OAuth, currently we have read-only). Once spec is approved I'll prepare the campaign objects manually OR we can re-mint LinkedIn token with rw_ads scope.
"""

gid = create_task(
    title="LinkedIn — Q2 2026 launch proposal (3 campaigns, $3,150/mo pilot)",
    description=proposal,
    project_key="optimization",
    task_type="Recommendation",
    channel="linkedin",
    asset_level="campaign",
    action="launch",
)
print(f"LinkedIn launch proposal: gid={gid}")


# ─── 2. HubSpot segment lists task (paired with the proposal) ────────────────
seg_spec = """
For the LinkedIn launch (and ad-platform CAPI seeding generally), the agent needs to create these HubSpot lists. These are also useful for retargeting and exclusion across ALL paid channels.

**Segment 1 — "LIST_won_deals_lookalike_seed"** (DYNAMIC)
- Filter: hs_lifecyclestage = customer OR (deal pipeline_stage = closedwon AND amount_won >= 1000)
- Use case: Lookalike seed for LinkedIn, Meta Custom Audience, Google Customer Match
- Update cadence: dynamic (rebuild weekly)
- Export schedule: nightly to LinkedIn Matched Audience + Meta CAPI

**Segment 2 — "LIST_disqualified_bad_timing_60d"** (DYNAMIC)
- Filter: hs_lifecyclestage = lead AND lead_status = disqualified AND disqualification_reason CONTAINS "timing" AND time_since_disqualified > 60 days
- Use case: Re-engagement audience for LinkedIn, Meta retargeting
- Update cadence: dynamic (rebuild daily)

**Segment 3 — "LIST_qualified_no_contact_14d"** (DYNAMIC)
- Filter: lead_status = qualified AND days_since_last_activity > 14
- Use case: Sales handoff gap alerting; can also be used as a retargeting pool
- Update cadence: dynamic

**Segment 4 — "LIST_high_intent_non_converting"** (DYNAMIC)
- Filter: form_submission_count >= 2 AND hs_lifecyclestage NOT IN (customer, evangelist) AND time_since_last_form_submission < 30 days
- Use case: Hot retargeting pool — they engaged but didn't qualify; show them a different message

**Segment 5 — "LIST_existing_customers_exclude"** (DYNAMIC)
- Filter: hs_lifecyclestage IN (customer, evangelist)
- Use case: EXCLUSION list for all paid campaigns (don't pay to acquire someone we already have)
- Push to: LinkedIn (exclude), Meta (exclude), Google Customer Match (exclude)

**WHAT YOU NEED TO DO**
- Approve which of these 5 to start with (recommend 1 + 5 first as foundational, then 2-4 as needed)
- Once approved, the executors/hubspot_lists.py task will create them via HubSpot Lists v3 API and set up the nightly export to ad platforms
"""

gid2 = create_task(
    title="HubSpot — Create 5 segment lists for LinkedIn launch + paid retargeting",
    description=seg_spec,
    project_key="daily_activity",
    task_type="Recommendation",
    channel="hubspot",
    asset_level="audience",
    action="launch",
)
print(f"Segment lists spec: gid={gid2}")


# ─── 3. Re-mint LinkedIn token with proper scopes ────────────────────────────
gid3 = create_task(
    title="Re-mint LinkedIn OAuth token — rw_ads scope needed for campaign create",
    description=(
        "Current LinkedIn token only has read-only ads scope. The agent can pull "
        "analytics but CANNOT create or pause campaigns programmatically.\n\n"
        "**To unlock auto-create:**\n"
        "1. Go to LinkedIn Developer Portal → our app → Auth tab\n"
        "2. Add scopes: rw_ads, rw_organization_admin\n"
        "3. Run: `python scripts/linkedin_oauth.py` to mint new token\n"
        "4. Paste returned access_token + refresh_token into Railway env\n"
        "   (variables: LI_ACCESS_TOKEN, LI_REFRESH_TOKEN)\n"
        "5. The nightly LinkedIn audit will now pull live campaign list and "
        "the future executors/linkedin_campaign.py can auto-pause underperformers.\n\n"
        "Until this is done, LinkedIn campaign management is fully manual via UI. "
        "This is OK for the launch pilot but not scalable for ongoing optimisation."
    ),
    project_key="daily_activity",
    task_type="Build",
    channel="linkedin",
    asset_level="tracking",
    action="fix",
)
print(f"LinkedIn token re-mint: gid={gid3}")
