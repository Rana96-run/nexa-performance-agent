"""Check what user_list audiences (Customer Match, Site Visitors, Video
Viewers) are already synced to the Google Ads accounts."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

c = get_client()
ga = c.get_service("GoogleAdsService")

for acct in ["1513020554", "5753494964"]:
    print(f"\n{'='*78}")
    print(f"ACCOUNT {acct} — user lists")
    print('='*78)
    q = """
    SELECT user_list.id, user_list.name, user_list.type, user_list.size_for_search,
           user_list.size_for_display, user_list.membership_status,
           user_list.access_reason
    FROM user_list
    """
    rows = list(ga.search(customer_id=acct, query=q))
    if not rows:
        print("  (none)")
        continue
    print(f"{'Type':<20} {'Size(Search)':>12} {'Size(Display)':>13}  Name")
    for r in rows:
        ul = r.user_list
        print(f"  {ul.type_.name:<20} {ul.size_for_search:>10,}  {ul.size_for_display:>11,}  {ul.name[:60]}")
