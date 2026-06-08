"""
scripts/setup_databox.py

One-time setup: connects Databox and runs the first full historical push.

Usage:
    railway run python scripts/setup_databox.py
"""
import subprocess
import sys


_STEPS = """
=============================================================
  DATABOX SETUP — 3 clicks
=============================================================

Step 1 — Open this URL in your browser (copy + paste):
  https://app.databox.com/databox-designer#

  Then: left sidebar → "+" (New data source)
        → Custom
        → Push Custom Data
        → Name it: "Qoyod BQ"
        → Click "Generate token"
        → Copy the token

Step 2 — Paste the token below when prompted.
          It will be saved to Railway automatically.

Step 3 — A historical backfill (365 days) will run once.
          Future daily runs are automatic (every 6h with BQ refresh).
=============================================================
"""

print(_STEPS)

token = input("Paste your Databox token here: ").strip()
if not token:
    print("No token provided — exiting.")
    sys.exit(1)

# Save to Railway
print("\nSaving DATABOX_TOKEN to Railway...")
result = subprocess.run(
    ["railway", "variables", "set", f"DATABOX_TOKEN={token}"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print(f"Railway CLI error: {result.stderr}")
    print("Set the token manually: railway variables set DATABOX_TOKEN=<token>")
    sys.exit(1)
print("Token saved to Railway.")

# Also write to local .env for local runs
env_path = ".env"
try:
    with open(env_path, "r") as f:
        content = f.read()
    if "DATABOX_TOKEN=" in content:
        lines = [f"DATABOX_TOKEN={token}" if l.startswith("DATABOX_TOKEN=") else l
                 for l in content.splitlines()]
        with open(env_path, "w") as f:
            f.write("\n".join(lines) + "\n")
    else:
        with open(env_path, "a") as f:
            f.write(f"\nDATABOX_TOKEN={token}\n")
    print("Token written to local .env")
except Exception as e:
    print(f"Could not update .env (non-fatal): {e}")

# Run the full historical backfill (365 days)
print("\nRunning historical backfill (365 days — this takes a few minutes)...")
import os
os.environ["DATABOX_TOKEN"] = token

from collectors.databox_pusher import run_push
total = run_push(days=365)
print(f"\nDone. {total:,} data points pushed to Databox.")
print("\nNext steps in Databox:")
print("  1. Go to app.databox.com → Metrics tab")
print("  2. Find 'Qoyod BQ' under Custom data sources")
print("  3. You'll see metrics: spend, leads, sqls, cpql, cpl, roas, ...")
print("  4. Each has dimensions: grain, channel, campaign_id, campaign,")
print("                          adset_id, adset, ad_id, ad, keyword, etc.")
print("  5. Build dashboards by dragging metrics and filtering by grain")
