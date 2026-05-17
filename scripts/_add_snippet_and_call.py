"""Add the remaining 2 extension assets — structured snippet + call.
Sitelinks (4) + callouts (8) already created in previous run."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from executors.google_ads import get_client

ACCOUNT  = "1513020554"
CAMP_IDS = ["23851270716", "23861101390"]
SAUDI_PHONE = "+966112345678"  # placeholder — replace with real Qoyod sales line

client     = get_client()
asset_svc  = client.get_service("AssetService")
camp_asset_svc = client.get_service("CampaignAssetService")


def create_asset(builder, label: str) -> str:
    op = client.get_type("AssetOperation")
    builder(op.create)
    r = asset_svc.mutate_assets(customer_id=ACCOUNT, operations=[op])
    rn = r.results[0].resource_name
    print(f"  ✅ asset {label}: {rn}")
    return rn


def link_to_campaigns(asset_rns: list[str], field_type_name: str):
    ops = []
    ft = getattr(client.enums.AssetFieldTypeEnum, field_type_name)
    for cid in CAMP_IDS:
        for arn in asset_rns:
            op = client.get_type("CampaignAssetOperation")
            ca = op.create
            ca.campaign  = f"customers/{ACCOUNT}/campaigns/{cid}"
            ca.asset     = arn
            ca.field_type = ft
            ops.append(op)
    r = camp_asset_svc.mutate_campaign_assets(customer_id=ACCOUNT, operations=ops)
    print(f"  ✅ linked {len(r.results)} {field_type_name} associations")


# ── Structured Snippet — use "Types" (one of Google's 12 valid headers) ────
print("=" * 70)
print("STRUCTURED SNIPPET — header = 'Types' (valid header)")
print("=" * 70)
SNIPPET_HEADER = "Types"
SNIPPET_VALUES = ["XML", "PDF/A-3", "REST API", "QR Code", "Encrypted Seal"]

def build_snippet(create_obj):
    create_obj.name = f"Snippet_Types_{SNIPPET_HEADER}"
    ss = create_obj.structured_snippet_asset
    ss.header = SNIPPET_HEADER
    for v in SNIPPET_VALUES:
        ss.values.append(v)

snippet_rn = create_asset(build_snippet, f"{SNIPPET_HEADER}: {', '.join(SNIPPET_VALUES)}")
link_to_campaigns([snippet_rn], "STRUCTURED_SNIPPET")


# ── Call extension ──────────────────────────────────────────────────────────
print()
print("=" * 70)
print("CALL extension")
print("=" * 70)

def build_call(create_obj):
    create_obj.name = f"Call_{SAUDI_PHONE}"
    call = create_obj.call_asset
    call.country_code = "SA"
    call.phone_number = SAUDI_PHONE
    call.call_conversion_reporting_state = (
        client.enums.CallConversionReportingStateEnum.DISABLED
    )

call_rn = create_asset(build_call, SAUDI_PHONE)
link_to_campaigns([call_rn], "CALL")

print()
print("=" * 70)
print("DONE")
print("=" * 70)
