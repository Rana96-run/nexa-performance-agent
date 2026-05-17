"""Smoke-test the campaign-pause-precedence guard end to end."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

print("=" * 70)
print("1. _campaigns_with_ad_pause_candidates() — live BQ scan")
print("=" * 70)
from analysers.campaign_health import _campaigns_with_ad_pause_candidates
cands = _campaigns_with_ad_pause_candidates(days=14)
print(f"Campaigns with at least one ad-level pause candidate: {len(cands)}")
for cid, ads in list(cands.items())[:5]:
    print(f"\n  Campaign {cid}: {len(ads)} bad ad(s)")
    for a in ads[:3]:
        print(f"    - {a['ad_name'][:50]}  ${a['spend']}  cpl=${a['cpl']}  "
              f"reasons={a['reasons']}  days={a['days']}")

print("\n" + "=" * 70)
print("2. QA gate check — simulate a campaign-pause Asana task")
print("=" * 70)
from qa import checks
checks._CACHE.clear()

# Pick a real campaign from the candidates if we found any, else use a synthetic name
if cands:
    # Look up the campaign name
    import os
    from collectors.bq_writer import get_client
    c = get_client()
    p = os.environ["BQ_PROJECT_ID"]; d = os.environ["BQ_DATASET"]
    sample_cid = list(cands.keys())[0]
    sql = f"SELECT campaign_name FROM `{p}.{d}.campaigns_daily` WHERE campaign_id='{sample_cid}' LIMIT 1"
    r = list(c.query(sql).result())
    sample_name = r[0].campaign_name if r else "Bing_Search_AR_Brand"
else:
    sample_name = "SyntheticTestCampaign"

task = {
    "name":  f"[Recommendation | Pause] {sample_name}",
    "notes": (f"Campaign exceeded CPL threshold for 7+ days.\n\n"
              f"Created: 2026-05-17\nDue: 2026-05-18\nPriority: High\n"
              f"Type: Recommendation\nChannel: microsoft_ads\n"
              f"Asset level: campaign\nAction: pause"),
}
r = checks.check_pause_precedence(task)
print(f"\nTask title: {task['name']}")
print(f"Result: {r}")

print("\n" + "=" * 70)
print("3. Task that should PASS — non-campaign-pause")
print("=" * 70)
r2 = checks.check_pause_precedence({
    "name":  "[Recommendation | Scale] SomeGoodCampaign",
    "notes": "Asset level: campaign\nAction: scale",
})
print(f"Result: {r2}")

print("\n" + "=" * 70)
print("4. Task already routed through drilldown — should PASS")
print("=" * 70)
r3 = checks.check_pause_precedence({
    "name":  f"[Recommendation | Pause] {sample_name}",
    "notes": "[PAUSE BLOCKED — ad-level cleanup first] Asset level: campaign\nAction: pause",
})
print(f"Result: {r3}")
