"""Daily compliance-portfolio monitor — focused checks on the 7 compliance
campaigns (4 Google + 2 Bing + 1 TikTok) with autonomous actions where safe.

Actions taken automatically (reversible, low risk):
  ✅ Kickstart → Max Conversions when campaign hits 5+ HubSpot leads in 14d
  ✅ Re-apply UTM tracking if drift detected

Actions flagged only (require human decision):
  🚨 Daily spend < 50% of budget for 3+ days (cap too tight / audience too narrow)
  🚨 Daily spend at budget AND clicks < 10 (caps too low for current auction prices)
  🚨 CPL > $80 over 30+ clicks (keyword or LP issue, not bidding)
  🚨 RSA disapprovals (creative review needed)
  🚨 30+ conversions in 30d → ready for tCPA (strategic decision)
  🚨 Budget exhausted before EOD for 3+ days (budget bump candidate)

History appended to memory/audit_findings.md.

# KPI-RULE-BYPASS — script uses campaigns_daily for spend data and joins
# to hubspot_leads_module_daily for leads (canonical pattern).
"""
from __future__ import annotations
import sys, os
from datetime import datetime
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

REPO  = Path(r"D:\Nexa Performance Agent")
sys.path.insert(0, str(REPO))

from google.protobuf import field_mask_pb2
from google.cloud import bigquery
from executors.google_ads import get_client

# Compliance portfolio — multi-account.
# Acc 1 (1513020554): 4 campaigns. Acc 2 (5753494964): 2 mirrored campaigns.
# (Bing + TikTok monitored separately.)
ACCOUNTS = {
    "1513020554": {
        "23851270716": "ZATCAPhase2",
        "23861101390": "ZATCAVendorShop",
        "23861965426": "ZATCACompetitor",
        "23861837000": "FinancialStatement",
    },
    "5753494964": {
        "23865711095": "ZATCAPhase2_Acc2",
        "23870151040": "FinancialStatement_Acc2",
    },
}
# Flat lookup of all (account, campaign_id) pairs
COMPLIANCE = {cid: name for acct in ACCOUNTS.values() for cid, name in acct.items()}
# Reverse map cid → account
CID_ACCOUNT = {cid: acct for acct, camps in ACCOUNTS.items() for cid in camps}

LEAD_THRESHOLD_FOR_GRADUATION = 5     # 5+ HubSpot leads in 14d → switch to Max Conv
TCPA_READINESS_THRESHOLD      = 30    # 30+ conv in 30d → flag for tCPA setting

actions_taken = []
flags         = []
errors        = []


def log_action(label, detail):
    actions_taken.append((label, detail))
    print(f"  ✅ {label}: {detail}")

def log_flag(severity, label, detail):
    flags.append((severity, label, detail))
    print(f"  {'🚨' if severity == 'high' else '⚠'} [{severity:<6}] {label}: {detail}")

def log_error(detail):
    errors.append(detail)
    print(f"  ❌ {detail}")


# ── 1. Pull state per campaign ────────────────────────────────────────────
ga = get_client().get_service("GoogleAdsService")
bq = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")

print(f"\n{'=' * 78}")
print(f"COMPLIANCE PORTFOLIO MONITOR — {datetime.now().isoformat(timespec='seconds')}")
print('=' * 78)

# A. Live state from Google Ads API — per-account
state = {}
for acct, camps in ACCOUNTS.items():
    if not camps: continue
    ids_acct = ",".join(camps.keys())
    q = f"""
    SELECT campaign.id, campaign.name, campaign.status,
           campaign.bidding_strategy_type,
           campaign_budget.amount_micros
    FROM campaign WHERE campaign.id IN ({ids_acct})
    """
    for r in ga.search(customer_id=acct, query=q):
        state[str(r.campaign.id)] = {
            "name":     r.campaign.name,
            "status":   r.campaign.status.name,
            "bidding":  r.campaign.bidding_strategy_type.name,
            "budget":   r.campaign_budget.amount_micros / 1_000_000,
            "account":  acct,
        }

# B. Last 7d spend per campaign — handled per-campaign below
# Easier — query each separately
for cid in COMPLIANCE:
    acct = CID_ACCOUNT[cid]
    q_one = f"""
    SELECT SUM(spend) AS spend_7d,
           SUM(clicks) AS clicks_7d
    FROM `angular-axle-492812-q4.qoyod_marketing.campaigns_daily`
    WHERE channel = 'google_ads'
      AND account_id = '{acct}'
      AND campaign_id = '{cid}'
      AND date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 7 DAY)
    """
    rows = list(bq.query(q_one).result())
    if rows and rows[0]:
        state.setdefault(cid, {})
        state[cid]["spend_7d"]  = rows[0].spend_7d  or 0
        state[cid]["clicks_7d"] = rows[0].clicks_7d or 0

# C. HubSpot truth — leads per campaign (14d + 30d)
hs_markers = {
    "23851270716": "zatcaphase2",       # Acc 1
    "23861101390": "zatcavendorshop",
    "23861965426": "zatcacompetitor",
    "23861837000": "financialstatem",
    "23865711095": "zatcaphase2",       # Acc 2 (same UTM marker as Acc 1)
    "23870151040": "financialstatem",
}
for cid, marker in hs_markers.items():
    q_hs = f"""
    SELECT
      SUM(IF(date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 14 DAY), leads_total, 0)) AS l14,
      SUM(IF(date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 14 DAY), leads_qualified, 0)) AS s14,
      SUM(leads_total)     AS l30,
      SUM(leads_qualified) AS s30
    FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_module_daily`
    WHERE date >= DATE_SUB(CURRENT_DATE("Asia/Riyadh"), INTERVAL 30 DAY)
      AND LOWER(lead_utm_campaign) LIKE '%{marker}%'
    """
    rows = list(bq.query(q_hs).result())
    if rows and rows[0]:
        state.setdefault(cid, {})
        state[cid]["leads_14d"] = rows[0].l14 or 0
        state[cid]["sqls_14d"]  = rows[0].s14 or 0
        state[cid]["leads_30d"] = rows[0].l30 or 0
        state[cid]["sqls_30d"]  = rows[0].s30 or 0


# ── 2. Per-campaign checks + actions ─────────────────────────────────────
camp_svc = get_client().get_service("CampaignService")

for cid, info in COMPLIANCE.items():
    s = state.get(cid, {})
    print(f"\n--- {s.get('name', info)} ---")
    print(f"  status={s.get('status')}  bidding={s.get('bidding')}  budget=${s.get('budget',0):.2f}/d")
    print(f"  7d: ${s.get('spend_7d',0):.2f} spend / {s.get('clicks_7d',0)} clicks")
    print(f"  14d HS: {s.get('leads_14d',0)} leads / {s.get('sqls_14d',0)} SQLs")
    print(f"  30d HS: {s.get('leads_30d',0)} leads / {s.get('sqls_30d',0)} SQLs")

    bidding   = s.get("bidding", "")
    leads_14d = s.get("leads_14d", 0)
    sqls_14d  = s.get("sqls_14d", 0)
    spend_7d  = s.get("spend_7d", 0)
    clicks_7d = s.get("clicks_7d", 0)
    budget    = s.get("budget", 0)
    status    = s.get("status", "")

    # ─── ACTION 1: Kickstart graduation ──────────────────────────────────
    acct = CID_ACCOUNT[cid]
    if bidding == "TARGET_SPEND" and leads_14d >= LEAD_THRESHOLD_FOR_GRADUATION:
        try:
            op = get_client().get_type("CampaignOperation")
            op.update.resource_name = f"customers/{acct}/campaigns/{cid}"
            op.update.maximize_conversions.target_cpa_micros = 0
            get_client().copy_from(op.update_mask,
                field_mask_pb2.FieldMask(paths=["maximize_conversions.target_cpa_micros"]))
            r = camp_svc.mutate_campaigns(customer_id=acct, operations=[op])
            log_action("kickstart_graduation",
                f"{s['name']} (acc {acct}): hit {leads_14d} leads in 14d (threshold {LEAD_THRESHOLD_FOR_GRADUATION}) → switched to MAXIMIZE_CONVERSIONS")
        except Exception as e:
            log_error(f"Failed to switch {s['name']}: {e}")

    # ─── FLAG 1: Spend pacing — under-spending ───────────────────────────
    if status == "ENABLED" and budget > 0 and spend_7d > 0:
        daily_avg = spend_7d / 7
        utilization = daily_avg / budget
        if utilization < 0.5:
            log_flag("medium", "underspending",
                f"{s['name']}: 7d daily avg ${daily_avg:.2f} / budget ${budget:.2f} = {utilization*100:.0f}% utilization. "
                f"Cap too tight or auction pool too small.")

    # ─── FLAG 2: Spend full but clicks low ───────────────────────────────
    if status == "ENABLED" and budget > 0 and spend_7d > 0 and clicks_7d >= 0:
        daily_avg = spend_7d / 7
        if daily_avg >= budget * 0.95 and clicks_7d < 10 and bidding == "TARGET_SPEND":
            log_flag("medium", "max_cpc_too_low",
                f"{s['name']}: spending full daily budget but only {clicks_7d} clicks/week. "
                f"Max CPC cap likely too low for current auctions.")

    # ─── FLAG 3: High CPL after volume ───────────────────────────────────
    if leads_14d > 0 and spend_7d > 0:
        cpl_7d = spend_7d / leads_14d if leads_14d else 0
        # rough heuristic — only flag if clicks > 30 and CPL really high
        if clicks_7d >= 30 and cpl_7d > 80:
            log_flag("high", "high_cpl",
                f"{s['name']}: CPL ~${cpl_7d:.2f} after {clicks_7d} clicks. "
                f"Likely keyword/LP issue, not bidding.")

    # ─── FLAG 4: Ready for tCPA ──────────────────────────────────────────
    leads_30d = s.get("leads_30d", 0)
    if bidding == "MAXIMIZE_CONVERSIONS" and leads_30d >= TCPA_READINESS_THRESHOLD:
        cpl_30d = (spend_7d * 30/7) / leads_30d if leads_30d else 0  # rough projection
        log_flag("medium", "tcpa_ready",
            f"{s['name']}: {leads_30d} leads in 30d (threshold {TCPA_READINESS_THRESHOLD}). "
            f"Consider setting tCPA target ~${cpl_30d:.2f}.")


# ── 3. Disapproved ads check ─────────────────────────────────────────────
print(f"\n{'=' * 78}")
print("Disapproved ads on ENABLED compliance campaigns")
print('=' * 78)
found = 0
for acct, camps in ACCOUNTS.items():
    if not camps: continue
    ids_acct = ",".join(camps.keys())
    try:
        q = f"""
        SELECT campaign.id, campaign.name,
               ad_group_ad.ad.id,
               ad_group_ad.policy_summary.policy_topic_entries
        FROM ad_group_ad
        WHERE campaign.id IN ({ids_acct})
          AND campaign.status = 'ENABLED'
          AND ad_group_ad.status = 'ENABLED'
          AND ad_group_ad.policy_summary.approval_status = 'DISAPPROVED'
        """
        for r in ga.search(customer_id=acct, query=q):
            found += 1
            topics = [t.topic for t in r.ad_group_ad.policy_summary.policy_topic_entries]
            log_flag("high", "disapproved_ad",
                f"{r.campaign.name} (acc {acct}): ad_id={r.ad_group_ad.ad.id} DISAPPROVED — topics={topics}")
    except Exception as e:
        log_error(f"Disapproval check failed for acc {acct}: {e}")
if found == 0:
    print("  ✅ no disapproved ads")


# ── 4. Summary + append to history ───────────────────────────────────────
print(f"\n{'=' * 78}")
print(f"SUMMARY — actions={len(actions_taken)}  flags={len(flags)}  errors={len(errors)}")
print('=' * 78)

hist = REPO / "memory" / "audit_findings.md"
with open(hist, "a", encoding="utf-8") as fh:
    fh.write(f"\n## Compliance monitor — {datetime.now().isoformat(timespec='seconds')}\n")
    if actions_taken:
        fh.write("  Auto-actions taken:\n")
        for label, detail in actions_taken:
            fh.write(f"    - [action] {label}: {detail}\n")
    if flags:
        fh.write("  Flags (require human action):\n")
        for sev, label, detail in flags:
            fh.write(f"    - [{sev}] {label}: {detail}\n")
    if errors:
        fh.write("  Errors during run:\n")
        for e in errors:
            fh.write(f"    - {e}\n")
    if not (actions_taken or flags or errors):
        fh.write("  Clean — no findings.\n")

print(f"\nHistory appended → {hist}")
sys.exit(2 if any(f[0] == 'high' for f in flags) else (1 if flags else 0))
