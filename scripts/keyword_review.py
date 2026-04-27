"""
Keyword review — pulls keyword-level performance from Google Ads (live API)
and identifies pause / scale / negative-keyword candidates.

Two accounts are queried (Qoyod New + Auto Cloud).

Run:
    python -m scripts.keyword_review
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

from collectors.google_ads import get_client
from collectors.google_ads_bq import _customer_ids
from collectors.currency import normalize_currency, to_usd

GOOGLE_ADS_CUSTOMER_IDS = _customer_ids()

DAYS = 14   # rolling window for waste detection (pause threshold needs 14d)


def fetch_keywords(customer_id: str):
    client = get_client()
    ga = client.get_service("GoogleAdsService")
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=DAYS - 1)

    query = f"""
      SELECT
        ad_group_criterion.keyword.text,
        ad_group_criterion.keyword.match_type,
        ad_group_criterion.resource_name,
        ad_group.name,
        campaign.name,
        customer.currency_code,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions
      FROM keyword_view
      WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        AND ad_group_criterion.status = 'ENABLED'
      ORDER BY metrics.cost_micros DESC
    """
    rows = []
    try:
        for r in ga.search(customer_id=customer_id, query=query):
            native_cur   = normalize_currency(getattr(r.customer, "currency_code", None))
            spend_native = r.metrics.cost_micros / 1_000_000
            spend        = to_usd(spend_native, native_cur)
            rows.append({
                "account":    customer_id,
                "campaign":   r.campaign.name,
                "ad_group":   r.ad_group.name,
                "keyword":    r.ad_group_criterion.keyword.text,
                "match":      r.ad_group_criterion.keyword.match_type.name,
                "spend":      round(spend, 2),
                "clicks":     int(r.metrics.clicks),
                "conv":       float(r.metrics.conversions),
                "impressions": int(r.metrics.impressions),
                "resource":   r.ad_group_criterion.resource_name,
            })
    except Exception as e:
        print(f"  account {customer_id}: ERROR — {e}")
    return rows


# ─── Pull both accounts ───────────────────────────────────────────────────────
all_kw = []
for cid in GOOGLE_ADS_CUSTOMER_IDS:
    print(f"[google_ads] fetching keywords for account {cid}…")
    rows = fetch_keywords(cid)
    print(f"  → {len(rows)} keywords pulled")
    all_kw.extend(rows)

print(f"\nTOTAL: {len(all_kw)} keyword rows across {len(GOOGLE_ADS_CUSTOMER_IDS)} accounts\n")


# ─── Classify ────────────────────────────────────────────────────────────────
# Rules from qoyod-paid-media-agent.md:
#   Pause ad: zero conversions, 7+ days, spend > $30
#   Pause keyword: zero conversions, 14+ days, spend > $15
#   Negative-keyword candidate: clearly irrelevant, confirmed
pause_kw = [k for k in all_kw if k["spend"] > 15  and k["conv"] == 0]
high_spend_pause = [k for k in pause_kw if k["spend"] > 50]
low_cpa_scale  = [k for k in all_kw if k["conv"] >= 3 and (k["spend"] / k["conv"]) < 30]

# ─── Report ──────────────────────────────────────────────────────────────────
print("=" * 100)
print(f"PAUSE CANDIDATES — keywords with $0 conversions / >$15 spend / 14d window")
print("=" * 100)
pause_kw.sort(key=lambda k: -k["spend"])
total_waste = 0
for k in pause_kw[:30]:
    total_waste += k["spend"]
    flag = " 🔴 HIGH" if k["spend"] > 50 else ""
    print(f"  ${k['spend']:>5,.0f}  clicks={k['clicks']:>3}  imp={k['impressions']:>5,}  "
          f"[{k['match'][:6]:6s}] {k['keyword'][:50]:50s} | "
          f"{k['campaign'][:30]:30s}{flag}")
print(f"\n  ⚠️  Total wasted spend on pause-candidates: ${total_waste:,.2f} (last {DAYS}d)")

print()
print("=" * 100)
print(f"SCALE CANDIDATES — 3+ conversions, CPA < $30")
print("=" * 100)
low_cpa_scale.sort(key=lambda k: -k["conv"])
for k in low_cpa_scale[:20]:
    cpa = k["spend"] / k["conv"]
    print(f"  ${k['spend']:>5,.0f}  conv={k['conv']:>4.1f}  CPA=${cpa:>5.0f}  "
          f"[{k['match'][:6]:6s}] {k['keyword'][:50]:50s} | {k['campaign'][:35]:35s}")

print()
print("=" * 100)
print("SUMMARY")
print("=" * 100)
print(f"  Total keywords:                 {len(all_kw)}")
print(f"  Pause candidates ($15+ no conv): {len(pause_kw)}  → ${total_waste:,.0f} wasted")
print(f"  High-priority pauses ($50+):     {len(high_spend_pause)}")
print(f"  Scale candidates (CPA < $30):    {len(low_cpa_scale)}")
