# Phase 3 — Cowork Connector Setup Checklist

**Owner:** project-coordinator  
**Blocks:** Phase 4 (daily loop parallel run)  
**Estimated time:** 30–60 min  
**Status:** ✅ Complete (2026-06-12)

---

## What needs to happen

Six connectors must be wired in the Cowork platform UI. Once done, the Cowork
skills that declare `connectors: [bigquery, slack, ...]` in their frontmatter
will have live data access.

The monthly automation skills (`monthly-creative-report`, `monthly-performance-deck`)
fire on July 1st. **This setup must be complete before then.**

---

## Connectors to wire (in order)

### 1. BigQuery
Required by: `monthly-creative-report`, `monthly-performance-deck`, `daily-loop`, `weekly-review`, all analysis skills.

- Project: `angular-axle-492812-q4`
- Dataset: `qoyod_marketing`
- Auth: service account (`secrets/bigquery-key.json`) — same credentials used by Railway
- Verify by running a test query: `SELECT MAX(date) FROM qoyod_marketing.campaigns_daily`

### 2. Slack
Required by: `daily-slack-audit`, `monthly-performance-deck`, `daily-loop`

- Workspace: Qoyod workspace
- Bot token: `SLACK_BOT_TOKEN` (from Railway env)
- Channels needed: `#approvals`, `SLACK_CHANNEL_NOTIFY`
- **Note:** Uses a local dev custom Slack app — not the production bot. All channel IDs readable from Railway env.
- Verify by reading the last message in `#approvals`

### 3. Asana
Required by: `monthly-creative-report`, `monthly-performance-deck`, `daily-loop`, `campaign-manager`, `cro-specialist`

- Workspace: Qoyod Asana workspace (`ASANA_WORKSPACE_ID` from Railway env)
- Personal access token or OAuth: `ASANA_TOKEN` from Railway env
- Verify by listing projects

### 4. Meta Ads
Required by: `campaign-manager`, `creative-strategist`, `budget-shift`

- Account ID: from `META_AD_ACCOUNT_ID` Railway env
- Access token: `META_ACCESS_TOKEN`
- Verify by fetching campaigns list

### 5. Google Ads
Required by: `campaign-manager`, `keyword-autofix`

- MCC customer ID: `GOOGLE_ADS_MCC_ID`
- Child accounts: 5753494964 and 1513020554
- Developer token + refresh token: from Railway env
- Verify by listing campaigns for one child account

### 6. HubSpot
Required by: `growth-analyst`, `cro-specialist`, `project-coordinator`

- Access token: `HUBSPOT_ACCESS_TOKEN` (Railway env — NOT in local .env)
- Portal ID: 144952270
- Verify by fetching 1 lead from Lead Module (object 0-136)

---

## After wiring all 6 connectors

Run a dry-run of the daily loop:

```
/daily-loop
```

Check that it:
1. Reads from Asana (gets today's tasks)
2. Posts a digest to Slack
3. Does NOT attempt to run BQ analysis directly (that stays on Railway)

See `memory/14_learning_patterns.md` (2026-06-12 entry) — the Cowork sandbox
cannot run Python analysers or call Google/BQ APIs directly. The loop's role
is: read context from connectors → summarize → post to Slack.

---

## Phase 4 gate (14-day parallel run)

Once connectors are wired:
1. Schedule `/daily-loop` in Cowork at 08:00 Riyadh
2. Railway `main.py daily` continues running in parallel
3. Compare outputs daily for 14 days
4. When outputs match for 14 consecutive days → retire Railway LLM layer

Track progress in `memory/09_open_tasks.md` Phase 4 row.

---

## Google Drive prerequisites (before wiring the connector)

**Google Drive API:** ✅ Already enabled in GCP project (confirmed 2026-06-12)

**Remaining steps (manual — ~10 min):**

### Step 1 — Share the root folder with the service account
1. Open `secrets/bigquery-key.json` (or Railway env `GOOGLE_APPLICATION_CREDENTIALS_JSON`)
2. Copy the value of `"client_email"` (looks like `something@angular-axle-492812-q4.iam.gserviceaccount.com`)
3. Open [the shared Drive folder](https://drive.google.com/drive/folders/1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74)
4. Click **Share** → paste the service account email → set to **Editor** → uncheck "Notify people" → **Send**

### Step 2 — Create the two report subfolders
Inside the root folder, create these two subfolders:

| Subfolder name | Purpose | Env var to set |
|---|---|---|
| `Nexa Performance Reports/Monthly Decks` | Monthly performance deck (PPTX) | `GDRIVE_REPORTS_FOLDER_ID` |
| `Nexa Performance Reports/Creative Reports` | Monthly winning creatives Sheet | `GDRIVE_CREATIVE_REPORTS_FOLDER_ID` |

For each: right-click the folder → **Get link** → copy the ID from the URL (`/folders/<ID>`).

### Step 3 — Set the IDs in Railway
```bash
railway variables set GDRIVE_REPORTS_FOLDER_ID=<id-from-step-2>
railway variables set GDRIVE_CREATIVE_REPORTS_FOLDER_ID=<id-from-step-2>
```

Also add to your local `.env` if you run scripts locally.

### Step 4 — Verify access
```bash
railway run python -c "
from collectors.drive_reader import list_folder
import os
fid = os.getenv('GDRIVE_REPORTS_FOLDER_ID')
print('Files in Monthly Decks folder:', list_folder(fid))
"
```
Should return an empty list (not an error). If it throws a 403, the share in Step 1 didn't apply.

> Note: `collectors/drive_reader.py` doesn't exist yet — the Drive reader is described in `memory/10_google_drive.md`. If needed before the connector is wired, use the Drive MCP (google-drive connector in Cowork) instead.
