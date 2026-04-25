# Deploying the Qoyod Performance Agent (no local Python needed)

Goal: the agent runs itself on schedule, pulls the latest code every run, and emails you on failure. Pick one of two hosts — or both (GitHub as source of truth, Replit for browser-editing).

---

## Option A — GitHub Actions (free, push-to-deploy)

### One-time setup
1. Push this project to a **private** GitHub repo.
2. Repo Settings → Secrets and variables → Actions → paste each secret below.
3. Actions tab → enable workflows if prompted.
4. Done. `.github/workflows/agent.yml` runs daily 08:00 Riyadh, weekly Mon, monthly 1st, quarterly Jan/Apr/Jul/Oct 1st.

### Manual run
Actions tab → **Qoyod Performance Agent** → **Run workflow** → pick cadence.

### Updating
Push to `main`. Next scheduled run picks up the new code. No local Python.

---

## Option B — Replit (browser-editing, ~$20/mo for scheduled)

### One-time setup
1. Replit → **Import from GitHub** (or upload the project folder).
2. In the repl, open **Secrets** (padlock icon in sidebar) and paste each secret below.
3. Click **Deploy** → **Scheduled** → create four deployments:

   | Cadence | Cron (UTC) | Command |
   |---|---|---|
   | Daily | `0 5 * * *` | `python main.py daily` |
   | Weekly | `5 5 * * 1` | `python main.py weekly` |
   | Monthly | `10 5 1 * *` | `python main.py monthly` |
   | Quarterly | `15 5 1 1,4,7,10 *` | `python main.py quarterly` |

4. Replit auto-installs from `requirements.txt` on first run.

### Manual run
Hit **Run** in the workspace, or **Run deployment** in the Deployments tab.

### Updating
Edit in the browser, or link the repl to GitHub and push — the repl pulls automatically.

### Replit-specific notes
- `.replit` and `replit.nix` are already committed; Replit will use them.
- `NOTIFY_VIA=email` and `GOOGLE_APPLICATION_CREDENTIALS=/tmp/bigquery-key.json` are set in `.replit [env]`.
- Paste the full contents of `bigquery-key.json` into a Secret named `GOOGLE_APPLICATION_CREDENTIALS_JSON`. `bootstrap.py` writes it to `/tmp/bigquery-key.json` on startup.

---

## Secrets to add (same names for both hosts)

| Secret | Source |
|---|---|
| `ANTHROPIC_API_KEY` | .env |
| `GOOGLE_ADS_DEVELOPER_TOKEN` / `CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN` | .env |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | paste full contents of `bigquery-key.json` |
| `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_1`, `META_AD_ACCOUNT_2` | .env |
| `HUBSPOT_ACCESS_TOKEN` | .env |
| `SLACK_ACCESS_TOKEN`, `SLACK_CHANNEL_NOTIFY`, `SLACK_CHANNEL_APPROVAL` | Slack admin |
| `ASANA_ACCESS_TOKEN`, `ASANA_PROJECT_DAILY_ACTIVITY`, `ASANA_PROJECT_OPTIMIZATION`, `ASANA_PROJECT_CAMPAIGNS_HUB`, `ASANA_PROJECT_SEASONAL` | .env |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM_NAME` | .env |
| `EMAIL_ALL`, `EMAIL_TEAM_LEAD`, `EMAIL_TEAM_MANAGER`, `EMAIL_PERFORMANCE` | .env |
| `BQ_PROJECT_ID`, `BQ_DATASET`, `BQ_LOCATION` | .env |

GitHub Actions also reads `NOTIFY_VIA` as a **Variable** (Settings → Variables → Actions). Replit reads it from `.replit [env]`.

---

## Failure alerts (both hosts)
- GitHub Actions → emails `EMAIL_TEAM_LEAD` with a link to the failed run.
- Replit → check the Deployment logs; set up Replit's built-in notification hooks if desired.
