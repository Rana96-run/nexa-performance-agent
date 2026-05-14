# Hex Performance Dashboard — Navigation Guide

Dashboard URL:
https://app.hex.tech/019de9f2-2933-7000-80ba-80156bf7570d/app/Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK/latest

Open the link → switch to **Edit mode** to change SQL or layout.
Switch to **App mode** (top-right "Run") to see the final published view.

---

## Currency rule (applies everywhere)

- **Spend** → USD (collectors convert at write time). Use as-is.
- **Deal amounts / revenue** → USD (collector calls `to_usd()` at write time). Use as-is.
- **Never divide by 3.75** anywhere — that causes double-conversion.
- **ROAS** is unitless (USD revenue ÷ USD spend). Display with 2 decimal places.

---

## Dashboard structure — 4 tabs

| Tab | Name | Purpose |
|-----|------|---------|
| 1 | **Overview** | All-channel KPIs + scorecard |
| 2 | **By Channel** | Per-channel drill-down (campaigns → ad groups → ads → keywords) |
| 3 | **Trends & Insights** | 7 trend/efficiency charts for management |
| 4 | **By Pipeline** | Deal pipeline breakdown (Sales / Bookkeeping / Qflavours / Renewal) |

---

## TAB 1 — Overview

### How to reach it
App Builder → click **Tab 1** in the tab bar at the top.

### Controls
- **Date range picker** → sets `start_date` / `end_date` for all cells on this tab.

### Cells in order

| # | Title | SQL file | Notes |
|---|-------|----------|-------|
| 1 | KPI Scorecards | `0_scorecard.sql` | 3 rows × 4 tiles. Row 0 = current period, Row 1 = previous. |
| 2 | All Channels Overview | `1_channel_overview.sql` | One row per channel. Shows spend, leads, CPL, CPQL, qual rate, revenue, ROAS + vs-prev change %. |

#### Scorecard tile layout

| Row | Tile 1 | Tile 2 | Tile 3 | Tile 4 |
|-----|--------|--------|--------|--------|
| 1 | Total Spend | Total Leads | CPL | CPQL |
| 2 | Qual Rate | Disq Rate | Blended ROAS | Revenue Won |
| 3 | Disqualified Leads | Total Deal Amount | — | — |

---

## TAB 2 — By Channel

### How to reach it
App Builder → click **Tab 2** in the tab bar.

### Controls
- **Date range picker** → `start_date` / `end_date`
- **Channel dropdown** → `channel` — selects which channel's cells are active.
  Values: `google_ads` · `meta` · `snapchat` · `tiktok` · `microsoft_ads` · `linkedin`

### Cells in order (repeat for each channel)

Each channel has its own set of SQL cells. The channel dropdown controls which set is visible.

| # | Title | SQL file | Row click output |
|---|-------|----------|-----------------|
| 1 | Channel KPI Tiles | `by_channel/<channel>/0_kpi_scorecard.sql` | — |
| 2 | Campaigns | `by_channel/<channel>/1_campaigns.sql` | → `selected_campaign` |
| 3 | Ad Groups | `by_channel/<channel>/2_adsets.sql` | → `selected_adset` |
| 4 | Ads | `by_channel/<channel>/3_ads.sql` | — (leaf) |
| 5 | Keywords | `by_channel/google_ads/4_keywords.sql` or `microsoft_ads/4_keywords.sql` | — (leaf, search channels only) |

#### Drill-down flow

```
Date picker + Channel dropdown
        │
        ▼
[Channel KPI Tiles]  ← always visible for selected channel
        │
        ▼
[Campaigns table]  ── click row ──► selected_campaign (output variable)
        │
        ▼
[Ad Groups table]  ── filtered by selected_campaign ── click row ──► selected_adset
        │
        ▼
[Ads table]  ── filtered by selected_campaign + selected_adset (leaf)
        │
        ▼
[Keywords table]  ── filtered by selected_campaign (Google + Microsoft only, leaf)
```

#### Filtering logic per cell

| Cell | Filters applied |
|------|----------------|
| Campaigns | `channel` + `date range` |
| Ad Groups | `channel` + `date range` + `selected_campaign` (hides if no campaign clicked) |
| Ads | `channel` + `date range` + `selected_campaign` + `selected_adset` (hides if no adset clicked) |
| Keywords | `channel` + `date range` + `selected_campaign` (only shown for google_ads / microsoft_ads) |

#### Channel → SQL folder mapping

| Channel dropdown value | SQL folder |
|------------------------|-----------|
| `google_ads` | `by_channel/google_ads/` |
| `meta` | `by_channel/meta/` |
| `snapchat` | `by_channel/snapchat/` |
| `tiktok` | `by_channel/tiktok/` |
| `microsoft_ads` | `by_channel/microsoft_ads/` |
| `linkedin` | `by_channel/linkedin/` |

---

## TAB 3 — Trends & Insights

### How to reach it
App Builder → click **Tab 3** in the tab bar.

### Controls
- **Date range picker** → `start_date` / `end_date` — affects Charts 1, 2, 4, 5, 6, 7.
- Chart 3 (Spend vs Revenue) is always last 90 days — hardcoded, not affected by date picker.

### Charts in order

| Chart # | Title | SQL file | Chart type | Key columns |
|---------|-------|----------|-----------|-------------|
| 1 | ROAS Trend | `by_trends/1_roas_trend.sql` | Line chart | `week_start` · `roas` · `new_biz_roas` |
| 2 | Channel Efficiency Quadrant | `by_trends/2_channel_quadrant.sql` | Scatter plot | `spend_share_pct` (X) · `revenue_share_pct` (Y) · `channel` (label) |
| 3 | Spend vs Revenue (last 90 days) | `by_trends/3_spend_vs_revenue.sql` | Dual-axis line | `date` · `spend` / `spend_7d_avg` · `revenue_won` / `revenue_7d_avg` |
| 4 | Top 5 Winners + Bottom 5 Burners | `by_trends/4_top_bottom_campaigns.sql` | Table | `rank` · `campaign_name` · `channel` · `spend` · `roas` |
| 5 | Lead → Qualified → Won Funnel | `by_trends/5_lead_funnel.sql` | Horizontal stacked bar | `channel` · `leads` · `qualified` · `disqualified` · `deals_won` |
| 6 | CAC by Channel | `by_trends/6_cac_by_channel.sql` | Horizontal bar | `channel` · `cac` · `cac_prev` · `cac_change_pct` |
| 7 | Disqualification Reasons | `by_trends/7_disqualification_reasons.sql` | Pivot / drilldown table | `channel` · `reason` · `sub_reason` · `campaign` · `disqualified_count` · `share_of_total_pct` |

### Chart-by-chart configuration

#### Chart 1 — ROAS Trend
- **Type:** Line chart
- **X-axis:** `week_start` — set granularity to **Day** (not Month/Auto)
- **Y-axis:** `roas` (left, label "All Paid ROAS") + `new_biz_roas` (right, label "New Biz ROAS")
- **Reference line:** Y = 1.0 (break-even). Add via Chart settings → Reference lines.
- **Date range:** Controlled by the tab's date picker.

#### Chart 2 — Channel Efficiency Quadrant
- **Type:** Scatter plot
- **X-axis:** `spend_share_pct` (label: "% of Total Spend")
- **Y-axis:** `revenue_share_pct` (label: "% of Revenue")
- **Point label:** `channel`
- **Point size:** `roas` (bubble size = ROAS magnitude)
- **Reference lines:** X = 16.7, Y = 16.7 (equal-share lines for 6 channels)
- **Interpretation:** Top-left = high revenue, low spend (efficient). Bottom-right = high spend, low revenue (inefficient).

#### Chart 3 — Spend vs Revenue (last 90 days)
- **Type:** Dual-axis line chart
- **X-axis:** `date` — set granularity to **Day**
- **Left Y-axis:** `spend_7d_avg` (7-day rolling average spend — smoother)
- **Right Y-axis:** `revenue_7d_avg` (7-day rolling average revenue)
- **Note:** This chart ignores the date picker — it always shows the last 90 days (hardcoded in SQL).
- **Optional:** Add `spend` and `revenue_won` as secondary series (raw daily) with low opacity for context.

#### Chart 4 — Top 5 Winners + Bottom 5 Burners
- **Type:** Table
- **Group by:** `rank` column (values: `TOP` or `BOTTOM`)
- **Sort:** `roas` DESC within each group
- **Conditional formatting on `roas`:**
  - ≥ 3.0 → green
  - 1.0–2.99 → yellow
  - < 1.0 → red
- **Filter:** Only campaigns with spend ≥ $200 (applied in SQL — no Hex filter needed).
- **Date range:** Controlled by the tab's date picker.

#### Chart 5 — Lead → Qualified → Won Funnel
- **Type:** Horizontal stacked bar
- **Y-axis (bars):** `channel`
- **X-axis (stacked):** `qualified` + `disqualified` + `deals_won`
- **Add data labels:** `qual_rate_pct` and `lead_to_won_pct` as separate columns or tooltips
- **Sort:** By `leads` DESC (highest-volume channel on top)
- **Date range:** Controlled by the tab's date picker.

#### Chart 6 — CAC by Channel
- **Type:** Horizontal bar chart
- **Y-axis (bars):** `channel`
- **X-axis:** `cac` (current period)
- **Secondary bar or tooltip:** `cac_prev` (previous period)
- **Data label / extra column:** `cac_change_pct` with conditional formatting:
  - Negative (CAC going down) → green (improving)
  - Positive (CAC going up) → red (worsening)
- **Sort:** `cac` ASC (lowest CAC = best efficiency at top)
- **Note:** Only channels with `deals_won > 0` appear (SQL filters out channels with no wins).
- **Date range:** Controlled by the tab's date picker.

#### Chart 7 — Disqualification Reasons
- **Type:** Pivot table (grouped drilldown table)
- **Hierarchy:** `channel` → `reason` → `sub_reason` → `campaign`
- **Columns to show:** `disqualified_count` · `share_of_total_pct`
- **Rename `share_of_total_pct`** → label it **"% of All Disqualified"** in Hex column settings
- **Format `share_of_total_pct`:** Number → 1 decimal → add `%` suffix
- **Sort:** `disqualified_count` DESC (biggest problem at top)
- **Conditional formatting on `disqualified_count`:** Higher = darker red
- **Date range:** Controlled by the tab's date picker.
- **Column meaning:**
  - `disqualified_count` = raw count of disqualified leads for this row's combination
  - `share_of_total_pct` = this row's count ÷ ALL paid disqualifications × 100 (tells you "1 in X" impact)

---

## TAB 4 — By Pipeline

### How to reach it
App Builder → click **Tab 4** in the tab bar.

### Controls
- **Date range picker** → `start_date` / `end_date`

### Cells in order

| # | Title | SQL file | Notes |
|---|-------|----------|-------|
| 1 | ROAS Scorecards | `by_pipeline/_roas_scorecards.sql` | 2 tiles: New Biz ROAS vs All Paid ROAS |
| 2 | All Pipelines Overview | `by_pipeline/_pipelines_overview.sql` | One row per pipeline — spend, leads, revenue, ROAS |
| 3 | Sales Pipeline Detail | `by_pipeline/sales_pipeline.sql` + `sales_pipeline_kpi.sql` | |
| 4 | Bookkeeping Pipeline Detail | `by_pipeline/bookkeeping.sql` + `bookkeeping_kpi.sql` | |
| 5 | Qflavours Pipeline Detail | `by_pipeline/qflavours.sql` + `qflavours_kpi.sql` | |
| 6 | Renewal Pipeline Detail | `by_pipeline/renewal.sql` + `renewal_kpi.sql` | |

---

## Quick-reference: which SQL file for each chart

| Chart / Table | SQL file path |
|--------------|--------------|
| Main scorecard (all channels) | `0_scorecard.sql` |
| All channels overview table | `1_channel_overview.sql` |
| Google Ads KPI tiles | `by_channel/google_ads/0_kpi_scorecard.sql` |
| Google Ads campaigns | `by_channel/google_ads/1_campaigns.sql` |
| Google Ads ad groups | `by_channel/google_ads/2_adsets.sql` |
| Google Ads ads | `by_channel/google_ads/3_ads.sql` |
| Google Ads keywords | `by_channel/google_ads/4_keywords.sql` |
| Meta KPI tiles | `by_channel/meta/0_kpi_scorecard.sql` |
| Meta campaigns | `by_channel/meta/1_campaigns.sql` |
| Meta ad groups | `by_channel/meta/2_adsets.sql` |
| Meta ads | `by_channel/meta/3_ads.sql` |
| Snapchat KPI tiles | `by_channel/snapchat/0_kpi_scorecard.sql` |
| Snapchat campaigns | `by_channel/snapchat/1_campaigns.sql` |
| TikTok KPI tiles | `by_channel/tiktok/0_kpi_scorecard.sql` |
| TikTok campaigns | `by_channel/tiktok/1_campaigns.sql` |
| Microsoft Ads KPI tiles | `by_channel/microsoft_ads/0_kpi_scorecard.sql` |
| Microsoft Ads keywords | `by_channel/microsoft_ads/4_keywords.sql` |
| LinkedIn KPI tiles | `by_channel/linkedin/0_kpi_scorecard.sql` |
| LinkedIn campaigns | `by_channel/linkedin/1_campaigns.sql` |
| ROAS trend (Tab 3, Chart 1) | `by_trends/1_roas_trend.sql` |
| Channel efficiency quadrant (Tab 3, Chart 2) | `by_trends/2_channel_quadrant.sql` |
| Spend vs Revenue 90d (Tab 3, Chart 3) | `by_trends/3_spend_vs_revenue.sql` |
| Top/Bottom campaigns (Tab 3, Chart 4) | `by_trends/4_top_bottom_campaigns.sql` |
| Lead funnel by channel (Tab 3, Chart 5) | `by_trends/5_lead_funnel.sql` |
| CAC by channel (Tab 3, Chart 6) | `by_trends/6_cac_by_channel.sql` |
| Disqualification reasons (Tab 3, Chart 7) | `by_trends/7_disqualification_reasons.sql` |
| Pipeline ROAS scorecards | `by_pipeline/_roas_scorecards.sql` |
| All pipelines overview | `by_pipeline/_pipelines_overview.sql` |

---

## Common Hex actions

| Action | How |
|--------|-----|
| Add a new SQL cell | `+ Cell` → `SQL` → paste query → select BigQuery connection |
| Rename a cell | Click the cell title at the top → type new name |
| Wire row-click output | Table cell → click column header gear ⚙ → "On row click" → set output variable name |
| Add reference line | Chart → `Customize` panel → scroll to `Reference lines` → `+ Add line` |
| Add data labels | Chart → `Customize` → `Data labels` → toggle on |
| Independent Y-axes | Chart → `Customize` → Y-axis → tick "Independent axis scale" |
| Rename a column label | Table → column header gear ⚙ → "Display name" |
| Set number format | Table → column header gear ⚙ → "Format" → Number / Currency / Percent |
| Move cell to a tab | App Builder mode → drag the cell into the desired tab canvas area |
| Publish changes | Top bar → `Publish` button (makes changes visible to all viewers) |
