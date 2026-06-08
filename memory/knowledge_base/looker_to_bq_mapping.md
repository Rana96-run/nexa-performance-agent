# Looker Studio → BigQuery Replication Map

Source: user's 3 Looker dashboards (PDFs in `md_files/looker_reports/`).
Goal: every tile / chart / table below is reproduced as a BQ view so we can regenerate these reports from a single source of truth (and serve them to both Looker Studio AND our own web dashboard).

---

## 1. Live Campaigns Dashboard (bookkeeping-focused, realtime)

**Top-line KPI strip (10 tiles, period-over-period delta):**
- Bookkeeping Leads · Bookkeeping Qualified · Bookkeeping Disqualified · Deals Amount · Won Amount
- Bookkeeping Cost · CPL Bookkeeping · CPQL Bookkeeping · Qualified% (Q+UnQ) · Disqualified% (Q+UnQ)

**Charts:**
- Donut: Lead stage by bookkeeping leads (Disqualified / Qualified / Attempting)
- Donut: Source by bookkeeping leads (Meta 31.3% / Snap 23.8% / Google 14% / Offline 10.5% / TikTok 9.7% / Others / Email / Organic / MS Ads)

**Drill-down tables (3 levels):**
- Campaign Name × (Cost, Leads BK, CPL BK Pipeline, Leads Qualified, CPQL BK, Leads Disqualified, CPL Total, CPQL total)
- Ad Group Name × same metrics
- Ad Name × same metrics

→ BQ views: `bk_live_kpis`, `bk_live_by_source`, `bk_live_by_stage`, `bk_live_campaign`, `bk_live_adgroup`, `bk_live_ad`

---

## 2. Growth Marketing Overview (all-channels executive view)

**Top strip:**
- Total Leads · Qualified Leads · Qualified % · Disqualified Leads · ROI (Organic+Paid)
- Total Ad Spend · CPL · CPQL · Deals Amount · Deal Won Amount

**Time series (daily, selectable date range):**
- Number of leads + Qualified leads + Cost (dual axis)

**Source mix (4 donuts):**
- Source by Number of Leads — Paid / Organic / Direct (67.8 / 15.3 / 16.9%)
- Source by Qualified Leads (73 / 12 / 15%)
- Open Leads Stages (Attempting / Connected / New, 85.9 / 13.6 / 0.5%)
- Closed Won Deal Amount by Source (66.2 / 26.2 / 7.7%)

**Sub-pages:**
- **Organic /Total** — Total Leads · Qualified · Disqualified · Qualified % · Deal Won Amount
- **Organic Overview** — Source table (Direct Traffic / Organic Search / Organic Social / Email Marketing / Google Ads) × (Leads, Qualified, Disq, Q%, Disq%, Won $)
- **Organic Monthly Trend** — 15-month bar chart of Number of Leads
- **Organic Sessions** — monthly GA4 sessions (Jan 2025 → current)
- **First/Last page seen** — URL × (Leads, Qualified Leads, Disqualified Leads) — needs GA4 + HubSpot join
- **Paid /Total** — mirror of Organic /Total
- **Paid /Performance** — Leads · Qualified · Disq · Q% · Disq% / Ad Spend · CPL · CPQL · **ROAS** · Deal Won Amount
- **Paid /Performance** source breakdown table: Source × (Cost, Leads, Qualified, Disq, Q%, Disq%, CPL, CPQL, **ROI**)
  - Rows: Google Ads / Meta Ads / Snapchat Ads / TikTok Ads / Microsoft Ads
- **Paid / Branding Only** — same shape filtered to brand keyword campaigns; adds Impressions, Clicks, CPC, CTR
- **Paid / Monthly Trend** — 15-month bars: Number of Leads / Avg CPL / Qualified % / Paid Sessions

**Pipeline sub-views:**
- Lead Pipeline (leads, qualified, disqualified, Q%, Disq%)
- Lead Bookkeeping Pipeline (same)
- Lead Qoyod Flavours Pipeline (same)
- Deals Sales Pipeline — Number of Deals · Won Deals · Deals Amount · Won Amount · Closing Won Ratio
- Deals Bookkeeping Pipeline (same + horizontal bar: Closed Lost / Quotation Sent / New / Closed Won by count + $)
- Digital Marketing / Bookkeeping Pipeline (same)
- Deals Qoyod Flavours Pipeline (same)
- Other Pipelines / Paid Source (same)
- Ad Name × (Number of Deals, Deals Amount) leaderboard

→ BQ views: `gm_top_kpis`, `gm_timeseries`, `gm_source_mix`, `gm_organic_source`, `gm_organic_monthly`, `gm_paid_source`, `gm_paid_branding`, `gm_paid_monthly`, `gm_pipeline_leads`, `gm_pipeline_deals`, `gm_ad_deals_leaderboard`

---

## 3. Channels Performance (per-channel drill-down)

**Structure:** one tabbed page per channel (Meta, Snapchat, Google, TikTok, Microsoft, Offline, Email, Organic). Each tab has identical layout:

**KPI strip:** Total Leads · Qualified · Disq · CPL · CPQL · CPL BK · CPQL BK
**Donuts:** Campaign name by Qualified Leads · Campaign name by Disqualified Leads · Campaign name by Qualified BK Leads
**Drill-down table:** Campaign × (Cost, Leads, CPL, Qualified, CPQL, Disq, Deals, Deals Amount, BK Qualified, BK Disq, CPQL BK, Campaign Status)
**Ad Group table** (same metrics)
**Ad Name table** (same metrics)
**Status table:** Campaign × (Ad set Effective Status, Campaign Effective Status)
**Disqualification matrix:** Campaign / Ad Name × Disqualification Reason (Ops) × Sub-reason → count of leads
  - Columns include: No lead response · Number failed · Not a Buyer/Personal Use · Browsing/Training · Existing customer · Urdu speaker · Student · No Register · After 8+ sales attempts
**Landing URL table:** campaigns.qoyod.com / app.qoyod.com paths × (Leads, Qualified, Disqualified)

→ BQ views (one set × 8 channels, or parameterized): `ch_kpis`, `ch_campaign`, `ch_adgroup`, `ch_ad`, `ch_status`, `ch_disq_matrix`, `ch_landing`

---

## Source Tables Required in BigQuery (underpinning the views)

| Table | Status | Populated from |
|---|---|---|
| `campaigns_daily` | ✅ built | Google Ads + Meta collectors; need Snap, TikTok, MS |
| `ads_daily` | schema exists, not populated | Google Ads + Meta at ad level (TODO: ad-level collectors) |
| `hubspot_leads_module_daily` | ✅ built + 2,679 rows backfilled | Lead object 0-136 with `lead_qoyod_source` |
| `hubspot_contacts_daily` | ✅ built | Contact object |
| `hubspot_deals_daily` | **TODO — building next** | Deals object with `dealstage.probability` for won/lost/open |
| `ga4_sessions_daily` | TODO (GA4 access pending) | GA4 export — sessions, source/medium, landing page, engaged sessions |
| `ga4_page_leads` | TODO | GA4 + HubSpot join via utm/email on first_page_seen |

## Channel Labels (consistent across all views)

Internal `channel` enum, matched against `lead_qoyod_source` / `deal_qoyod_source`:
- `Meta Ads` · `Google Ads` · `Snapchat Ads` · `Tiktok Ads` · `Microsoft Ads` · `Twitter Ads`
- `Email Marketing` · `Organic Search` · `Organic Social` · `Direct Traffic` · `Offline` · `Referral` · `Paid Influencer`

## Campaign / Ad-Group / Ad keyword tagging (regex on name)

Ran against campaign/ad names to power the "Branding only", seasonal, and ad-format filters:

| Tag | Regex (case-insensitive) |
|---|---|
| **Seasonal — Bookkeeping** | `bookkeeping\|BK` |
| **Seasonal — Founding Day** | `founding[\s_]?day\|FD2026\|FD` |
| **Seasonal — End of Year** | `end[\s_]?of[\s_]?year\|EOY` |
| **Seasonal — Ramadan** | `ramadan` |
| **Seasonal — ZATCA/VAT** | `zatca\|vat\|e-?invoice` |
| **Seasonal — POS** | `pos\b` |
| **Branding** | `brand\|brandi(ng|_)` |
| **Ad format — Video** | `video\|vid_\|_vid` |
| **Ad format — UGC** | `ugc` |
| **Ad format — Image/Static** | `image\|static` |
| **Ad format — Carousel** | `carousel` |
| **Ad format — Story/Reel** | `story\|reel` |

## ROAS / ROI formula (consistent with Looker)

```sql
roas = SUM(deal_won_amount) / NULLIF(SUM(cost), 0)
cpl  = SUM(cost) / NULLIF(SUM(leads), 0)
cpql = SUM(cost) / NULLIF(SUM(qualified_leads), 0)
qualified_pct = SUM(qualified_leads) / NULLIF(SUM(qualified_leads + disqualified_leads), 0)
```

`deal_won_amount` joins on `(date, channel)` from `hubspot_deals_daily` filtered to `dealstage.probability = 1.0`.
`leads / qualified_leads / disqualified_leads` come from `hubspot_leads_module_daily`.
`cost / impressions / clicks` from `campaigns_daily`.

---

## Build order (next sessions)

1. ✅ Looker reports catalogued (this doc)
2. **HubSpot Deals collector** → `hubspot_deals_daily` (in progress)
3. **Unified `channel_roas_daily` view** — joins spend + leads + deals per (date, channel)
4. Ad-level collectors (Google Ads + Meta) → `ads_daily`
5. Snap collector (blocked on OAuth)
6. MS Ads collector (blocked on admin consent)
7. TikTok collector (blocked on app approval)
8. GA4 collector (blocked on property access)
9. Seasonal / branding / format tag views
10. Per-channel drill-down views (8 channels × 7 view types)
11. Point fresh Looker Studio reports at the BQ views (or generate our own web dashboard)
