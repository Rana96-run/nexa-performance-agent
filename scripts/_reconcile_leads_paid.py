"""Reconcile last-7-day paid leads: BigQuery vs HubSpot Lead Module API.
Same window as deal reconciliation: 2026-05-07 → 2026-05-13 Riyadh.

For each paid channel:
- Pull count from BQ hubspot_leads_module_daily (paid-only filter)
- Pull count from HubSpot via Search API on Lead Module (0-136)
- Compare side-by-side
"""
import os, sys, requests, datetime as _dt
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from collectors.bq_writer import get_client

TOKEN = os.environ["HUBSPOT_ACCESS_TOKEN"]
H = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
BASE = "https://api.hubapi.com"

c = get_client()
proj = os.environ["BQ_PROJECT_ID"]; ds = os.environ["BQ_DATASET"]

# Same window as deals reconciliation
START = "2026-05-07"
END = "2026-05-13"

# Riyadh date → UTC epoch-ms (Riyadh = UTC+3)
# Start: 2026-05-07 00:00 Riyadh = 2026-05-06 21:00 UTC
# End:   2026-05-13 23:59:59.999 Riyadh = 2026-05-13 20:59:59 UTC
def riyadh_to_epoch_ms(date_str, hour=0, minute=0, second=0):
    """Convert Riyadh-time date to UTC epoch-ms."""
    dt = _dt.datetime.fromisoformat(date_str).replace(hour=hour, minute=minute, second=second)
    # Riyadh is UTC+3, so subtract 3h to get UTC
    utc = dt - _dt.timedelta(hours=3)
    return str(int(utc.timestamp() * 1000))

since_ms = riyadh_to_epoch_ms(START, 0, 0, 0)
until_ms = riyadh_to_epoch_ms(END, 23, 59, 59)

print(f"Window: {START} 00:00 → {END} 23:59 Riyadh")
print(f"        ({since_ms} → {until_ms} epoch ms UTC)\n")

PAID_CHANNELS = ["Google Ads", "Meta Ads", "Snapchat Ads", "Tiktok Ads",
                 "Microsoft Ads", "LinkedIn Ads", "Twitter Ads"]

# ── 1. BQ: leads by channel ──────────────────────────────────────────────
print("=" * 72)
print("BQ — leads by qoyod_source (paid only)")
print("=" * 72)
sql = f"""
SELECT qoyod_source, SUM(leads_total) AS leads
FROM `{proj}.{ds}.hubspot_leads_module_daily`
WHERE date BETWEEN '{START}' AND '{END}'
  AND qoyod_source IN UNNEST({PAID_CHANNELS})
GROUP BY 1
ORDER BY leads DESC
"""
bq_counts = {}
for r in c.query(sql).result():
    bq_counts[r.qoyod_source] = r.leads or 0
    print(f"  {str(r.qoyod_source):20s}  {r.leads or 0}")
bq_total = sum(bq_counts.values())
print(f"  {'─'*20}  ────")
print(f"  {'TOTAL':20s}  {bq_total}")

# ── 2. HubSpot Search API: leads by channel ─────────────────────────────
print("\n" + "=" * 72)
print("HubSpot Lead Module — leads by lead_qoyod_source (paid only)")
print("=" * 72)

def count_leads_for_source(source_value):
    body = {
        "filterGroups": [{"filters": [
            {"propertyName": "lead_qoyod_source", "operator": "EQ", "value": source_value},
            {"propertyName": "hs_createdate", "operator": "GTE", "value": since_ms},
            {"propertyName": "hs_createdate", "operator": "LT",  "value": until_ms},
        ]}],
        "properties": ["hs_createdate"],
        "limit": 1,
    }
    r = requests.post(f"{BASE}/crm/v3/objects/0-136/search",
                      headers=H, json=body, timeout=30)
    if r.status_code != 200:
        return None
    return r.json().get("total", 0)

hs_counts = {}
for ch in PAID_CHANNELS:
    n = count_leads_for_source(ch)
    hs_counts[ch] = n
    print(f"  {ch:20s}  {n if n is not None else 'ERR'}")
hs_total = sum(v for v in hs_counts.values() if v is not None)
print(f"  {'─'*20}  ────")
print(f"  {'TOTAL':20s}  {hs_total}")

# ── 3. Side-by-side ──────────────────────────────────────────────────────
print("\n" + "=" * 72)
print("Side-by-side reconciliation")
print("=" * 72)
print(f"  {'channel':20s}  {'BQ':>5s}  {'HubSpot':>7s}  {'Δ':>5s}  {'Δ%':>6s}")
print(f"  {'-'*20}  {'-'*5}  {'-'*7}  {'-'*5}  {'-'*6}")
for ch in PAID_CHANNELS:
    bq = bq_counts.get(ch, 0)
    hs = hs_counts.get(ch, 0) or 0
    delta = bq - hs
    pct = (delta / hs * 100) if hs else 0
    mark = "✓" if abs(pct) < 5 else "⚠"
    print(f"  {ch:20s}  {bq:>5d}  {hs:>7d}  {delta:>+5d}  {pct:>+5.1f}%  {mark}")
print(f"  {'-'*20}  {'-'*5}  {'-'*7}  {'-'*5}  {'-'*6}")
delta_total = bq_total - hs_total
pct_total = (delta_total / hs_total * 100) if hs_total else 0
print(f"  {'TOTAL':20s}  {bq_total:>5d}  {hs_total:>7d}  {delta_total:>+5d}  {pct_total:>+5.1f}%")
