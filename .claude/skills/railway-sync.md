# railway-sync — pull Railway env vars → local .env

## Purpose

Sync environment variables from Railway (production) into the local `.env` file.
Run this whenever tokens are updated in Railway so local collectors and tests use
the same credentials as production.

The sync also runs automatically every 6 hours via the scheduled task in
`.claude/settings.json` (PostToolUse / SessionStart hook, or cron task).

## When to invoke this skill

- User says "I updated [token] in Railway"
- A collector returns 0 rows / auth error locally but works on Railway
- At the start of any session where tokens may have rotated (LinkedIn 60-day, TikTok 24-hour)
- Whenever `railway variables` output differs from `.env`

## Steps

### 1. Fetch all Railway variables

```bash
cd "D:\Nexa Performance Agent"
railway variables --json > /tmp/railway_vars.json
```

If the Railway CLI isn't linked, run `railway link` first and select the project.

### 2. Update .env

Run the sync helper (creates it if needed):

```python
import json, re, pathlib

raw   = pathlib.Path("/tmp/railway_vars.json").read_text()
rvars = json.loads(raw)

env_path = pathlib.Path("D:/Nexa Performance Agent/.env")
env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

# Keys we want to pull from Railway into local .env
SYNC_KEYS = [
    "LI_ACCESS_TOKEN", "LI_REFRESH_TOKEN", "LI_AD_ACCOUNT_URN",
    "TIKTOK_ACCESS_TOKEN", "TIKTOK_REFRESH_TOKEN",
    "MS_REFRESH_TOKEN",
    "META_ACCESS_TOKEN",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "SNAP_ACCESS_TOKEN", "SNAP_REFRESH_TOKEN",
]

updated = []
for key in SYNC_KEYS:
    if key not in rvars:
        continue
    val = rvars[key]
    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={val}"
    if re.search(pattern, env_text, re.MULTILINE):
        env_text = re.sub(pattern, replacement, env_text, flags=re.MULTILINE)
    else:
        env_text += f"\n{replacement}"
    updated.append(key)

env_path.write_text(env_text, encoding="utf-8")
print(f"Synced {len(updated)} keys: {updated}")
```

### 3. Verify

```bash
python -c "
from dotenv import load_dotenv; load_dotenv(override=True)
import os
keys = ['LI_ACCESS_TOKEN','TIKTOK_ACCESS_TOKEN','MS_REFRESH_TOKEN']
for k in keys:
    v = os.getenv(k,'')
    print(f'{k}: {v[:12]}...' if v else f'{k}: MISSING')
"
```

### 4. Quick smoke-test the updated connector

If the sync was triggered by a LinkedIn update:
```bash
python -c "from collectors import linkedin_bq; print(linkedin_bq.collect_and_write(days=3))"
```

For TikTok:
```bash
python -c "from collectors import tiktok_bq; print(tiktok_bq.collect_and_write(days=3))"
```

## Automatic 6-hour sync (scheduled)

A Railway cron job (`railway up` service) runs
`railway variables --json` and patches `.env` on the Railway container itself
every 6 hours — so production is always in sync.

For **local** automatic sync, set up a Windows Task Scheduler entry:

```
Task name:   RailwayEnvSync
Trigger:     Every 6 hours, starting at session login
Action:      powershell -Command "cd 'D:\Nexa Performance Agent'; railway variables --json | python scripts/sync_railway_env.py"
```

Or use the Claude Code hook in `.claude/settings.json`:
```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "cd /d \"D:\\Nexa Performance Agent\" && railway variables --json 2>nul | python scripts/sync_railway_env.py 2>nul || true"
      }]
    }]
  }
}
```

## Notes

- Never commit `.env` — it is gitignored.
- Railway is the source of truth. Local `.env` is a read cache.
- LinkedIn tokens expire every 60 days. TikTok access tokens expire every 24 hours.
  Both rotate automatically via their respective refresh scripts on Railway.
