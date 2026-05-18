"""Apply the website-visitor audience as a signal to the 2 PMax campaigns
on Acc2 (PMax can't use campaign_criterion; uses asset_group_signal instead).

PMax_AR_Invoice (22790330091)
PMax_AR_Invoice_Technology (23844719995)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "5753494964"
PMAX_CAMPS = ["22790330091", "23844719995"]
LIST_RN = "customers/5753494964/userLists/9390186986"

client = get_client()
ga     = client.get_service("GoogleAdsService")
ags_svc = client.get_service("AssetGroupSignalService")

# Discover asset groups for each PMax campaign
q = f"""
SELECT asset_group.id, asset_group.name, campaign.id
FROM asset_group
WHERE campaign.id IN ({",".join(PMAX_CAMPS)})
"""
asset_groups = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    asset_groups.append({
        "ag_id":   str(r.asset_group.id),
        "ag_name": r.asset_group.name,
        "cid":     str(r.campaign.id),
    })

print(f"Found {len(asset_groups)} asset group(s):")
for ag in asset_groups:
    print(f"  cid={ag['cid']}  ag={ag['ag_id']}  {ag['ag_name']}")

# PMax needs an Audience resource (asset_group_signal.audience expects an
# Audience RN, not a user_list directly). Create one wrapping our user list.

aud_svc = client.get_service("AudienceService")
AUD_NAME = "PMax Signal — Qoyod Site Visitors (excl app)"

# Check if already exists
existing_rn = None
q2 = f"SELECT audience.resource_name FROM audience WHERE audience.name = '{AUD_NAME}'"
for r in ga.search(customer_id=ACCOUNT, query=q2):
    existing_rn = r.audience.resource_name
    break

if existing_rn:
    AUDIENCE_RN = existing_rn
    print(f"\nReusing existing Audience: {AUDIENCE_RN}")
else:
    print(f"\nCreate Audience wrapper for the user list ...")
    op = client.get_type("AudienceOperation")
    a = op.create
    a.name = AUD_NAME
    a.description = "PMax audience signal — visitors to qoyod.com domains except app"
    seg_dim = client.get_type("AudienceDimension")
    seg = client.get_type("AudienceSegment")
    seg.user_list.user_list = LIST_RN
    seg_dim.audience_segments.segments.append(seg)
    a.dimensions.append(seg_dim)
    r = aud_svc.mutate_audiences(customer_id=ACCOUNT, operations=[op])
    AUDIENCE_RN = r.results[0].resource_name
    print(f"  ✅ created: {AUDIENCE_RN}")

# Now create asset_group_signal pointing to the Audience
print(f"\nLink Audience to {len(asset_groups)} asset groups")
ops = []
for ag in asset_groups:
    op = client.get_type("AssetGroupSignalOperation")
    co = op.create
    co.asset_group = f"customers/{ACCOUNT}/assetGroups/{ag['ag_id']}"
    co.audience.audience = AUDIENCE_RN
    ops.append(op)

try:
    r = ags_svc.mutate_asset_group_signals(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ added {len(r.results)} asset_group_signal(s)")
except Exception as e:
    import re
    msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
    for m in msgs[:5]:
        print(f"  ❌ {m}")
