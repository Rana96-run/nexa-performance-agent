# Qoyod Performance Dashboard — Looker Studio Setup
*Windsor-style, powered by BigQuery. Free forever.*

---

## Step 1 — Connect BigQuery Data Sources

Go to **lookerstudio.google.com** → **Create** → **Report** → **Add data**

Add each of these (BigQuery → project `angular-axle-492812-q4` → dataset `qoyod_marketing`):

| # | Table/View | Used For |
|---|-----------|---------|
| 1 | `v_kpi_scorecard` | Header KPI cards |
| 2 | `v_channel_scorecard` | Channel comparison + WoW |
| 3 | `v_daily_trend` | All time-series charts |
| 4 | `v_campaign_leaderboard` | Campaign table + bar charts |
| 5 | `v_budget_pacing` | Pacing bullets |
| 6 | `channel_roas_monthly` | Monthly ROAS + funnel |
| 7 | `campaign_performance_daily` | Channel deep dive |
| 8 | `disqualification_matrix` | Disqualification breakdown |
| 9 | `pipeline_funnel` | Funnel chart |

---

## Step 2 — Report Theme (Qoyod Brand)

**Theme & Layout** → **Customize**:

| Setting | Value |
|---------|-------|
| Background | `#FFFFFF` |
| Canvas color | `#F5F7FA` |
| Font family | **Inter** (or Google Sans) |
| Header text color | `#1A1A2E` |
| Body text | `#2D2D2D` |
| Accent / primary | `#6C63FF` |

**Channel colors** (apply consistently across all charts):
| Channel | Hex |
|---------|-----|
| Google Ads | `#4285F4` |
| Meta | `#1877F2` |
| Snapchat | `#FFFC00` with border |
| TikTok | `#010101` |
| Microsoft | `#00A4EF` |

**KPI Zone colors**:
| Zone | Color |
|------|-------|
| Scale 🚀 | `#00C48C` |
| On Target ✅ | `#52C41A` |
| Warning ⚠️ | `#FFB800` |
| Pause Zone 🔴 | `#FF4D4F` |

---

## Page 1 — Executive Overview

### Row 1: KPI Scorecards (8 cards across the top)
**Add a Chart → Scorecard** × 8, source: `v_kpi_scorecard`

| Card | Metric | Format | Color Rule |
|------|--------|--------|------------|
| Total Spend | `total_spend` | `SAR #,###` | None |
| Total Leads | `total_leads` | `#,###` | None |
| Total SQLs | `total_sqls` | `#,###` | None |
| Blended CPL | `blended_cpl` | `SAR #.##` | <20 green / 20-30 amber / >30 red |
| Blended CPQL | `blended_cpql` | `SAR #.##` | <40 green / 40-80 amber / >80 red |
| Qual Rate | `qual_rate_pct` | `#.#%` | >30% green |
| Blended ROAS | `blended_roas` | `#.##x` | >1 green |
| Revenue Won | `revenue_won` | `SAR #,###` | None |

**Scorecard style**: No border, light `#F5F7FA` background, metric value 32px bold, label 11px `#8C8C8C`.

---

### Row 2: CPL & CPQL Trend — Time Series
**Source**: `v_daily_trend`
- Chart type: **Smooth line chart**
- Dimension: `date`
- Metrics: `cpl_7d_avg` (purple `#6C63FF`) + `cpql_7d_avg` (red `#FF4D4F`)
- Add **reference lines**: 30 (CPL pause, red dashed) and 80 (CPQL pause, red dashed)
- Enable **date range control** (top-right of chart)
- Enable **channel filter** (dimension: `channel`)

---

### Row 3: Left — Channel Bar Chart | Right — Channel KPI Table

**Left: Grouped Bar Chart**
- Source: `v_channel_scorecard`
- Dimension: `channel`
- Metrics: `spend_7d`, `leads_7d`, `sqls_7d`
- Colors: per channel map above
- Enable data labels

**Right: Pivot Table**
- Source: `v_channel_scorecard`
- Rows: `channel`
- Columns: `spend_7d`, `leads_7d`, `sqls_7d`, `disqualified_7d`, `cpl_7d`, `cpql_7d`, `qual_rate_pct`, `roas_7d`, `cpl_wow_delta`, `cpl_status`
- Color `cpl_status` column by text: Scale=green, On Target=green, Warning=amber, Pause Zone=red
- Color `cpl_wow_delta` column: negative values = green (CPL improved), positive = red

### Row 4: Two-Pipeline Breakdown Table
- Source: `v_channel_scorecard`
- Dimension: `channel`
- Show columns for **Lead Pipeline**: `leads_accounting_7d`, `sqls_accounting_7d`, `disqual_accounting_7d`, `cpl_accounting_7d`, `cpql_accounting_7d`
- Show columns for **Bookkeeping Pipeline**: `leads_bookkeeping_7d`, `sqls_bookkeeping_7d`, `disqual_bookkeeping_7d`, `cpl_bookkeeping_7d`, `cpql_bookkeeping_7d`
- Add column groups header: "Lead Pipeline (Accounting)" | "Bookkeeping Pipeline"

---

## Page 2 — CPL & CPQL Deep Dive

### Chart 1: Daily CPL by Channel (90 days)
- Source: `v_daily_trend`
- Dimension: `date`, Breakdown: `channel`
- Metric: `cpl`
- Reference lines: 28 (amber), 30 (red)
- Colors: channel map

### Chart 2: Daily CPQL by Channel
- Same as above, metric: `cpql`
- Reference lines: 65 (amber), 80 (red)

### Chart 3: CPL vs Qualification Rate (Bubble Chart)
- Source: `v_channel_scorecard`
- X: `cpl_7d` | Y: `qual_rate_pct` | Size: `spend_7d` | Color: `channel`
- Tooltip: channel, spend, leads
- **Insight**: channels in top-left quadrant (low CPL + high qual rate) = scale

---

## Page 3 — Campaign Leaderboard

### Table: Top Campaigns Last 14 Days
- Source: `v_campaign_leaderboard`
- Columns: `campaign_name`, `channel`, `format_tag`, `seasonal_tag`, `spend`, `leads`, `cpl`, `avg_ctr`, `status`
- Sort default: `spend DESC`
- Row background color rule on `status` column
- Add **search box** (filter control on `campaign_name`)
- Add **channel** dropdown filter

### Bar Chart: CPL by Campaign (Top 15)
- Source: `v_campaign_leaderboard`
- Horizontal bars, sorted by `cpl` ascending
- Color bars by `status`
- Reference line at 30 (pause threshold)
- Limit: 15 rows

---

## Page 4 — Budget & Pacing

### Bullet Charts: Pacing by Channel
- Source: `v_budget_pacing`
- One bullet per channel showing `actual_spend` vs `projected_month_spend`
- Color `pacing_status` label

### Stacked Area: Daily Spend This Month
- Source: `channel_roas_daily`
- Dimension: `date`, Breakdown: `channel`
- Metric: `spend`
- Chart type: **Stacked area**
- Filter: current month
- Colors: channel map

---

## Page 5 — Pipeline & Funnel

### Funnel Chart
- Source: `pipeline_funnel`
- Stages (in order): `leads_total` → `leads_qualified` → `leads_open`
- Breakdown: `qoyod_source`
- Add filters: `month`, `pipeline_label`
- **Filter to show Lead Pipeline and Bookkeeping Pipeline side by side using `pipeline_label`**

### Disqualification Breakdown Table
- Source: `disqualification_matrix`
- Columns: `qoyod_source`, `pipeline`, `disqual_reason_label`, `disqualified_count`
- Sort: `disqualified_count DESC`
- Bar sparklines on count column
- **Reason labels** (mapped from HubSpot raw values):
  - No Lead Response / After 8+ Attempts / Number Failed / Not a Buyer
  - No Registered Business / Browsing or Testing / Training / Existing Customer
  - Urdu Speaker / Student / Lead Denies / Out of Region

### Monthly ROAS Bar Chart
- Source: `channel_roas_monthly`
- X: `month` | Breakdown: `channel` | Metric: `roas`
- Reference line at 1.0 (break-even)
- Colors: channel map

---

## Page 6 — Channel Deep Dive

### Tab Selector Filter
- Add a **filter control** on `channel` dimension
- Style: tab/chip selector (horizontal pills)

### Scorecard Row (filtered by tab)
- Source: `v_channel_scorecard`
- 6 cards: spend, leads, SQLs, CPL, CPQL, ROAS
- All linked to channel filter

### CPL Trend (filtered)
- Source: `v_daily_trend`
- Linked to channel filter tab

### Campaign Table (filtered)
- Source: `campaign_performance_daily`
- Linked to channel filter tab

---

## Step 3 — Global Controls (add to every page)

1. **Date range control** (top-right, default: Last 30 days)
2. **Channel dropdown** filter
3. **Page navigation** (left sidebar or top tabs)

---

## Step 4 — Share & Embed

- **Share** → "Anyone with the link can view"
- **Embed** in Notion or internal wiki: File → Embed report
- **Schedule email delivery**: Share → Schedule email delivery → daily 9am Riyadh

---

## Run the setup script first
```bash
cd "D:/Nexa Performance Agent"
.venv/Scripts/python.exe looker/setup.py
```
This creates all 5 enhanced views in BigQuery before you connect Looker Studio.
