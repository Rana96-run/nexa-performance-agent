# Skill — Funnel.io (learn only, read-only)

Use when Amar says "audit Funnel", "what does the Looker board compute",
"reconcile Funnel vs our BQ", or "what custom dims/metrics does Funnel have".

**Posture:** we do NOT write to Funnel. No push, no webhook call, no
`collectors/funnel_*.py`. We only read to learn the existing setup so our
Streamlit dashboards + agent outputs use the same definitions Amar's team
already trusts. See `memory/12_funnel_io.md` for the full context.

## Access

| Purpose | Creds | Status |
|---|---|---|
| Read normalized rows (API) | `FUNNEL_API_TOKEN` + `FUNNEL_ACCOUNT_ID` + `FUNNEL_PROJECT_ID` | **pending** — ask Amar |
| Read custom-dim / metric definitions | UI only — Funnel has no read API for these | manual audit |
| Read via BQ export | `FUNNEL_BQ_DATASET` | **pending** — check if export is enabled |
| File Import Webhook | `FUNNEL_WEBHOOK_URL` + `FUNNEL_WEBHOOK_TOKEN` | recorded, **not called** |

## 1. Audit custom dims + metrics (UI, no creds needed)

Funnel's API does **not** expose definitions. Amar screen-shares or
exports screenshots, we transcribe.

Checklist to capture for each **Custom Dimension**:
- Name
- Sources it applies to (Google Ads / Meta / Snap / …)
- Rule body (conditions → result)
- Expected output values (enumerate if finite, e.g. `brand | non_brand | pmax`)

Checklist to capture for each **Custom Metric**:
- Name
- Type: rule-based (SUM/COUNT/MIN/MAX/NONE over a source field) or
  formula (arithmetic over rule-based metrics — cannot nest)
- Expression
- Intended unit (SAR? ratio? count?)

Paste the captures into `memory/12_funnel_io.md` under a new heading:
```
## Custom Dimensions (audited YYYY-MM-DD)
## Custom Metrics (audited YYYY-MM-DD)
```

## 2. List dims + metrics available via API (once token lands)

```python
import os, requests
url = (f"https://api.funnel.io/api/account/v1/"
       f"{os.environ['FUNNEL_ACCOUNT_ID']}/project/"
       f"{os.environ['FUNNEL_PROJECT_ID']}")
r = requests.get(url, params={
    "group_by":  "day",
    "date_from": "2026-04-01",
    "date_to":   "2026-04-07",
    "apiToken":  os.environ["FUNNEL_API_TOKEN"],
}, timeout=60)
r.raise_for_status()
data = r.json()
# First row's keys = all available dims + metrics (standard + custom)
print(sorted(data["rows"][0].keys()) if data.get("rows") else data)
```

The returned column names are the **effective** schema. Anything we
don't recognize = a custom dim/metric we need to go back and audit in
the UI.

## 3. Pull a baseline snapshot

```python
# Last 30 days, day × channel × campaign × cost × leads
r = requests.get(url, params={
    "group_by":  "campaign_day",
    "date_from": (date.today() - timedelta(days=30)).isoformat(),
    "date_to":   date.today().isoformat(),
    "apiToken":  os.environ["FUNNEL_API_TOKEN"],
}, timeout=120)
# write r.json() to memory/_snapshots/funnel_YYYY-MM-DD.json
```

This snapshot becomes the reference for reconciliation work.

## 4. Reconcile Funnel vs our BQ

For each (day, channel) in the snapshot, compare to our
`channel_roas_daily`. Expected drift:
- **Cost**: ≤ 3% (currency or TZ quirks)
- **Leads**: often higher drift — our `qualified_leads` uses HubSpot
  Lead module (0-136), Funnel uses Contact.lifecyclestage. Different
  denominators → different CPQLs. Document which is which.

When drift > 5% on cost, check in order:
1. Funnel `channel_unified` rule vs our `CHANNEL_MAP`
2. Funnel workspace currency vs our SAR
3. Funnel workspace time zone vs our Asia/Riyadh
4. Funnel account IDs vs our `.env` (make sure it's the same MCC + child accounts)

## 5. Trace a single HubSpot SQL through Funnel

Pick one contact we know crossed lifecyclestage → SQL yesterday.

1. In Funnel UI, filter Contacts by that email/id.
2. Follow Associations → Deal. Note the deal stage.
3. Note which `channel_unified` row carries the cost that should be
   attributed to this SQL.
4. Verify that (cost / SQL-count) matches whatever Looker tile claims
   to be CPQL.

Document the path in `memory/12_funnel_io.md` under
`## HubSpot join trace (verified YYYY-MM-DD)`.

## 6. Translate to dashboard tiles

Once dims/metrics are audited, for each one:
- Does it belong on our Streamlit dashboard? (overlap, or gap-filler)
- Which page? (Paid Overview / Organic Overview / Channel Deep Dive /
  Leads Funnel / Insights)
- Exact formula reference — every tile gets a "?" tooltip quoting the
  Funnel definition verbatim when we're mirroring it.

Maintain the spec in `memory/13_dashboard_spec.md` (create when the
audit is far enough along to design from).

## Don'ts

- **Don't** push data to Funnel. The webhook exists, we don't call it.
- **Don't** invent new metric names when Funnel already has one. Use the
  existing label so Looker and Streamlit read the same.
- **Don't** assume "qualified lead" = the same thing in Funnel and our
  BQ. Funnel = Contact lifecyclestage. Ours = Lead module 0-136.
- **Don't** nest Funnel formula metrics (Funnel won't allow it anyway).
- **Don't** attempt to read custom-dim definitions from the API — no
  such endpoint exists. Use the UI.

## Pitfalls to log

New Funnel quirks → append one line to `memory/08_pitfalls.md` under
`### Funnel.io`.
