"""Smoke-test the QA gate end-to-end."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from qa.gate import gate
from qa import checks

print("=" * 60)
print("1. Dashboard QA status (read-only)")
print("=" * 60)
status, results = gate.dashboard_status()
print(f"Status: {status}")
for r in results:
    print(f"  {r}")

print("\n" + "=" * 60)
print("2. Slack format check — should FAIL on IS abbreviation")
print("=" * 60)
r = checks.check_slack_format("Daily report — IS at 45% lost", "daily")
print(f"  {r}")

print("\n3. Slack format check — should PASS with URL + spelled-out terms")
r = checks.check_slack_format(
    "Daily report — https://hex.tech/qoyod for 2026-05-15 (Impression Share 45%)",
    "daily",
)
print(f"  {r}")

print("\n" + "=" * 60)
print("4. Asana footer — should FAIL on missing footer")
print("=" * 60)
r = checks.check_asana_footer({"notes": "Pause this campaign"})
print(f"  {r}")

print("\n5. Asana footer — should PASS with complete footer")
r = checks.check_asana_footer({"notes": (
    "Pause underperformer.\n"
    "Created: 2026-05-16\nDue: 2026-05-17\nPriority: High\n"
    "Type: Recommendation\nChannel: meta"
)})
print(f"  {r}")

print("\n" + "=" * 60)
print("6. BQ write sanity — should FAIL on internal dupes")
print("=" * 60)
dup_rows = [
    {"date": "2026-05-15", "channel": "meta", "campaign_id": "A", "spend": 10},
    {"date": "2026-05-15", "channel": "meta", "campaign_id": "A", "spend": 12},
]
r = checks.check_bq_write("campaigns_daily", dup_rows, ["date", "channel", "campaign_id"])
print(f"  {r}")

print("\n7. Numeric claims — should WARN if many orphan figures")
r = checks.check_numeric_claims("Spend was $999999.99 and $888888.88 yesterday")
print(f"  {r}")

print("\n" + "=" * 60)
print("8. Freshness check (live BQ)")
print("=" * 60)
r = checks.check_freshness()
print(f"  {r}")

print("\n" + "=" * 60)
print("9. Multi-account presence (live BQ)")
print("=" * 60)
r = checks.check_multi_account_presence()
print(f"  {r}")
