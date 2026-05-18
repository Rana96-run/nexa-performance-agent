"""Find a few existing campaigns that already have final_url_suffix set, so we
can see the canonical template."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

c = get_client()
ga = c.get_service("GoogleAdsService")
q = "SELECT campaign.name, campaign.final_url_suffix FROM campaign WHERE campaign.final_url_suffix != ''"
n = 0
for r in ga.search(customer_id="1513020554", query=q):
    n += 1
    if n <= 5:
        print(f"\n{r.campaign.name}")
        print(f"  {r.campaign.final_url_suffix}")
print(f"\nTotal campaigns with suffix set: {n}")
