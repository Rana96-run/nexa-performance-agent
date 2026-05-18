"""Link the 4 /accounting sitelinks (already created on Acc1) to the 3 Brand
campaigns on Account 1."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"

BRAND_CAMPS = {
    "22221111741": "ImpressionShare_Search_AR_Brand",
    "22434988923": "Search_AR_Brand",
    "23032247671": "Search_AR_Brand_v2",
}

# Asset RNs created by _create_accounting_lp_sitelinks.py
SITELINK_RNS = [
    "customers/1513020554/assets/362037318899",  # مميزات قيود
    "customers/1513020554/assets/362037835289",  # كيف تبدأ في 3 خطوات
    "customers/1513020554/assets/362203451289",  # خطط الأسعار
    "customers/1513020554/assets/362123222224",  # الأسئلة الشائعة
]

client = get_client()
ca_svc = client.get_service("CampaignAssetService")

ops = []
for cid, name in BRAND_CAMPS.items():
    for arn in SITELINK_RNS:
        op = client.get_type("CampaignAssetOperation")
        op.create.campaign   = f"customers/{ACCOUNT}/campaigns/{cid}"
        op.create.asset      = arn
        op.create.field_type = client.enums.AssetFieldTypeEnum.SITELINK
        ops.append(op)

r = ca_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
print(f"✅ linked {len(r.results)} associations  (4 sitelinks × 3 brand campaigns)")
