"""Smoke-test the new ping format (no actual post)."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

# Disable actual Slack post — just see what would be sent
os.environ["SLACK_BOT_TOKEN"] = ""

from notifications.slack_ping import ICON, _dashboard_url

print(f"Dashboard URL: {_dashboard_url()}")
print()
print("Sample pings (what the team would now see in Slack):")
print()

samples = [
    ("warn",  "BQ↔HubSpot drift on 2 days (worst: 2026-05-14 BQ 147 vs HS 148)"),
    ("alert", "QA gate blocked slack (3 check failures, first: numeric_claims)"),
    ("warn",  "BQ↔HubSpot drift (2026-05-09 to 2026-05-16): paid leads +6.2%, 1 channel(s)"),
    ("warn",  "8 anomaly(ies) vs 7d baseline — biggest: snapchat spend up 142%"),
    ("alert", "9 social campaigns have ad-level pause candidates"),
    ("ok",    "Daily reconciliation passed"),
]

for status, headline in samples:
    text = f"{ICON[status]} {headline} → {_dashboard_url()}"
    print(f"  [{status:5s}]  {text}")
    print(f"           length: {len(text)} chars (cap is 240)")
    print()

print("=" * 70)
print("Compare to the OLD message that triggered this fix (556 chars):")
print("=" * 70)
print("""
🚨 *BQ ↔ HubSpot daily check — 2026-05-18*
Drift detected (>5.0% AND >5 leads).
```
date            BQ    HS   diff      %
----------------------------------------
2026-05-17      18    99    -81  81.8% ⚠️
2026-05-14     147   148     -1   0.7%
... (5 more rows)
```
Check: scheduler running? recent BQ syncs successful? views materialized?
""")
