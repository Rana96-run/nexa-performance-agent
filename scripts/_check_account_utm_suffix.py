"""Check account-level (customer.final_url_suffix) on both accounts."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

client = get_client()
ga = client.get_service("GoogleAdsService")

for acct in ["1513020554", "5753494964"]:
    q = "SELECT customer.id, customer.descriptive_name, customer.final_url_suffix, customer.tracking_url_template FROM customer"
    print(f"\n=== Account {acct} ===")
    for r in ga.search(customer_id=acct, query=q):
        c = r.customer
        print(f"  name           : {c.descriptive_name}")
        suf = c.final_url_suffix or "(empty)"
        print(f"  final_url_suffix length: {len(c.final_url_suffix or '')}")
        print(f"  final_url_suffix       : {suf[:300]}")
        tpl = c.tracking_url_template or "(empty)"
        print(f"  tracking_url_template  : {tpl[:200]}")
