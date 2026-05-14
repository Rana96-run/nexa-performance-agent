"""Prove that DIRECT_TRAFFIC contacts with gclid set are actually Google Ads
leads — they came through a Google ad at some point, then returned via a
direct visit/bookmark/email link. The 'direct' classification is last-touch,
not the truth of the acquisition source.

Evidence:
  1. hs_google_click_id (gclid) — ONLY populated when user clicked a Google ad
  2. hs_analytics_first_url — may contain hsa_cam from the original ad click
  3. hs_analytics_source_data_1 — campaign/source from FIRST touch
"""
import os, sys, requests, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

# Pull DIRECT_TRAFFIC contacts that have gclid set (paid-traffic-decayed-to-direct)
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=72)).timestamp() * 1000))

body = {
    "filterGroups": [{"filters": [
        {"propertyName": "hs_analytics_source", "operator": "EQ", "value": "DIRECT_TRAFFIC"},
        {"propertyName": "hs_google_click_id", "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ]}],
    "properties": [
        "createdate", "email",
        "hs_analytics_source", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
        "hs_google_click_id",
        "campaign_id", "ad_group_id", "ad_id",
        "hs_analytics_first_url", "hs_analytics_last_url",
        "hs_analytics_first_referrer",
    ],
    "limit": 10,
    "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
}
r = requests.post(f"{BASE}/crm/v3/objects/contacts/search", headers=H, json=body, timeout=30)
results = r.json().get("results", [])
print(f"DIRECT_TRAFFIC contacts WITH gclid (last 72h): {len(results)}")
print(f"→ These are leads HubSpot classified as 'direct' but came from a Google ad\n")

count_with_hsa_in_url = 0
count_paid_first_source = 0
for ct in results:
    p = ct["properties"]
    print(f"━━━ Contact {ct['id']}  (created {p.get('createdate')}) ━━━")
    print(f"  hs_analytics_source       = {p.get('hs_analytics_source')}  ← HubSpot's last-touch label")
    print(f"  hs_analytics_source_data_1 = {p.get('hs_analytics_source_data_1')}  ← first-touch detail")
    print(f"  hs_google_click_id         = {(p.get('hs_google_click_id') or '')[:40]}...  ← PROOF of Google click")
    print(f"  campaign_id                = {p.get('campaign_id') or '(not captured)'}")

    first_url = p.get("hs_analytics_first_url") or ""
    has_hsa = "hsa_cam" in first_url
    has_gclid_in_url = "gclid=" in first_url
    has_utm_google = "utm_source=Google" in first_url or "utm_source=google" in first_url
    print(f"  hs_analytics_first_url     = {first_url[:75]}...")

    # Try to extract hsa_cam from first URL
    m = re.search(r"hsa_cam=(\d+)", first_url)
    if m:
        print(f"  → hsa_cam in first URL: {m.group(1)}  ← Google campaign_id available here!")
        count_with_hsa_in_url += 1
    if has_gclid_in_url or has_hsa or has_utm_google:
        count_paid_first_source += 1

    print()

print(f"\n=== SUMMARY ===")
print(f"All {len(results)} contacts have hs_google_click_id set — they ALL came through")
print(f"a Google ad originally, even though HubSpot's last-touch label says 'DIRECT_TRAFFIC'.")
print(f"{count_with_hsa_in_url}/{len(results)} have hsa_cam available in hs_analytics_first_url")
print(f"  → we can REGEX-extract the campaign_id from the URL even when contact.campaign_id is NULL")
