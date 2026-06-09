---
name: finding_paid-channel-daily-no-date-spine
description: paid_channel_daily had no date spine — channels with zero activity on a day disappeared entirely from reports
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: The `paid_channel_daily` view was built as a FULL OUTER JOIN of spend, leads, and deals. If all three were zero for a channel on a given day, that row simply did not exist. A paused LinkedIn campaign would vanish from the channel overview for the entire pause period.

Source: Session a7de53a6 — discovered during BQ schema audit.

Impact: Dashboard charts showed missing channel rows for quiet periods; period-over-period comparisons silently dropped channels that paused.

Fix / How to handle: Add a `channel_dates` CTE as a spine: `SELECT DISTINCT date, channel FROM campaigns_daily UNION DISTINCT ... leads ... deals`. Then LEFT JOIN all metrics from the spine, so every channel that ever had a campaign shows up with 0 values on quiet days.
