Check the Railway deployment status and recent logs for the Nexa agent.

1. Check health endpoint:
   curl -s https://nexa-web-production-c859.up.railway.app/health

2. Check recent Railway logs (last 30 lines):
   railway logs --tail 30

3. Show:
   - Is the app live? (health endpoint returns {"status":"ok"})
   - Any errors in recent logs?
   - Last deployment time (from logs or Railway CLI)
   - Current git branch and last commit deployed

Keep the output concise — one paragraph summary + any error lines.
