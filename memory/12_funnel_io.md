# Funnel.io — Role in the Qoyod Stack

Funnel.io is a **data unification layer** between ad platforms + CRM and
reporting tools. In this project it sits in parallel to our own collectors,
not instead of them: we use Funnel for cross-channel normalization and
Looker Studio boards that were already built there; our BigQuery pipeline
keeps going for the Streamlit dashboard + agent decisions.

## The three layers (Funnel's model)

| Layer | What it does | Qoyod example |
|---|---|---|
| **Connect** | Pulls raw data from each platform via connector | Google Ads, Meta (2 accts), Snap, TikTok, LinkedIn, Microsoft Ads, HubSpot |
| **Organize** | Normalizes schemas + creates **Custom Dimensions** and **Custom Metrics** across sources | Unified channel dim, campaign-type classifier, blended CPL |
| **Share** | Exports normalized dataset out | Looker Studio (via BQ), BigQuery dataset, Google Sheets |

## Custom Dimensions — how they work

- **Location in UI:** Organize → Custom Dimensions → Create → Rule-based
- **Rule syntax:** condition → result ("when X then Y"), row-level
  - Condition fields: any source field (campaign name, account ID, date, etc.)
  - Result: literal text, regex extract, concatenation, date transforms
- **Typical Qoyod patterns to check for in our workspace:**
  - `channel_unified` — maps Meta/Google/Snap/LI/TikTok/MS account IDs to
    canonical channel names (should mirror our `channel_roas_daily.channel`
    values)
  - `campaign_type` — regex over campaign name → `brand | non_brand |
    pmax | retargeting | prospecting`
  - `funnel_stage` — derived from campaign naming or objective → `tof |
    mof | bof`
  - `region` / `market` — when we run KSA vs GCC separately

**API limitation:** there is **no documented read API** for custom dim/metric
definitions. To inspect, use the UI or ask Funnel support for a config
export. Track our custom dims in this file once we audit them.

## Custom Metrics — how they work

Two flavors:
- **Rule-based** (source level) — aggregations on a single source:
  SUM / COUNT / MIN / MAX / NONE
- **Formula-based** (visualization level) — arithmetic over rule-based
  metrics: division, multiplication, conditional. **No nesting** —
  formulas can't reference other formulas.

**Typical Qoyod patterns:**
- `blended_cpl = SUM(cost_all_sources) / SUM(leads_all_sources)`
- `blended_cpql = SUM(cost_all_sources) / SUM(sqls_hubspot)`
- `channel_cac = cost_by_channel / won_deals_by_channel`
- `roas = (conversions × aov) / cost`

## How HubSpot is joined to ad spend

Funnel's HubSpot connector pulls:
- **Contacts** + all properties (incl. custom), associations to deals
- **Deals** + stage, amount, pipeline, associations to contacts
- **Companies, Tickets, Activities** (calls/emails/meetings/tasks)
- **Owners**

**Key pitfall for us:** Funnel **does not natively expose the HubSpot
Lead module** (object `0-136`). So "qualified leads" in Funnel = Contacts
filtered by a property (usually `lifecyclestage = salesqualifiedlead`),
not our Lead-module qualifieds. This is a real attribution gap — see
`07_attribution.md`.

**Join path inside Funnel:** Contact → Associations → Deal → Deal stage.
For CPQL, filter Contacts by SQL lifecyclestage and divide by channel
cost. Funnel handles the cross-source math as long as both sources share
a common dimension (channel, date).

## Connection flow (what talks to what)

```
  Google Ads ─┐
  Meta (x2)  ─┤
  Snapchat   ─┤     ┌──────────────────────┐
  TikTok     ─┼───► │     FUNNEL.IO        │
  LinkedIn   ─┤     │  (Connect · Organize │
  Microsoft  ─┤     │    · Share layer)    │
  HubSpot    ─┘     └──────┬───────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        Looker Studio  BigQuery    Google Sheets
        (existing      (Funnel_    (ad-hoc
         boards)        export_*)   exports)
```

Our own pipeline runs in parallel:

```
  Same platforms ─► our collectors ─► BigQuery (qoyod_marketing)
                                        │
                            ┌───────────┼───────────┐
                            ▼           ▼           ▼
                       Streamlit    Agents       Dashboard pages
                        dashboard   (Analyst,    (paid + organic
                                     PM, Paid)    split)
```

**Why both?**
- Funnel = fast path to a working board with custom dims/metrics we can
  reference but can't manipulate from code
- Own pipeline = agent-readable, decision-ready BigQuery, fully code-owned

## Export / destinations

| Destination | Setup | Refresh cadence | Notes |
|---|---|---|---|
| **BigQuery** | Funnel native connector → `Funnel_export_<workspace>` dataset | Incremental; only changed months | Schema auto-generated; not manually configurable |
| **Looker Studio** | Use BQ connector in Looker Studio pointed at Funnel's dataset | Manual "refresh fields" after schema change | Our existing Looker boards likely read this |
| **Google Sheets** | Direct export | Scheduled | Used for ad-hoc workbooks |
| **REST API** | `https://api.funnel.io/api/account/v1/$ACCOUNT_ID/project/$PROJECT_ID` | On-demand | **Reads data only; no API for custom-dim definitions** |

## Funnel REST API (for agent access)

**Auth:** workspace API token.
**Endpoint shape:**
```
GET https://api.funnel.io/api/account/v1/{account_id}/project/{project_id}
    ?group_by=day|campaign_day
    &date_from=YYYY-MM-DD
    &date_to=YYYY-MM-DD
    &apiToken={token}
```
Returns normalized rows with all dimensions + metrics visible in the UI
(including custom ones).

**Use cases for the Analyst agent:**
- Pull blended CPL/CPQL time series
- Cross-check our BigQuery numbers against Funnel's normalized view
- Surface gaps between "Funnel Contact-SQL count" vs "our Lead-module
  qualified count"

## Pitfalls (add to 08_pitfalls.md once confirmed)

- **Rate limits:** workspace quota on a 60-second window; also inherits
  per-platform quotas (Google Ads, Meta, …)
- **Data lag:** retries on failed pulls; hours of lag during platform
  outages are normal
- **"Too many rows" errors** on wide queries — paginate or filter
- **No custom-dim read API** — dims/metrics must be audited in the UI
- **HubSpot Lead-module blind spot** — Funnel only sees the Contact module
- **Formula metrics can't nest** — if you need A/B where A is already a
  formula, compute it rule-based first

## Posture: LEARN ONLY — do not push

**We don't write to Funnel.** Funnel is the reference system Amar's team
already uses; our job is to understand what's in it so our Streamlit
dashboards + agent outputs match the mental model the team already has.
No `collectors/funnel_push_*.py`. No writes of any kind.

The File Import Webhook endpoint Amar shared is recorded below for
completeness but is **not called** by any code in this repo.

```
FUNNEL_WEBHOOK_URL=https://fileimport-webhook.funnel.io/146902fd-...
FUNNEL_WEBHOOK_TOKEN=0e63df38-...
```

## What we need to learn (and why)

Before we design `dashboard/pages/*.py` we must answer:

| Question | Why it matters for the dashboard |
|---|---|
| What **custom dimensions** exist and what rules produce them? | Our pages must use the same channel / campaign-type / funnel-stage / region labels the team reads in Looker, or numbers will look "wrong" even when they're right. |
| What **custom metrics** exist and how are they computed? | We need the exact blended_cpl / blended_cpql / channel_cac / ROAS formulas so our Streamlit tiles match Funnel to the decimal. |
| How is **HubSpot joined to ad spend** inside Funnel? | Reveals the attribution logic (Contact.lifecyclestage vs Lead module, associations path). Our CPQL must say which definition it's using. |
| What **time zone + currency** does Funnel normalize to? | Drift source #1 when reconciling. Ours is Asia/Riyadh; reporting in USD (peg 3.75 SAR/USD via `config.USD_SAR_PEG`); ad-account natives preserved alongside. |
| What **date range + grain** do the existing Looker boards default to? | Our default filters should mirror them (last 7d? MTD? campaign_day vs day?). |
| What **channel names** does `channel_unified` emit? | Must equal our `CHANNEL_MAP` values in `collectors/views.py`. |
| Which **dimensions are missing** from Funnel that the team still asks for? | That's where our Streamlit dashboard adds value (e.g. HubSpot Lead-module 0-136, adset/ad grain, creative-type tags). |

## Questions to ask Amar (batch these, don't drip)

1. Can we get **read-only API token + account_id + project_id**? (Pending)
2. Which Looker Studio boards are "the source of truth" today? URLs please.
3. Is the Funnel BQ export enabled? If yes, what's the dataset name?
4. What workspace currency is configured? (Funnel-side likely SAR; we report in USD downstream — confirm Funnel's native then we convert.)
5. What time zone is the workspace on? (Assume Asia/Riyadh; confirm.)
6. For CPQL in Looker: is "qualified" defined as (a) Contact
   lifecyclestage = SQL, (b) Deal stage crosses a probability, or (c)
   a custom property? We need the literal rule.
7. Any **custom dims/metrics** the team considers "don't touch"? We want
   to mirror them exactly, not reinvent.
8. Are the Meta / Snap / Google Ads accounts connected to Funnel the
   **same** accounts in our `.env`? (Name + ID cross-check.)
9. Is there a campaign-naming convention Funnel relies on for
   `campaign_type` / `funnel_stage` regex? We should publish it so new
   campaigns stay compatible.
10. What gets exported to Google Sheets on a schedule, and who consumes
    those sheets? We may be able to replace or supplement in Streamlit.

Log the answers at the bottom of this file under a new
`## Workspace facts (confirmed YYYY-MM-DD)` heading.

## Learning workflow (no code needed initially)

1. **UI walkthrough** — Amar screen-shares Organize tab. Screenshot each
   custom dim + metric. Paste into this file.
2. **Looker board audit** — for each existing board, list the tiles, what
   metric they cite, and the filter set. Goal: every tile becomes a
   question we know how to answer in our Streamlit dashboard.
3. **Dimension × metric matrix** — build a grid of which metrics are
   available broken down by which dims. This tells us what's already
   possible in Funnel vs what we'd need our own BQ for.
4. **HubSpot join trace** — follow one known SQL contact through Funnel's
   Contact → Associations → Deal path; compare the resulting CPQL to
   what our BQ `channel_roas_daily` produces.

## Dashboard design implications (carry forward)

- **Terminology parity** — our Streamlit page titles and column headers
  must read the same as the Looker boards. `Blended CPL`, `Channel CAC`,
  `Qualified Leads (SQL)` — not our own coinages.
- **Explicit definitions per tile** — every metric tile gets a
  "?" tooltip with the exact formula and the data source (Funnel vs our
  BQ). Ambiguity is the enemy.
- **Side-by-side reconciliation page** — one dashboard page that shows
  Funnel blended_cpl next to our blended_cpl per day; if drift > 5%,
  flag the row. This is the trust-builder.
- **Gaps become our unique value** — HubSpot Lead-module (0-136)
  qualified counts, creative-type breakdowns, adset/ad grain — these
  are things Funnel can't show. Our dashboard makes them visible.
- **Agent questions** — when the Analyst agent asks "why is CPL up on
  channel X?", it should reference both sources (Funnel and our BQ) and
  note which one the user is looking at in Looker.

## .env keys

```
FUNNEL_WEBHOOK_URL=          # recorded only; NOT called from code   [set]
FUNNEL_WEBHOOK_TOKEN=        # recorded only; NOT called from code   [set]
FUNNEL_API_TOKEN=            # read API, workspace-level             [pending]
FUNNEL_ACCOUNT_ID=           # for read-API URL path                 [pending]
FUNNEL_PROJECT_ID=           # for read-API URL path                 [pending]
FUNNEL_BQ_DATASET=           # e.g. Funnel_export_qoyod              [pending]
FUNNEL_LOOKER_REPORT_ID=     # URL of the canonical Looker board     [pending]
```

## First tasks once read creds land

1. `GET` the API; **list available dimensions + metrics** (standard + custom)
2. Inventory every **Custom Dimension** (name, rule, sources it applies to)
3. Inventory every **Custom Metric** (rule-based vs formula, expression)
4. Identify overlap with our own BQ views: if Funnel has `blended_cpl`
   and we have it in `channel_roas_daily`, reconcile per day
5. Map Funnel's `channel_unified` values → our `CHANNEL_MAP` in
   `collectors/views.py` so naming is identical across stacks
6. Pull 30 days of (day × channel × campaign × blended_cpl) as a CSV
   snapshot to `memory/_snapshots/funnel_YYYY-MM-DD.csv` so we have a
   baseline to diff against later
7. Translate each confirmed metric into a Streamlit tile spec in
   `memory/13_dashboard_spec.md` (create when ready)

## Docs to keep nearby

- Custom Dimensions: https://help.funnel.io/en/articles/1622167
- Creating a Custom Dim: https://help.funnel.io/en/articles/9449152
- Custom Metrics: https://help.funnel.io/en/articles/2308146
- ROAS metric example: https://help.funnel.io/en/articles/10304878
- Export to BQ: https://help.funnel.io/en/articles/399854
- Export to Looker (via BQ): https://help.funnel.io/en/articles/8425527
- HubSpot dims/metrics: https://help.funnel.io/en/articles/6956025
- Rate limits: https://help.funnel.io/en/articles/2668633
- File Import Webhook: https://help.funnel.io/en/articles/8439795
