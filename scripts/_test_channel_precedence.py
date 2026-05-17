"""Smoke-test channel-aware pause precedence."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from qa import checks
checks._CACHE.clear()

print("=" * 75)
print("1. SEARCH campaign — should block on keyword + LP review")
print("=" * 75)
r = checks.check_pause_precedence({
    "name":  "[Recommendation | Pause] ImpressionShare_Search_AR_Invoice",
    "notes": "Asset level: campaign\nAction: pause",
})
print(f"  {r}")

print("\n" + "=" * 75)
print("2. SOCIAL campaign with bad ads — should block on ad-level")
print("=" * 75)
r = checks.check_pause_precedence({
    "name":  "[Recommendation | Pause] Snapchat_LeadGen_Prospecting_Interest_iOS_Instantform_v3",
    "notes": "Asset level: campaign\nAction: pause",
})
print(f"  {r}")

print("\n" + "=" * 75)
print("3. Bing campaign (search) — should block on keyword + LP review")
print("=" * 75)
r = checks.check_pause_precedence({
    "name":  "[Recommendation | Pause] Bing_Search_AR_Brand",
    "notes": "Asset level: campaign\nAction: pause",
})
print(f"  {r}")

print("\n" + "=" * 75)
print("4. Live ad-level keyword candidate scan")
print("=" * 75)
from analysers.campaign_health import _campaigns_with_keyword_pause_candidates
kw = _campaigns_with_keyword_pause_candidates(days=14)
print(f"Search campaigns with keyword-pause candidates: {len(kw)}")
for cid, kws in list(kw.items())[:5]:
    print(f"  Campaign {cid}: {len(kws)} bad keyword(s)")
    for k in kws[:3]:
        cpl_s = f"${k['cpl']:.0f}" if k['cpl'] else "no conv"
        print(f"    - '{k['keyword'][:40]}'  ${k['spend']:.0f} spend  cpl={cpl_s}  reasons={k['reasons']}")
