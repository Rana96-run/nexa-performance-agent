"""Discover INDIRECT-but-effective audiences for ZATCA campaigns.

Direct fit (already attached): Accounting Software, Tax Prep, Financial
Planning, Business Services, Enterprise Software, ERP Solutions.

Indirect angles to scan:
  - Saudi SMB owners (any "small business" or "entrepreneur" audience)
  - Phase 2-affected sectors: Restaurants/F&B, Retail/E-commerce, Real Estate
  - SaaS/cloud buyers (Phase 2 forces them to adopt cloud)
  - Mobile/online banking (SMB owners managing finances)
  - Business professionals (affinity — wider funnel)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
c = get_client()
ga = c.get_service("GoogleAdsService")

# Pull in-market + affinity
TAXONOMIES = ["IN_MARKET", "AFFINITY", "AFFINITY_NEW"]

INDIRECT_KEYWORDS = [
    # SMB / entrepreneur signals
    "small business", "smb", "entrepreneur", "business owner",
    # Phase-2-affected sectors
    "restaurant", "café", "cafe", "food", "retail", "e-commerce", "ecommerce",
    "real estate", "construction", "wholesale",
    # SaaS / cloud / tech buyers
    "saas", "cloud", "software as a service", "b2b software",
    # Financial behavior signals
    "online banking", "mobile banking", "financial services", "fintech",
    # Office / business tools
    "office", "productivity", "collaboration", "team management",
    # Compliance / regulatory
    "compliance", "tax", "regulation", "audit",
    # Business news / professional content
    "business news", "professional", "executive",
]

print("Scanning user_interest taxonomies for indirect fit...")
q = "SELECT user_interest.user_interest_id, user_interest.name, user_interest.taxonomy_type FROM user_interest"
all_audiences = list(ga.search(customer_id=ACCOUNT, query=q))
print(f"  total audiences in account: {len(all_audiences)}")

# Already attached (skip)
EXISTING = {80133, 80137, 80281, 80463, 80530, 80536}   # the 6 kept after removing 80539

candidates = []
USABLE_TAX = {"IN_MARKET", "AFFINITY", "AFFINITY_NEW"}
for r in all_audiences:
    aid  = r.user_interest.user_interest_id
    name = r.user_interest.name
    tax  = r.user_interest.taxonomy_type.name
    if aid in EXISTING:
        continue
    if tax not in USABLE_TAX:
        continue   # Skip VERTICAL_GEO (Display only), MOBILE_APP_INSTALL_USER, etc.
    nl = name.lower()
    for kw in INDIRECT_KEYWORDS:
        if kw in nl:
            candidates.append({"id": aid, "name": name, "tax": tax, "match": kw})
            break

# Dedupe by ID
seen = set()
unique = []
for x in candidates:
    if x["id"] in seen: continue
    seen.add(x["id"])
    unique.append(x)
candidates = unique

print(f"\n  Matched {len(candidates)} indirect candidates:")
for c_ in sorted(candidates, key=lambda x: x["tax"]):
    print(f"    [{c_['tax']:<14}] {c_['id']:>10}  {c_['name'][:60]:<60}  (matched: {c_['match']})")
