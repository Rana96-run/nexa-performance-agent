"""Create EN RSAs in the 3 _EN_AdGroups (re-shortened headlines ≤ 30 chars)."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from executors.google_ads import get_client

ACCOUNT = "1513020554"
LP_URL  = "https://lp.qoyod.com/einvoice-integration/"

EN_RSAS = {
    "23851270716": {  # C1 ZATCAPhase2
        "headlines": [
            "ZATCA Phase 2 Integration",
            "Connect to Fatoora Fast",
            "ZATCA Certified E-Invoicing",
            "REST API + XML + PDF/A-3",
            "50,000+ Saudi Businesses",
            "14-Day Free Trial - No Card",
            "Phase 2 Deadline: 30 Jun",
            "Arabic 24/7 Support",
            "Phase 2 Compliance in 7 Days",
            "Qoyod - Saudi #1 E-Invoice",
            "Compliance Guaranteed",
            "Phase 1 + Phase 2 Compliant",
        ],
        "descriptions": [
            "Connect your business to Fatoora portal easily. XML, PDF/A-3, REST API. ZATCA approved.",
            "50,000+ Saudi companies use Qoyod. 14-day free trial. No credit card. Start now.",
            "Wave 24 of Phase 2 ends 30 June 2026. Integrate in 7 days or your fees back.",
            "Arabic-first customer support, 24/7. Specialized in the Saudi market.",
        ],
    },
    "23861101390": {  # C2 VendorShop
        "headlines": [
            "Best E-Invoice Software 2026",
            "ZATCA Approved Software",
            "Compare Saudi Accounting",
            "Qoyod - Saudi #1 Choice",
            "Phase 1 + Phase 2 Compliant",
            "50,000+ Businesses Trust Us",
            "14-Day Free Trial",
            "Arabic Support 24/7",
            "Easy Setup + Fast Integration",
            "Saudi Tax Experts",
            "Compliance Guaranteed",
            "Start Free - No Credit Card",
        ],
        "descriptions": [
            "Compare top e-invoicing platforms in Saudi Arabia. Qoyod: certified, local, specialized.",
            "Discover why 50,000+ Saudi businesses chose Qoyod. Full free trial. Start today.",
            "Phase 2 compliance guaranteed. Integrate in 7 days or full refund of fees.",
            "What sets Qoyod apart: locally certified, fully Arabic, 24/7 support.",
        ],
    },
    "23861965426": {  # C3 Competitor
        "headlines": [
            "Best Daftra Alternative",
            "Better Than Wafeq + Rewaa",
            "ZATCA Approved - Saudi #1",
            "Why Businesses Switch to Us",
            "Phase 2 Integration Fast",
            "Arabic 24/7 Support - Local",
            "50,000+ Saudi Businesses",
            "14-Day Free Trial",
            "No Credit Card Required",
            "Compliance Guaranteed",
            "REST API + XML + PDF/A-3",
            "Qoyod - Saudi #1 Platform",
        ],
        "descriptions": [
            "Looking for a Daftra or Wafeq alternative? Qoyod: ZATCA-certified, fully Saudi.",
            "Compare Qoyod with competitors: 24/7 Arabic support, easier setup, local service.",
            "50,000+ Saudi businesses switched to Qoyod. 14-day free trial, no card. Discover why.",
            "Wave 24 ends 30 June 2026. Faster + easier integration than any competitor.",
        ],
    },
}

EN_AG_IDS = {
    "23851270716": "201783257932",
    "23861101390": "191840910210",
    "23861965426": "197201564312",
}

# Verify headline lengths
print("Verify headline lengths (≤30):")
for cid, rsa in EN_RSAS.items():
    bad = [h for h in rsa["headlines"] if len(h) > 30]
    if bad:
        print(f"  ❌ {cid}: {bad}")
        sys.exit(1)
    bad_d = [d for d in rsa["descriptions"] if len(d) > 90]
    if bad_d:
        print(f"  ❌ {cid} desc: {bad_d}")
        sys.exit(1)
print("  all OK\n")

client   = get_client()
agad_svc = client.get_service("AdGroupAdService")

for cid, rsa in EN_RSAS.items():
    ag_id = EN_AG_IDS[cid]
    op = client.get_type("AdGroupAdOperation")
    op.create.ad_group = f"customers/{ACCOUNT}/adGroups/{ag_id}"
    op.create.status   = client.enums.AdGroupAdStatusEnum.PAUSED
    op.create.ad.final_urls.append(LP_URL)
    for h in rsa["headlines"]:
        a = client.get_type("AdTextAsset"); a.text = h
        op.create.ad.responsive_search_ad.headlines.append(a)
    for d in rsa["descriptions"]:
        a = client.get_type("AdTextAsset"); a.text = d
        op.create.ad.responsive_search_ad.descriptions.append(a)
    try:
        r = agad_svc.mutate_ad_group_ads(customer_id=ACCOUNT, operations=[op])
        print(f"  ✅ EN RSA created in {ag_id} → {r.results[0].resource_name}")
    except Exception as e:
        # Find the actual error message
        import re
        msgs = re.findall(r'message:\s*"([^"]+)"', str(e))
        for m in msgs[:5]:
            print(f"    ERR: {m}")
