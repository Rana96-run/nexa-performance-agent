Run the cross-channel CPQL/CPL health check and show findings without creating tasks or posting to Slack.

Execute:
  cd "D:\Nexa Performance Agent"
  python -c "
from analysers.campaign_health import audit_campaign_health
findings = audit_campaign_health()
for f in findings:
    cpql = f'\${f[\"cpql\"]:.0f}' if f.get('cpql') else 'N/A'
    cpl  = f'\${f[\"cpl\"]:.0f}'  if f.get('cpl')  else 'N/A'
    print(f'{f[\"action\"].upper():10} {f[\"channel\"]:12} {f[\"campaign\"][:50]:50} CPQL={cpql} CPL={cpl} qual={f[\"qual_rate\"]:.0f}%')
print(f'Total: {len(findings)} findings')
"

Show a clean table of findings grouped by action (scale / pause / optimize / drilldown).
Highlight any junk-leads alerts.
Do NOT create Asana tasks or post to Slack — analysis only.
