# How to read each chart

---

### 1. ROAS Trend (line chart, date-range driven)
- **Flat or rising line** = paid is performing consistently or improving
- **Falling line** = efficiency dropping — usually because spend ramped faster than the funnel can absorb
- **Two lines:** "All Paid ROAS" includes every pipeline; "New Biz ROAS" includes only Sales Pipeline + Bookkeeping + Qflavours. Divergence between them = renewals or other pipelines are distorting the blended number
- **Reference line at 1.0** = break-even. Any week below it = we spent more than we earned

---

### 2. Channel Efficiency Quadrant (scatter plot)

**Important: this chart shows SHARE OF TOTAL, not absolute ROAS.**
That's why a channel with the highest per-dollar ROAS may appear in the lower-left as a small dot. Read both axes together:

| Position | What it means | Decision |
|---|---|---|
| 🟢 **Upper-right** (high spend share, high revenue share) | The workhorse — generates most of your revenue at acceptable efficiency | **Maintain budget**, optimize incrementally. Don't cut. |
| 🔵 **Lower-left + high ROAS** (tiny spend share, tiny revenue share, BUT high ROAS) | Proven channel at sub-scale — a high-efficiency experiment | **Scale up budget**. Highest marginal upside. ROAS will compress at scale but should stay healthy. |
| ❌ **Lower-right** (high spend share, low revenue share) | Burning budget — taking up share of spend without proportional return | **Optimize creative/targeting OR pause** |
| ⚪ **Lower-left + low ROAS** (small everything, weak ROAS) | Low-impact, neutral | Keep as exploratory budget or pause |

**Current state read** (Apr 10 → May 9):
- 🟢 **Google Ads** (62% spend, 91% revenue, ROAS 4.22) — workhorse. Maintain.
- 🔵 **Microsoft Ads** (1.4% spend, 2.8% revenue, ROAS 5.87) — **highest ROAS, smallest scale → scaling opportunity**
- ❌ **Meta** (19% spend, 3% revenue, ROAS 0.44), **Snapchat** (12% spend, 1.3% revenue, ROAS 0.32) — burning. Need creative/targeting fix.
- ⚪ **TikTok** — close to break-even at small scale. Keep watching.

---

### 3. Spend vs Revenue Trend (dual-axis line, always last 90 days)
- **This chart is hardcoded to last 90 days** — it does not move with the date picker. It exists to show the macro trend regardless of the selected window.
- **Healthy state**: revenue line tracks (or lags slightly behind) the spend line
- **Revenue flat while spend climbs** = funnel saturation. Scale-back signal.
- **Revenue rising faster than spend** = efficiency gain. This is when to push for more budget.
- Use the **7-day rolling average lines** (smoother) to read the trend — the raw daily lines show the true data but are noisy.
- **Important on the new-biz line**: revenue is attributed to deal **createdate**, not closedate. So today's new biz revenue counts only deals that were created today and have already won — recent days will look smaller until those leads mature into closed-won deals. Old periods are stable.

---

### 4. Top/Bottom Campaigns (table)
- **TOP 5** = highest ROAS campaigns in the selected period → scale candidates for next budget review
- **BOTTOM 5** = lowest ROAS campaigns → pause/optimize candidates
- Minimum $200 spend filter is applied in the query — tiny-sample campaigns with 1–2 leads don't distort the list
- A campaign in BOTTOM 5 with 0 revenue and high spend = no attribution to deals yet — check if UTM tracking is set up correctly before pausing
- **`new_biz_roas` column** lets you re-rank by new-business-only revenue. A campaign can be top by blended ROAS (because of renewals attributed back to its UTM) but bottom by new biz ROAS — that's a signal it's not driving fresh customer acquisition.

---

### 5. Lead Funnel by Channel (stacked bar)
- Each bar shows where leads fall off across the funnel for that channel
- **Short "qualified" segment vs total leads** → audience targeting issue — wrong people are clicking the ads
- **Long "qualified" segment but few "won" deals** → sales/closing issue, not a marketing problem
- **High "disqualified" count** → drill into Chart 7 (Disqualification Reasons) to see which channel + campaign + reason is driving it

---

### 6. CAC by Channel (horizontal bar)
- **CAC = total spend ÷ won deals** for the selected period. Different from CPL — this is cost per *paying customer*, not cost per lead.
- **Lower CAC = better.** Channels are sorted lowest to highest.
- The **% change column** (vs previous same-length period) tells you if efficiency is improving or worsening:
  - 🟢 Negative % = CAC going down = getting more efficient
  - 🔴 Positive % = CAC going up = getting more expensive per customer
- **Channels with no won deals are excluded** — a channel that generated leads but zero closed deals does not appear here. That itself is a signal (check Chart 5 for its funnel drop-off).
- **`new_biz_cac` column** = CAC counted only against new-business deals (Sales Pipeline + Bookkeeping + Qflavours). Use this to judge channel quality on acquisition alone, isolated from renewal credit.
- Rule of thumb: **CAC should be ≤ 1/3 of customer LTV**. If you know average contract value, use that to sanity-check each bar.

---

### 7. Disqualification Reasons (pivot drilldown table)
- Expand the rows: **Channel → Reason → Sub-reason → Campaign**
- **`disqualified_count`** = raw number of disqualified leads for that combination
- **`% of All Disqualified`** = that row's count ÷ total disqualified across *all* paid channels × 100. A row at 15% means 1 in 7 of your disqualified paid leads traces to that exact channel + campaign + reason.
- **How to use it:**
  - High % on **"Wrong audience / not our target"** → targeting fix needed (wrong segment, wrong geography, wrong ad creative)
  - High % on **"No lead response after 8+ sales attempts"** → this is a *sales* problem, not marketing. The lead was qualified but sales couldn't reach them. Marketing should not be blamed or paused for this.
  - High % on **"Budget / price objection"** → messaging or pricing-page issue
  - Same reason appearing across multiple channels → systemic problem (offer, landing page, or product positioning), not a single-channel fix

---

### Vocabulary cheat sheet — what each column means

Every dashboard cell exposes both **"all pipelines"** and **"new business only"** versions of the deal metrics. New Business = Sales Pipeline + Bookkeeping + Qflavours (renewals excluded).

| Concept | All-pipelines column | New-biz-only column |
|---|---|---|
| Count of won deals | `deals_won` | `new_biz_deals_won` |
| Count of lost deals | `deals_lost` | `new_biz_deals_lost` |
| Count of still-open deals | `deals_open` | `new_biz_deals_open` |
| Won revenue | `revenue_won` / `closed_won_amount` | `new_biz_revenue_won` |
| Lost deal value | `amount_lost` / `closed_lost_amount` | `new_biz_amount_lost` |
| Open pipeline value | `amount_open` / `open_deal_amount` | `new_biz_amount_open` |
| Total deal value | `amount_total` / `total_deal_amount` | `new_biz_amount_total` |
| Return on ad spend | `roas` / `blended_roas` | `new_biz_roas` |
| Cost per won customer | `cac` | `new_biz_cac` |

All deal numbers (counts and amounts) are attributed to **deal createdate**, not closedate. A deal created today that wins next month belongs in today's numbers — that aligns deal attribution with the spend period that generated the lead. See the Spend vs Revenue Trend note above for the implication on recent days.
