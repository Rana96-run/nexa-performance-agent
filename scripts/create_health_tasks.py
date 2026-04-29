"""
Phase 2 — Create Asana tasks from 90-day campaign health audit.
Run: python scripts/create_health_tasks.py
"""
import sys
sys.path.insert(0, r"D:\Nexa Performance Agent")
from dotenv import load_dotenv
load_dotenv(override=True)

from executors.asana import create_task
from datetime import date

# ── Health findings from the 90-day BQ audit ─────────────────────────────────
findings = [
    # SCALE candidates (CPQL < $40 and CPL < $20)
    {"channel": "snapchat", "campaign": "Snapchat_LeadGen_Retargeting_Instantform",
     "spend": 507.85, "hs_leads": 132, "sqls": 51, "cpl": 3.85, "cpql": 9.96, "qual_rate": 38.6, "action": "scale",
     "note": "CPQL $9.96 + CPL $3.85 both in scale zone. Raise budget 25%."},
    {"channel": "snapchat", "campaign": "Snapchat_Leadgen_Bookkeeping_Broad_iPohne_Instantform",
     "spend": 549.07, "hs_leads": 29, "sqls": 16, "cpl": 18.93, "cpql": 34.32, "qual_rate": 55.2, "action": "scale",
     "note": "CPQL $34.32 + CPL $18.93 both in scale zone. Raise budget 25%."},
    {"channel": "snapchat", "campaign": "Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v3",
     "spend": 2879.76, "hs_leads": 150, "sqls": 76, "cpl": 19.20, "cpql": 37.89, "qual_rate": 50.7, "action": "scale",
     "note": "CPQL $37.89 + CPL $19.20 both in scale zone. Raise budget 25%."},

    # OPTIMIZE candidates
    {"channel": "meta", "campaign": "Meta_LeadGen_Prospecting_Retargeting_BrandingEquity_Instantform",
     "spend": 3201.71, "hs_leads": 66, "sqls": 43, "cpl": 48.51, "cpql": 74.46, "qual_rate": 65.2, "action": "optimize",
     "note": "CPQL $74.46 in warning zone (>$65). Qual rate 65.2%. Investigate audience/creative quality before scaling."},
    {"channel": "meta", "campaign": "Meta_LeadGen_Prospecting_Lookalike_BrandingEquity_Instantform_",
     "spend": 2226.23, "hs_leads": 55, "sqls": 29, "cpl": 40.48, "cpql": 76.77, "qual_rate": 52.7, "action": "optimize",
     "note": "CPQL $76.77 in warning zone (>$65). Review audience quality and creative fatigue."},
    {"channel": "meta", "campaign": "Meta_Leadgen_Prospecting_Lookalike_CRMPixel_Instantform",
     "spend": 2463.15, "hs_leads": 107, "sqls": 29, "cpl": 23.02, "cpql": 84.94, "qual_rate": 27.1, "action": "optimize",
     "note": "CPQL $84.94 in pause zone. Qual rate only 27.1% (target 30%). WARNING: CPL $23.02 looks OK but CPQL is junk-level — do not scale on CPL alone. Fix audience targeting."},
    {"channel": "meta", "campaign": "Meta_LeadGen_Bookkeeping_Prospecting_Intersts_MaxmizeLeads_Instantform",
     "spend": 1933.06, "hs_leads": 52, "sqls": 21, "cpl": 37.17, "cpql": 92.05, "qual_rate": 40.4, "action": "optimize",
     "note": "CPQL $92.05 in pause zone. Qual rate 40.4%. Review Bookkeeping audience interests and landing page."},
    {"channel": "google_ads", "campaign": "PMax_AR_Invoice_FiveSectors",
     "spend": 12270.80, "hs_leads": 247, "sqls": 133, "cpl": 49.68, "cpql": 92.26, "qual_rate": 53.8, "action": "optimize",
     "note": "CPQL $92.26 in pause zone. Highest-spend campaign. Qual rate 53.8%. Investigate PMax asset groups — likely non-ICP sectors driving cheap leads."},
    {"channel": "google_ads", "campaign": "PMax_AR_Invoice",
     "spend": 4523.21, "hs_leads": 59, "sqls": 35, "cpl": 76.66, "cpql": 129.23, "qual_rate": 59.3, "action": "optimize",
     "note": "CPQL $129.23 in pause zone. Qual rate 59.3%. Review asset groups and audience signals."},
    {"channel": "google_ads", "campaign": "PMax_AR_Generic",
     "spend": 1318.81, "hs_leads": 53, "sqls": 9, "cpl": 24.88, "cpql": 146.53, "qual_rate": 17.0, "action": "optimize",
     "note": "CPQL $146.53 in pause zone. Qual rate only 17% — junk leads. WARNING: CPL $24.88 masks very low quality. Do not scale."},
    {"channel": "google_ads", "campaign": "Search_AR_Brand",
     "spend": 2142.78, "hs_leads": 42, "sqls": 18, "cpl": 51.02, "cpql": 119.04, "qual_rate": 42.9, "action": "optimize",
     "note": "CPQL $119.04 in pause zone. Brand search campaigns typically show lower qual rates. Review brand keyword list for non-ICP terms."},
    {"channel": "google_ads", "campaign": "Search_AR_Brand_v2",
     "spend": 1939.18, "hs_leads": 25, "sqls": 11, "cpl": 77.57, "cpql": 176.29, "qual_rate": 44.0, "action": "optimize",
     "note": "CPQL $176.29 — 2.2x the warning threshold. Investigate ad copy and landing page relevance."},
    {"channel": "meta", "campaign": "Meta_Conversion_Prospecting_Lookalike_Invoice_Websiteform",
     "spend": 493.01, "hs_leads": 9, "sqls": 5, "cpl": 54.78, "cpql": 98.60, "qual_rate": 55.6, "action": "optimize",
     "note": "CPQL $98.60 in pause zone. Small sample (9 leads). Check website form UTM tracking — low lead volume may indicate form drop-off."},
    {"channel": "meta", "campaign": "Meta_Conversion_Prospecting_Lookalike_Websiteform",
     "spend": 234.73, "hs_leads": 4, "sqls": 2, "cpl": 58.68, "cpql": 117.37, "qual_rate": 50.0, "action": "optimize",
     "note": "CPQL $117.37 in pause zone. Very small sample (4 leads). Attribution gap likely — verify pixel/UTM setup."},
    {"channel": "google_ads", "campaign": "Search_E-invoice_AR",
     "spend": 3571.12, "hs_leads": 105, "sqls": 54, "cpl": 34.01, "cpql": 66.13, "qual_rate": 51.4, "action": "optimize",
     "note": "CPQL $66.13 just above acceptable ($65). Monitor closely. 51% qual rate acceptable but trending toward warning."},

    # PAUSE candidates
    {"channel": "google_ads", "campaign": "Search_AR/EN_E-Invoice",
     "spend": 945.69, "hs_leads": 67, "sqls": 5, "cpl": 14.11, "cpql": 189.14, "qual_rate": 7.5, "action": "pause",
     "note": "CPQL $189.14 is 2.4x warning threshold. Qual rate only 7.5% — severe junk lead problem. WARNING: CPL $14.11 masks extremely poor quality. Pause immediately."},
    {"channel": "google_ads", "campaign": "PMax_AR_E-Invoice",
     "spend": 4585.15, "hs_leads": 113, "sqls": 22, "cpl": 40.58, "cpql": 208.42, "qual_rate": 19.5, "action": "pause",
     "note": "CPQL $208.42 is 2.6x warning threshold. Qual rate 19.5%. Spent $4,585 with poor conversion quality. Pause and audit PMax asset groups."},
    {"channel": "snapchat", "campaign": "Snapchat_LeadGen_Einvoice_Phase2_Prospecting_Interest_Instantform",
     "spend": 958.15, "hs_leads": 27, "sqls": 4, "cpl": 35.49, "cpql": 239.54, "qual_rate": 14.8, "action": "pause",
     "note": "CPQL $239.54 is 3x warning threshold. Qual rate 14.8%. E-Invoice Phase 2 on Snapchat is not converting qualified leads."},
    {"channel": "google_ads", "campaign": "Search_AR_ZATCA_Invoice",
     "spend": 1225.03, "hs_leads": 18, "sqls": 3, "cpl": 68.06, "cpql": 408.34, "qual_rate": 16.7, "action": "pause",
     "note": "CPQL $408.34 is 5.1x warning threshold. ZATCA-specific search terms attracting consultants/accountants, not SMB owners. Pause and review keyword intent."},
    {"channel": "google_ads", "campaign": "Search_AR_Qflavours_Feature (Acc1)",
     "spend": 913.54, "hs_leads": 15, "sqls": 2, "cpl": 60.90, "cpql": 456.77, "qual_rate": 13.3, "action": "pause",
     "note": "CPQL $456.77 is 5.7x warning threshold. Qflavours Feature search is not generating qualified restaurant/F&B leads. Pause and review intent."},
    {"channel": "google_ads", "campaign": "Search_AR_Qflavours_Competitor_Acc2 (ENABLED)",
     "spend": 1594.90, "hs_leads": 11, "sqls": 3, "cpl": 144.99, "cpql": 531.63, "qual_rate": 27.3, "action": "pause",
     "note": "CPQL $531.63 is 6.6x warning threshold. Competitor terms for Qflavours are extremely expensive per SQL. Pause and review competitor strategy."},
    {"channel": "google_ads", "campaign": "Traffic_ImpressionShare_Search_Invoice",
     "spend": 740.90, "hs_leads": 8, "sqls": 1, "cpl": 92.61, "cpql": 740.90, "qual_rate": 12.5, "action": "pause",
     "note": "CPQL $740.90 — 9.3x warning threshold. Traffic/impression-share objective campaigns rarely convert at SQL level. Pause immediately."},
    {"channel": "google_ads", "campaign": "Search_AR_Generic_v2",
     "spend": 400.74, "hs_leads": 1, "sqls": 1, "cpl": 400.74, "cpql": 400.74, "qual_rate": 100.0, "action": "pause",
     "note": "CPQL $400.74 — only 1 lead in 90 days on $400 spend. Statistically insufficient volume — pause or merge with Search_AR_Generic."},
]

# ── Attribution gap campaigns (spend >= $100, zero HubSpot leads in BQ health data) ──
attribution_gaps = [
    {"channel": "snapchat", "campaign": " Snapchat_LeadGen_Invoice_Prospecting_Broad_Instantform",
     "spend": 174.93, "note": "Leading space in campaign name may break UTM matching. Verify campaign name in HubSpot UTM data."},
    {"channel": "snapchat", "campaign": "Snapchat_LeadGen_Qflavours_Prospecting_Intersts_Instatform",
     "spend": 125.04, "note": "No HubSpot leads attributed in 90 days. Typo in name ('Intersts', 'Instatform') may indicate UTM misconfiguration."},
    {"channel": "snapchat", "campaign": "Snapchat_Awareness_Prospecting_Broad_BrandEquity_Website",
     "spend": 66.89, "note": "Awareness campaign — leads expected via website form. Verify UTM tracking on landing page."},
    {"channel": "google_ads", "campaign": "ImpressionShare_Search_AR_Invoice (acc2, ENABLED)",
     "spend": 1161.75, "sqls": 0, "note": "Spent $1,162 with ZERO SQLs. High impression-share spend with no HubSpot conversion. Likely UTM mismatch or non-converting traffic objective."},
    {"channel": "google_ads", "campaign": "Search_AR_Qflavours_Feature (acc1, PAUSED)",
     "spend": 482.45, "sqls": 0, "note": "Spent $482 with 0 SQLs. Paused but had spend in window. Verify Qflavours lead routing in HubSpot."},
    {"channel": "google_ads", "campaign": "Search_AR_Qflavours_Competitor (acc2, PAUSED)",
     "spend": 590.89, "sqls": 0, "note": "Spent $591 with 0 SQLs. Competitor terms for Qflavours not driving qualified leads."},
    {"channel": "google_ads", "campaign": "Search_AR_Qflavours_Feature_Acc2 (PAUSED)",
     "spend": 439.32, "sqls": 0, "note": "Spent $439 with 0 SQLs. Check if UTM utm_campaign matches HubSpot source tracking."},
    {"channel": "google_ads", "campaign": "WebsiteTraffic_Search_AR_Invoice",
     "spend": 746.14, "sqls": 0, "note": "Spent $746 with only 1 HubSpot lead total (0 SQLs). Traffic objective campaigns not tracked in HubSpot. Verify conversion action setup."},
    {"channel": "meta", "campaign": "Meta_LeadGen_E-Invoice_Phase2_Retargeting_Instantform",
     "spend": 212.65, "sqls": 0, "note": "Spent $213 with 13 Meta leads but ZERO SQLs attributed. Retargeting lead form may not be syncing to HubSpot. Verify Meta lead sync webhook."},
]

print("=== FINDINGS SUMMARY ===")
scale_f = [f for f in findings if f["action"] == "scale"]
optimize_f = [f for f in findings if f["action"] == "optimize"]
pause_f = [f for f in findings if f["action"] == "pause"]
print(f"Scale: {len(scale_f)}, Optimize: {len(optimize_f)}, Pause: {len(pause_f)}, Attribution gaps: {len(attribution_gaps)}")

# ── Create Asana tasks ────────────────────────────────────────────────────────
created_gids = {}

# GROUP 1: Scale candidates (one combined task)
if scale_f:
    lines = ["The following campaigns are in the scale zone (CPQL < $40, CPL < $20) over the last 90 days. Recommended action: raise daily budget by 25%.\n"]
    for f in scale_f:
        lines.append(f"- **SCALE: {f['channel'].upper()} — {f['campaign']}**")
        lines.append(f"  Spend: ${f['spend']:,.2f} | CPQL: ${f['cpql']:.2f} | CPL: ${f['cpl']:.2f} | Qual Rate: {f['qual_rate']:.1f}%")
        lines.append(f"  Note: {f['note']}")
        lines.append("")

    gid = create_task(
        title="90-Day Campaign Health Review: Scale Candidates",
        description="\n".join(lines),
        project_key="optimization",
        task_type="Direct Log",
        channel="snapchat",  # Most scale candidates are Snapchat
        asset_level="campaign",
        action="scale",
    )
    created_gids["scale_all"] = gid
    print(f"[task] Scale group created: gid={gid}")

# GROUP 2: Optimize — one task per channel
from collections import defaultdict
optimize_by_channel = defaultdict(list)
for f in optimize_f:
    optimize_by_channel[f["channel"]].append(f)

for channel, items in optimize_by_channel.items():
    lines = [f"The following {channel.upper()} campaigns need optimization. CPQL in warning or pause zone — do not scale until resolved.\n"]
    for f in items:
        lines.append(f"- **{f['campaign']}**")
        lines.append(f"  Spend: ${f['spend']:,.2f} | CPQL: ${f['cpql']:.2f} | CPL: ${f['cpl']:.2f} | Qual Rate: {f['qual_rate']:.1f}%")
        lines.append(f"  Action: {f['note']}")
        lines.append("")

    gid = create_task(
        title=f"90-Day Campaign Health Review: Needs Optimization — {channel.upper()}",
        description="\n".join(lines),
        project_key="optimization",
        task_type="Recommendation",
        channel=channel,
        asset_level="campaign",
        action="optimize",
    )
    created_gids[f"optimize_{channel}"] = gid
    print(f"[task] Optimize {channel} created: gid={gid}")

# GROUP 3: Pause candidates (one combined task)
if pause_f:
    lines = ["The following campaigns have CPQL 3x+ above the warning threshold ($80). Recommended action: pause and investigate.\n"]
    for f in pause_f:
        cpql_mult = f['cpql'] / 80
        lines.append(f"- **PAUSE: {f['channel'].upper()} — {f['campaign']}**")
        lines.append(f"  Spend: ${f['spend']:,.2f} | CPQL: ${f['cpql']:.2f} ({cpql_mult:.1f}x warning) | CPL: ${f['cpl']:.2f} | Qual Rate: {f['qual_rate']:.1f}%")
        lines.append(f"  Note: {f['note']}")
        lines.append("")

    gid = create_task(
        title="90-Day Campaign Health Review: Pause Candidates",
        description="\n".join(lines),
        project_key="optimization",
        task_type="Direct Log",
        channel="google_ads",  # Most pauses are Google
        asset_level="campaign",
        action="pause",
    )
    created_gids["pause_all"] = gid
    print(f"[task] Pause group created: gid={gid}")

# GROUP 4: Attribution gaps (one task per campaign with spend >= $100)
for gap in attribution_gaps:
    if gap["spend"] < 100:
        continue
    gid = create_task(
        title=f"UTM Attribution Gap — {gap['channel'].upper()}: {gap['campaign'].strip()}",
        description=(
            f"This campaign spent ${gap['spend']:,.2f} in the last 90 days with no HubSpot leads attributed.\n\n"
            f"**Issue:** {gap['note']}\n\n"
            f"**Action required:**\n"
            f"1. Verify utm_campaign value matches the campaign name in HubSpot Lead Module\n"
            f"2. Check that lead form / pixel is firing correctly\n"
            f"3. Confirm HubSpot webhook / CRM sync is active for this channel\n"
            f"4. If UTM mismatch found, update the campaign URL and re-test\n"
        ),
        project_key="optimization",
        task_type="Recommendation",
        channel=gap["channel"],
        asset_level="tracking",
        action="fix",
    )
    created_gids[f"gap_{gap['channel']}_{gap['campaign'][:30]}"] = gid
    print(f"[task] Attribution gap task created for {gap['channel']} / {gap['campaign'][:50]}: gid={gid}")

print("\n=== ALL TASKS CREATED ===")
import json
print(json.dumps(created_gids, indent=2))
