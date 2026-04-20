"""
HubSpot -> BigQuery collector.
Aggregates contacts by utm_campaign per day and lifecyclestage,
writes to hubspot_leads_daily.
"""
from datetime import date, timedelta, datetime, timezone
from collections import defaultdict
import hubspot
from config import HUBSPOT_TOKEN
from collectors.bq_writer import upsert_rows


STAGES = {
    "lead": "leads",
    "marketingqualifiedlead": "mqls",
    "salesqualifiedlead": "sqls",
    "opportunity": "opportunities",
    "customer": "customers",
}


def _fetch_contacts(client, since_ms, after=None):
    """Paginate through contacts createdate >= since_ms."""
    req = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "createdate",
                "operator": "GTE",
                "value": str(since_ms),
            }]
        }],
        "properties": [
            "createdate", "lifecyclestage",
            "utm_campaign", "utm_source", "utm_medium",
            "qoyod_source",
        ],
        "limit": 100,
    }
    if after:
        req["after"] = after
    return client.crm.contacts.search_api.do_search(public_object_search_request=req)


def collect_and_write(days: int = 14):
    client = hubspot.Client.create(access_token=HUBSPOT_TOKEN)
    end = date.today()
    start = end - timedelta(days=days)
    since_ms = int(datetime(start.year, start.month, start.day).timestamp() * 1000)

    # (date, utm_campaign, utm_source, utm_medium, qoyod_source) -> {leads, mqls, sqls, opportunities, customers}
    buckets = defaultdict(lambda: {"leads": 0, "mqls": 0, "sqls": 0, "opportunities": 0, "customers": 0})

    after = None
    page = 0
    total = 0
    while True:
        resp = _fetch_contacts(client, since_ms, after=after)
        for c in resp.results:
            p = c.properties
            created = p.get("createdate", "")[:10]  # YYYY-MM-DD
            if not created:
                continue
            key = (
                created,
                (p.get("utm_campaign") or "").strip() or None,
                (p.get("utm_source") or "").strip() or None,
                (p.get("utm_medium") or "").strip() or None,
                (p.get("qoyod_source") or "").strip() or None,
            )
            bucket = buckets[key]
            bucket["leads"] += 1
            stage = (p.get("lifecyclestage") or "").lower()
            for raw, col in STAGES.items():
                if stage == raw and col != "leads":
                    bucket[col] += 1
            total += 1

        page += 1
        if not resp.paging or not resp.paging.next:
            break
        after = resp.paging.next.after
        if page >= 100:  # safety cap
            break

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for (d, utm_c, utm_s, utm_m, qsrc), counts in buckets.items():
        rows.append({
            "date": d,
            "utm_campaign": utm_c,
            "utm_source": utm_s,
            "utm_medium": utm_m,
            "qoyod_source": qsrc,
            "leads_count": counts["leads"],
            "mqls_count": counts["mqls"],
            "sqls_count": counts["sqls"],
            "opportunities_count": counts["opportunities"],
            "customers_count": counts["customers"],
            "updated_at": now,
        })

    print(f"Processed {total} contacts -> {len(rows)} daily aggregates")
    # key is (date, utm_campaign) — treat null as empty string for idempotency
    for r in rows:
        if r["utm_campaign"] is None:
            r["utm_campaign"] = "__none__"
    n = upsert_rows("hubspot_leads_daily", rows,
                    key_fields=["date", "utm_campaign"])
    return n


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    n = collect_and_write(days)
    print(f"HubSpot backfill complete: {n} rows ({days} days)")
