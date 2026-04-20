# Deploying the Qoyod Performance Agent (no local Python needed)

Goal: the agent runs itself on schedule, pulls the latest code every run, and emails you on failure — you never need to keep Python running on your laptop.

## Option chosen: GitHub Actions (free, no server to maintain)

### One-time setup

1. **Push this project to a private GitHub repo** (private — it contains business logic).
2. In the repo, open **Settings → Secrets and variables → Actions → New repository secret**, and add every secret listed below.
3. Go to the **Actions** tab in GitHub and enable workflows if prompted.
4. Done. The scheduler in `.github/workflows/agent.yml` will fire daily at 08:00 Riyadh, weekly on Monday, monthly on the 1st, and quarterly on Jan/Apr/Jul/Oct 1st.

### Secrets to add

| Secret | Where it comes from |
|---|---|
| `ANTHROPIC_API_KEY` | .env |
| `GOOGLE_ADS_DEVELOPER_TOKEN` / `CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN` | .env |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | paste the **full contents** of `bigquery-key.json` |
| `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_1`, `META_AD_ACCOUNT_2` | .env |
| `HUBSPOT_ACCESS_TOKEN` | .env |
| `SLACK_ACCESS_TOKEN`, `SLACK_CHANNEL_NOTIFY`, `SLACK_CHANNEL_APPROVAL` | Slack admin |
| `ASANA_ACCESS_TOKEN`, `ASANA_PROJECT_*` (4 keys) | .env |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM_NAME` | .env |
| `EMAIL_ALL`, `EMAIL_TEAM_LEAD`, `EMAIL_TEAM_MANAGER`, `EMAIL_PERFORMANCE` | .env |
| `BQ_PROJECT_ID`, `BQ_DATASET`, `BQ_LOCATION` | .env |

Also add a **repository variable** (not secret): `NOTIFY_VIA = email` (change to `slack` or `both` once Slack is ready).

### Running on demand
- Actions tab → **Qoyod Performance Agent** → **Run workflow** → pick cadence → Run.

### Updating
Push to the repo's main branch. The next scheduled run picks up the new code automatically. No local Python, no manual pull.

### Failure alerts
If a run fails, an email goes to `EMAIL_TEAM_LEAD` with a link to the failed run's log.
