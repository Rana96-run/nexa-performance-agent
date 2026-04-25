# HubSpot Webhook Setup

## One-time steps (3 minutes)

### 1. Open your Private App in HubSpot
Settings → Integrations → Private Apps → select the Qoyod app

### 2. Copy the Client Secret
Under the app's **Auth** tab, copy the **Client Secret**.
It is already in `.env` as `HUBSPOT_CLIENT_SECRET` — no action needed.

### 3. Configure Webhook Subscriptions
Go to the app's **Webhooks** tab:

**Target URL:**
```
https://<your-railway-domain>/webhooks/hubspot
```
(After Railway deploy, replace with the actual domain. For local testing use ngrok.)

**Subscriptions to add (Lead module is primary):**

| Object | Subscription Type | Property | Priority |
|--------|-------------------|----------|----------|
| Lead (0-136) | `lead.creation` | — | High |
| Lead (0-136) | `lead.propertyChange` | `hs_pipeline_stage` | High |
| Deal | `deal.propertyChange` | `dealstage` | High |
| Contact | `contact.propertyChange` | `lifecyclestage` | Low (optional fallback) |

> The Lead module (`0-136`) is your primary CRM object. Qualification and
> disqualification are determined by `hs_pipeline_stage` labels, not contact
> lifecyclestage. Add the Contact subscription only if you also need lifecycle
> tracking at the contact level.

### 4. Test the endpoint
HubSpot will do a GET to `/webhooks/hubspot` to verify it's live.
It should return `{"status": "ok"}` — the route handles this.

---

## What happens on each event

| Trigger | Action |
|---------|--------|
| Lead created | Slack alert: name, source, campaign, audience, content, current stage |
| Lead `hs_pipeline_stage` → qualified stage (e.g. "Sales Qualified") | Slack alert + Asana "SQL Follow-up" task with full UTM context |
| Lead `hs_pipeline_stage` → disqualified stage | Slack alert with stage label + disqualification reason from `leads_disqualification_reason__ops` |
| Lead stage → any other stage (New, Attempting, Connected…) | Logged only — no alert |
| Deal `dealstage` → `closedwon` | Slack alert: deal name + USD amount + source/campaign |
| Deal `dealstage` → `closedlost` | Logged only (no Slack alert) |
| Contact `lifecyclestage` → `salesqualifiedlead` | Slack alert (fallback — only fires if Lead subscriptions not configured) |

---

## Local testing with ngrok

```bash
# Terminal 1 — run the Flask app
python -m reports.app

# Terminal 2 — expose it
ngrok http 8080

# Copy the https:// ngrok URL → paste into HubSpot Webhook Target URL
```

---

## Environment variables

| Variable | Source |
|----------|--------|
| `HUBSPOT_CLIENT_SECRET` | Already in `.env` — used for signature verification |
| `HUBSPOT_TOKEN` (`HUBSPOT_ACCESS_TOKEN`) | Already in `.env` — used to fetch contact/deal details |
| `SLACK_BOT_TOKEN` | Already in `.env` — used to post alerts |
| `SLACK_CHANNEL_NOTIFY` | Already in `.env` — channel where SQL / deal alerts go |
