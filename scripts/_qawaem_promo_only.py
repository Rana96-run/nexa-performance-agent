"""Promotion asset retry only — steps 1+2 already done."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from google.ads.googleads.errors import GoogleAdsException
from executors.google_ads import get_client

PROMOS = [
    {"name": "Promo_qawaem_AR_freetrial", "target": "تجربة قيود",
     "lang_code": "ar", "final_url": "https://lp.qoyod.com/qawaem/"},
    {"name": "Promo_qawaem_EN_freetrial", "target": "Qoyod Trial",
     "lang_code": "en", "final_url": "https://lp.qoyod.com/qawaem/"},
]
ACCOUNTS = [("1513020554", "23861837000"), ("5753494964", "23870151040")]

client = get_client()


def _err(e):
    if isinstance(e, GoogleAdsException):
        return " | ".join(f"{er.error_code}: {er.message[:120]}" for er in e.failure.errors[:3])
    return str(e)[:300]


for acct, cid in ACCOUNTS:
    print(f"\n=== Acc {acct} ===")
    asset_svc = client.get_service("AssetService")
    ca_svc    = client.get_service("CampaignAssetService")
    rns = []
    for p in PROMOS:
        op = client.get_type("AssetOperation")
        a = op.create
        a.name = p["name"]
        a.final_urls.append(p["final_url"])  # Asset-level
        pa = a.promotion_asset
        pa.promotion_target = p["target"]
        pa.percent_off = 1_000_000   # 1% probe
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
            print(f"  ✅ linked {len(r.results)} promo assets to campaign")
        except Exception as e:
            print(f"  ❌ link: {_err(e)[:250]}")
