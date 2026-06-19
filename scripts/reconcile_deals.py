"""
Quick 7-day deals reconciliation: BQ hubspot_deals_daily vs HubSpot API.
Run: railway run python -m scripts.reconcile_deals
"""
import sys, os, requests
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")
from collectors.bq_writer import get_client, PROJECT_ID, DATASET

PAID = ("Google Ads", "Meta Ads", "Snapchat Ads", "Tiktok Ads",
        "Microsoft Ads", "LinkedIn Ads")
DAYS = 7

def run():
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("HUBSPOT_ACCESS_TOKEN not set")

    end   = (datetime.utcnow() + timedelta(hours=3)).date() - timedelta(days=1)
    start = end - timedelta(days=DAYS - 1)

    # ── BQ side ──────────────────────────────────────────────────────────────
    client = get_client()
    sources = ", ".join(f"'{s}'" for s in PAID)
    sql = f"""
    SELECT date, SUM(deals_total) AS deals, SUM(deals_won) AS won,
           ROUND(SUM(amount_won), 2) AS rev_won
    FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
    WHERE date BETWEEN '{start}' AND '{end}'
      AND qoyod_source IN ({sources})
    GROUP BY date ORDER BY date
    """
    bq_by_day = {}
    bq_total = bq_won = 0
    bq_rev = 0.0
    print(f"\n=== BQ deals (paid, createdate Riyadh) — {start} to {end} ===")
    for r in client.query(sql).result():
        d = str(r.date)
        bq_by_day[d] = {"deals": int(r.deals), "won": int(r.won)}
        bq_total += int(r.deals); bq_won += int(r.won); bq_rev += float(r.rev_won or 0)
        print(f"  {d}  total={int(r.deals):>4}  won={int(r.won):>3}  rev=${float(r.rev_won or 0):>8,.0f}")
    print(f"  SUBTOTAL: total={bq_total}  won={bq_won}  rev=${bq_rev:,.0f}")

    # ── HubSpot side ─────────────────────────────────────────────────────────
    riyadh_start_utc = datetime(start.year, start.month, start.day) - timedelta(hours=3)
    riyadh_end_utc   = datetime(end.year, end.month, end.day) + timedelta(days=1) - timedelta(hours=3)
    since_ms = int(riyadh_start_utc.timestamp() * 1000)
    until_ms = int(riyadh_end_utc.timestamp()   * 1000)
    paid_set = set(PAID)
    headers  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    per_day: dict = defaultdict(lambda: {"deals": 0, "won": 0, "rev": 0.0})
    after = None
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)},
                {"propertyName": "createdate", "operator": "LT",  "value": str(until_ms)},
            ]}],
            "properties": ["createdate", "deal_qoyod_source", "dealstage", "amount"],
            "limit": 100,
        }
        if after:
            body["after"] = after
        r = requests.post("https://api.hubapi.com/crm/v3/objects/deals/search",
                          json=body, headers=headers, timeout=30)
        data = r.json()
        for row in data.get("results", []):
            p = row.get("properties", {})
            src = (p.get("deal_qoyod_source") or "").strip()
            if src not in paid_set:
                continue
            cd = p.get("createdate", "")
            if not cd:
                continue
            ts  = datetime.fromisoformat(cd.replace("Z", "+00:00"))
            day = str((ts + timedelta(hours=3)).date())
            per_day[day]["deals"] += 1
            if (p.get("dealstage") or "").endswith("closedwon"):
                per_day[day]["won"] += 1
                try:
                    per_day[day]["rev"] += float(p.get("amount") or 0) / 3.75  # SAR -> USD
                except (ValueError, TypeError) as e:
                    import logging
                    raw_val = p.get("amount")
                    logging.getLogger(__name__).warning(f"[reconcile_deals] could not parse amount '{raw_val}': {e} — defaulting to 0")
                    amount = 0.0
        nxt   = data.get("paging", {}).get("next", {})
        after = nxt.get("after")
        if not after:
            break

    hs_total = hs_won = 0
    hs_rev = 0.0
    print(f"\n=== HubSpot deals (paid, createdate Riyadh) — {start} to {end} ===")
    for day in sorted(per_day):
        d = per_day[day]
        print(f"  {day}  total={d['deals']:>4}  won={d['won']:>3}  rev=${d['rev']:>8,.0f}")
        hs_total += d["deals"]; hs_won += d["won"]; hs_rev += d["rev"]
    print(f"  SUBTOTAL: total={hs_total}  won={hs_won}  rev=${hs_rev:,.0f}")

    # ── Delta ─────────────────────────────────────────────────────────────────
    print(f"\n=== DELTA BQ vs HubSpot ===")
    print(f"  {'date':<12} {'BQ':>5} {'HS':>5} {'diff':>6}")
    print("  " + "-" * 32)
    all_days = sorted(set(list(bq_by_day) + list(per_day)))
    for day in all_days:
        b = bq_by_day.get(day, {"deals": 0, "won": 0})
        h = per_day.get(day, {"deals": 0})
        diff = b["deals"] - h["deals"]
        flag = " !!" if abs(diff) > 5 and abs(diff) / max(h["deals"], 1) > 0.05 else ""
        print(f"  {day:<12} {b['deals']:>5} {h['deals']:>5} {diff:>+6}{flag}")
    total_diff = bq_total - hs_total
    pct = abs(total_diff) / max(hs_total, 1) * 100
    print(f"\n  TOTAL: BQ={bq_total} HS={hs_total} diff={total_diff:+d} ({pct:.1f}%)")
    print(f"  Won:   BQ={bq_won}   HS={hs_won}   diff={bq_won-hs_won:+d}")

# Backwards-compat alias — callers that import reconcile() get run()
reconcile = run


if __name__ == "__main__":
    run()
