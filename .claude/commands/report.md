Trigger a manual on-demand performance report for the Nexa agent.

Run the daily cadence manually:
  cd "D:\Nexa Performance Agent"
  python -c "from main import run_cadence; run_cadence('on_demand', force=True)"

Show what was collected, how many Asana tasks were created, and what was sent to Slack.
Confirm the report is visible at the dashboard URL.
