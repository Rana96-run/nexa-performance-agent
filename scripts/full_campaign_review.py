"""
Full campaign review — every campaign with spend > $100 last 7d (ending yesterday).
Classifies by CPL / CPQL zones and recommends an action.

Run:
    python -m scripts.full_campaign_review
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from collectors.bq_writer import get_client, PROJECT_ID, DATASET
from config import (
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
)

# ─── Zones ────────────────────────────────────────────────────────────────────
def cpl_zone(v):
    if v is None: return "no_data"
    if v <= CPL_SCALE:       return "scale"
    if v <= CPL_ACCEPTABLE:  return "acceptable"
    if v <= CPL_WARNING:     return "warning"
    return "pause"

def cpql_zone(v):
    if v is None: return "no_data"
    if v <= CPQL_SCALE:      return "scale"
    if v <= CPQL_ACCEPTABLE: return "acceptable"
    if v <= CPQL_WARNING:    return "warning"
    return "pause"

ZONE_TXT = {
    "scale": "🟢 SCALE", "acceptable": "🟡 OK ", "warning": "🟠 WATCH",
    "pause": "🔴 PAUSE", "no_data": "⚪ NO_DATA",
}


# ─── Pull data ────────────────────────────────────────────────────────────────
client = get_client()

q_camp = f"""
WITH base AS (
  SELECT *
  FROM `{PROJECT_ID}.{DATASET}.paid_channel_campaign_daily`
  WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
    AND date <= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 1 DAY)
),
agg AS (
  SELECT
    channel, campaign_name,
    SUM(spend)        AS spend,
    SUM(leads)        AS leads,
    SUM(qualified)    AS qual,
    SUM(disqualified) AS disq,
    SUM(open_leads)   AS open_l,
    SUM(deals)        AS deals,
    SUM(deal_amount)  AS deal_amount
  FROM base
  GROUP BY channel, campaign_name
)
SELECT
  channel, campaign_name,
  spend, leads, qual, disq, open_l, deals, deal_amount,
  SAFE_DIVIDE(spend,       NULLIF(leads, 0))     AS cpl,
  SAFE_DIVIDE(spend,       NULLIF(qual, 0))      AS cpql,
  SAFE_DIVIDE(deal_amount, NULLIF(spend, 0))     AS roas,
  SAFE_DIVIDE(qual,        NULLIF(leads, 0)) * 100 AS qual_rate
FROM agg
WHERE spend > 100
ORDER BY spend DESC
"""

# ─── Classify and report ──────────────────────────────────────────────────────
print("=" * 110)
print("FULL CAMPAIGN REVIEW — last 7d ending yesterday  ($100+ spend)")
print("=" * 110)
print(f"  CPL zones:  scale ≤ ${CPL_SCALE}  acceptable ≤ ${CPL_ACCEPTABLE}  "
      f"warning ≤ ${CPL_WARNING}  pause > ${CPL_WARNING}")
print(f"  CPQL zones: scale ≤ ${CPQL_SCALE}  acceptable ≤ ${CPQL_ACCEPTABLE}  "
      f"warning ≤ ${CPQL_WARNING}  pause > ${CPQL_WARNING}")
print()
print(f"{'CH':10s} {'SPEND':>7s} {'L':>3s} {'Q':>3s} {'OPEN':>4s} "
      f"{'CPL':>5s} {'CPQL':>5s} {'q%':>3s}  CPL_ZONE  CPQL_ZONE  CAMPAIGN")
print("-" * 110)

actions = {"scale": [], "watch": [], "pause": [], "no_data": [], "ok": []}

for r in client.query(q_camp).result():
    cpl  = round(r.cpl, 0)  if r.cpl  is not None else None
    cpql = round(r.cpql, 0) if r.cpql is not None else None
    qrate = round(r.qual_rate, 0) if r.qual_rate is not None else 0

    cz = cpl_zone(cpl)
    qz = cpql_zone(cpql)

    # Decide action: pause if CPL OR CPQL is in pause zone; scale if BOTH are scale; otherwise watch/ok
    if cz == "pause" or qz == "pause":
        actions["pause"].append((r.channel, r.campaign_name, r.spend, cpl, cpql, qrate, cz, qz))
    elif cz == "scale" and qz == "scale":
        actions["scale"].append((r.channel, r.campaign_name, r.spend, cpl, cpql, qrate, cz, qz))
    elif cz == "warning" or qz == "warning":
        actions["watch"].append((r.channel, r.campaign_name, r.spend, cpl, cpql, qrate, cz, qz))
    elif cz == "no_data":
        actions["no_data"].append((r.channel, r.campaign_name, r.spend, cpl, cpql, qrate, cz, qz))
    else:
        actions["ok"].append((r.channel, r.campaign_name, r.spend, cpl, cpql, qrate, cz, qz))

    print(f"{r.channel:10s} ${int(r.spend or 0):>5,}  "
          f"{int(r.leads or 0):>3} {int(r.qual or 0):>3} {int(r.open_l or 0):>4}  "
          f"${int(cpl) if cpl else 0:>3}  ${int(cpql) if cpql else 0:>3}  "
          f"{int(qrate) if qrate else 0:>2}%  {ZONE_TXT[cz]}  {ZONE_TXT[qz]}  "
          f"{r.campaign_name[:60]}")

# ─── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 110)
print("ACTION SUMMARY")
print("=" * 110)
for kind in ("pause", "watch", "scale", "no_data", "ok"):
    print(f"\n{kind.upper()} ({len(actions[kind])}):")
    for ch, name, spend, cpl, cpql, qrate, cz, qz in actions[kind][:20]:
        print(f"  {ch:10s} ${int(spend):>5,}  CPL=${int(cpl) if cpl else 0:>3} "
              f"CPQL=${int(cpql) if cpql else 0:>3} q%={int(qrate) if qrate else 0:>2}  {name[:55]}")

print("\nTotals:")
for k, v in actions.items():
    total_spend = sum(row[2] for row in v)
    print(f"  {k:8s} {len(v):>3} campaigns, ${int(total_spend):>6,} spent")
