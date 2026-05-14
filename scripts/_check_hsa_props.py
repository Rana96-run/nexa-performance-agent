"""Find HubSpot Lead Module properties that store the parsed hsa_* URL parameters.
Google Ads auto-appends hsa_cam (campaign id), hsa_grp (ad group id), hsa_ad
(creative/ad id), hsa_kw (keyword), hsa_tgt (target id), hsa_mt (match type),
hsa_net (network), hsa_src (source). When users land on Qoyod and submit a
form, HubSpot captures these and writes them to lead/contact properties.
We need the exact property names so the collector can fetch them."""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
BASE = "https://api.hubapi.com"
H = {"Authorization": f"Bearer {TOKEN}"}

def list_props(object_type, label):
    r = requests.get(f"{BASE}/crm/v3/properties/{object_type}",
                     headers=H, timeout=60)
    if r.status_code != 200:
        print(f"[ERR] {label} ({object_type}): {r.status_code} {r.text[:200]}")
        return []
    return r.json().get("results", [])

# Patterns to search for
KEYWORDS = ["hsa_", "hs_ad_", "hs_googleads", "hs_google_ad", "hs_campaign",
            "hs_adgroup", "google_ads_", "googleads_", "campaign_id",
            "adgroup_id", "ad_group_id", "ad_id_", "click_id", "gclid",
            "msclkid", "matchtype", "match_type", "keyword", "creative",
            "network", "targetid", "target_id"]

for obj_type, label in [("0-136", "LEAD MODULE"), ("0-1", "CONTACT"), ("0-3", "DEAL")]:
    print(f"\n{'='*80}\n{label} ({obj_type}) — properties matching ad-tracking patterns\n{'='*80}")
    props = list_props(obj_type, label)
    matches = []
    for p in props:
        name = p["name"].lower()
        if any(k in name for k in KEYWORDS):
            matches.append(p)
    if not matches:
        print("  (none found)")
        continue
    for p in sorted(matches, key=lambda x: x["name"]):
        label_txt = p.get("label", "")[:50]
        ftype = p.get("type", "")
        print(f"  {p['name']:55s}  ({ftype})  {label_txt}")
