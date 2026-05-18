"""Unlink 3 sitelinks from all 3 ZATCA campaigns.

Removes the campaign_asset association only — the underlying asset is
preserved so it can be re-linked later if needed.

Targeting these link_texts:
  - احجز عرض توضيحي  (→ #demo)
  - حاسبة المرحلة الثانية  (→ #deadline)
  - تواصل مع المبيعات  (→ #contact)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMPS = ["23851270716", "23861101390", "23861965426"]

TARGET_TEXTS = {
    "احجز عرض توضيحي",
    "حاسبة المرحلة الثانية",
    "تواصل مع المبيعات",
}

client = get_client()
ga     = client.get_service("GoogleAdsService")
ca_svc = client.get_service("CampaignAssetService")

# Find campaign_asset RNs matching the target texts (ENABLED only)
q = f"""
SELECT campaign.id, campaign.name,
       campaign_asset.resource_name,
       campaign_asset.status,
       asset.sitelink_asset.link_text
FROM campaign_asset
WHERE campaign.id IN ({",".join(CAMPS)})
  AND campaign_asset.field_type = 'SITELINK'
  AND campaign_asset.status = 'ENABLED'
"""
to_remove = []
for r in ga.search(customer_id=ACCOUNT, query=q):
    text = r.asset.sitelink_asset.link_text
    if text in TARGET_TEXTS:
        to_remove.append((r.campaign.name, text, r.campaign_asset.resource_name))

print(f"Found {len(to_remove)} campaign_asset link(s) to remove:")
for cn, t, rn in to_remove:
    print(f"  {cn}  ::  {t}")

if not to_remove:
    print("Nothing to do.")
    sys.exit(0)

ops = []
for _, _, rn in to_remove:
    op = client.get_type("CampaignAssetOperation")
    op.remove = rn
    ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"\n✅ removed {len(r.results)} campaign_asset link(s)")
print("(Underlying assets preserved — can be re-linked any time)")
