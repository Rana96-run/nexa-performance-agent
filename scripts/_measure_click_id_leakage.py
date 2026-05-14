"""Quantify which paid click_id has the most leakage (contacts with that
click_id populated but qoyod_source is non-paid).

This tells us which channels are bleeding into Direct/Organic via late-firing
click_ids — so we can target re-enrollment to ONLY those click_ids, minimizing
the risk of overwriting correctly-classified contacts.
"""
import os, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

NON_PAID_VALUES = ["Other", "Direct Traffic", "Direct In-app Purchase",
                   "Organic Search", "Organic Social", "Email Marketing",
                   "Offline", "Referrals"]

# Each click_id and its corresponding "should be" paid channel
CLICK_IDS = [
    ("hs_google_click_id",   "Google Ads"),
    ("hs_facebook_click_id", "Meta Ads"),
    ("msclkid",              "Microsoft Ads"),
    ("hs_tiktok_click_id",   "Tiktok Ads"),
    ("hs_linkedin_click_id", "LinkedIn Ads"),
]

# Window: last 30 days
import datetime as _dt
since_ms = str(int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).timestamp() * 1000))


def count_search(filters):
    """Use Search API totalCount with limit=1 to avoid pulling rows."""
    body = {
        "filterGroups": [{"filters": filters}],
        "properties": ["createdate"],
        "limit": 1,
    }
    r = requests.post(f"{BASE}/crm/v3/objects/contacts/search",
                      headers=H, json=body, timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get("total", 0)


print(f"{'='*78}")
print(f"Phantom-paid leakage per click_id (last 30 days)")
print(f"{'='*78}\n")

print(f"{'Click ID':25s}  {'Should-be channel':18s}  Total  Phantom  Leakage%  Worst leak")
print("-" * 95)

leakage_data = []
for click_id_prop, expected_channel in CLICK_IDS:
    # Total contacts with this click_id populated in last 30d
    total = count_search([
        {"propertyName": click_id_prop, "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
    ])
    if total is None:
        print(f"  {click_id_prop}: ERR")
        continue

    # Phantom: same but qoyod_source is NON-PAID
    phantom = count_search([
        {"propertyName": click_id_prop, "operator": "HAS_PROPERTY"},
        {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
        {"propertyName": "qoyod_source", "operator": "IN", "values": NON_PAID_VALUES},
    ])
    if phantom is None:
        phantom = 0

    leakage_pct = (phantom / total * 100) if total else 0
    leakage_data.append((click_id_prop, expected_channel, total, phantom, leakage_pct))

    # Find which non-paid bucket they fall into most (sample a few)
    worst_bucket = "?"
    if phantom > 0:
        max_n = 0
        for npv in NON_PAID_VALUES:
            n = count_search([
                {"propertyName": click_id_prop, "operator": "HAS_PROPERTY"},
                {"propertyName": "createdate", "operator": "GTE", "value": since_ms},
                {"propertyName": "qoyod_source", "operator": "EQ", "value": npv},
            ])
            if n and n > max_n:
                max_n = n
                worst_bucket = f"{npv} ({n})"

    print(f"  {click_id_prop:23s}  {expected_channel:18s}  {total:5d}  {phantom:7d}  {leakage_pct:7.1f}%  {worst_bucket}")

# Recommendation
print(f"\n{'='*78}")
print(f"RECOMMENDATION — add to re-enrollment in this order:")
print(f"{'='*78}")
leakage_data.sort(key=lambda x: x[3], reverse=True)
for click_id, channel, total, phantom, pct in leakage_data:
    if phantom > 0:
        priority = "🔴 HIGH" if phantom >= 20 else ("🟡 MED" if phantom >= 5 else "🟢 LOW")
        print(f"  {priority} {click_id:25s} — {phantom} phantom-paid leads/month would be reclassified to {channel}")
    else:
        print(f"  ⚪ NONE {click_id:25s} — no leakage detected")
