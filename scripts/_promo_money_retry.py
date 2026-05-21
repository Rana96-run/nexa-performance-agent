"""Try money_amount_off promotion (SAR 100 off Qoyod Annual Plan)."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


PROMOS = [
    {"name": "Promo_qawaem_AR_v2", "target": "باقة قيود السنوية", "lang_code": "ar"},
    {"name": "Promo_qawaem_EN_v2", "target": "Qoyod Annual Plan", "lang_code": "en"},
]

asset_svc = client.get_service("AssetService")
ca_svc    = client.get_service("CampaignAssetService")

for acct, cid in [("1513020554", "23861837000"), ("5753494964", "23870151040")]:
    print(f"\n=== Acc {acct} ===")
    rns = []
    for p in PROMOS:
        op = client.get_type("AssetOperation")
        a = op.create
        a.name = p["name"]
        a.final_urls.append("https://lp.qoyod.com/qawaem/")
        pa = a.promotion_asset
        pa.promotion_target = p["target"]
        pa.money_amount_off.amount_micros = 100_000_000   # 100 SAR
        pa.money_amount_off.currency_code = "SAR"
        pa.language_code = p["lang_code"]
        try:
            r = asset_svc.mutate_assets(customer_id=acct, operations=[op])
            rns.append(r.results[0].resource_name)
            print(f"  ✅ {p['name']}: {r.results[0].resource_name}")
        except Exception as e:
            print(f"  ❌ {p['name']}: {_err(e)[:250]}")

    if rns:
        link_ops = []
        for rn in rns:
            op = client.get_type("CampaignAssetOperation")
            op.create.campaign   = f"customers/{acct}/campaigns/{cid}"
            op.create.asset      = rn
            op.create.field_type = client.enums.AssetFieldTypeEnum.PROMOTION
            link_ops.append(op)
        try:
            r = ca_svc.mutate_campaign_assets(customer_id=acct, operations=link_ops)
            print(f"  ✅ linked {len(r.results)} promo assets")
        except Exception as e:
            print(f"  ❌ link: {_err(e)[:200]}")
