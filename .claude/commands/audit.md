Run the Google Ads audit (Impression Share, Quality Score, search terms, keyword review).

Execute:
  cd "D:\Nexa Performance Agent"
  python -c "from analysers.google_ads_audit_tasks import create_audit_tasks; tasks = create_audit_tasks(); print(f'{len(tasks)} task(s) created')"

Show the audit findings: which campaigns have low IS, which keywords have low QS, which search terms are ready to promote, which keywords should be paused.
List the Asana task GIDs created.
