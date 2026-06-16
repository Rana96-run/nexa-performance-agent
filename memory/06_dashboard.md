# Dashboard

## Current tools (as of 2026-06-16)

**Hex** is the canonical dashboard. Two notebooks:
- Performance: `Qoyod-marketing-performance-0339sAIgaMNYNW4ffgEBZK`
- Agent Activity: `Nexa-Agent-Activity-033ArC9Xytz3SK6tPXwk9D`

Both read directly from BigQuery (`angular-axle-492812-q4.qoyod_marketing`). No hosting required — Hex manages it.

**Databox** is the external team-facing dashboard. Two datasets:
- Daily Spend (`199c5297`): channel-day grain
- All Grains (`6158be78`): 4-grain unified (campaign/adset/ad/keyword)
Data source ID: `4983171`. Account ID: `756469`.
Direct BQ integration — auto-refreshes when BQ updates.

## Deprecated (deleted 2026-06-16)
- Streamlit on Replit — replaced by Hex
- `reports/app.py` Flask dashboard — deleted
- `dashboard/` folder — deleted
