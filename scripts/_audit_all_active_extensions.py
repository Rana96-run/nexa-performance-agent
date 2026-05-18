"""Audit ALL active (ENABLED) campaigns across both Google Ads accounts —
list every campaign's sitelinks, callouts, structured snippets, and call
extensions. Flag whether each extension is tailored to its campaign or
inherited from generic account-level pool.

Goal: identify campaigns whose extensions are mismatched to their theme
(e.g., a Bookkeeping campaign with generic Invoice sitelinks)."""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from collections import defaultdict
from executors.google_ads import get_client

ACCOUNTS = ["1513020554", "5753494964"]

client = get_client()
ga     = client.get_service("GoogleAdsService")


def pull_active(account):
    """Return active campaigns + their per-campaign extension counts."""
    # 1. Active campaigns
    q1 = """
    SELECT campaign.id, campaign.name, campaign.status,
           campaign.advertising_channel_type,
           campaign_budget.amount_micros
    FROM campaign
    WHERE campaign.status = 'ENABLED'
    """
    campaigns = []
    for r in ga.search(customer_id=account, query=q1):
        campaigns.append({
            "id":      str(r.campaign.id),
            "name":    r.campaign.name,
            "channel": r.campaign.advertising_channel_type.name,
            "budget":  r.campaign_budget.amount_micros / 1_000_000,
            "exts":    {"SITELINK": [], "CALLOUT": [], "STRUCTURED_SNIPPET": [], "CALL": []},
        })

    if not campaigns:
        return []

    # 2. Pull extensions for those campaigns
    ids = ",".join(c["id"] for c in campaigns)
    q2 = f"""
    SELECT campaign.id,
           campaign_asset.field_type,
           asset.sitelink_asset.link_text,
           asset.callout_asset.callout_text,
           asset.structured_snippet_asset.header,
           asset.structured_snippet_asset.values,
           asset.call_asset.phone_number
    FROM campaign_asset
    WHERE campaign.id IN ({ids})
      AND campaign_asset.status = 'ENABLED'
      AND campaign_asset.field_type IN ('SITELINK','CALLOUT','STRUCTURED_SNIPPET','CALL')
    """
    by_cid = {c["id"]: c for c in campaigns}
    for r in ga.search(customer_id=account, query=q2):
        cid = str(r.campaign.id)
        if cid not in by_cid: continue
        ft  = r.campaign_asset.field_type.name
        a   = r.asset
        if ft == "SITELINK":
            by_cid[cid]["exts"]["SITELINK"].append(a.sitelink_asset.link_text)
        elif ft == "CALLOUT":
            by_cid[cid]["exts"]["CALLOUT"].append(a.callout_asset.callout_text)
        elif ft == "STRUCTURED_SNIPPET":
            h = a.structured_snippet_asset.header
            v = ", ".join(a.structured_snippet_asset.values)
            by_cid[cid]["exts"]["STRUCTURED_SNIPPET"].append(f"{h}: {v}")
        elif ft == "CALL":
            by_cid[cid]["exts"]["CALL"].append(a.call_asset.phone_number)

    return campaigns


# Run
all_data = {}
for acct in ACCOUNTS:
    print(f"\n{'=' * 80}")
    print(f"ACCOUNT {acct}")
    print('=' * 80)
    campaigns = pull_active(acct)
    if not campaigns:
        print("  (no enabled campaigns)")
        continue
    all_data[acct] = campaigns
    for c in campaigns:
        sl = len(c["exts"]["SITELINK"])
        co = len(c["exts"]["CALLOUT"])
        sn = len(c["exts"]["STRUCTURED_SNIPPET"])
        ca = len(c["exts"]["CALL"])
        coverage = f"SL={sl} CO={co} SN={sn} CA={ca}"
        flag = "" if (sl >= 4 and co >= 4) else " ⚠ thin"
        if sl == 0 and co == 0 and sn == 0:
            flag = " ❌ NO EXTENSIONS"
        print(f"\n  [{c['channel']:<15}] ${c['budget']:>5.0f}/d  {c['name'][:60]}")
        print(f"      ID={c['id']}  {coverage}{flag}")
        if sl: print(f"      SL: {' | '.join(c['exts']['SITELINK'][:6])}")
        if co: print(f"      CO: {' | '.join(c['exts']['CALLOUT'][:6])}")
        if sn: print(f"      SN: {c['exts']['STRUCTURED_SNIPPET'][0]}")
        if ca: print(f"      CA: {c['exts']['CALL'][0]}")

# Save full data
out = "scripts/_audit_all_active_extensions.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)
print(f"\n  full data → {out}")
