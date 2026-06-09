---
name: finding_period-window-last-complete-spend-day
description: Period windows must end at the last complete spend day — yesterday may have $0 spend (nightly collector not landed yet) causing false CPQL regression
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: Running the 7d-vs-prior period compare on 2026-06-09 with a yesterday-anchored window showed Meta CPQL spiking and a −72% MoM spend forecast. Cause: `campaigns_daily` had NO spend rows for the most recent date yet — the nightly collector hadn't landed. The window's last day was spend=$0 but leads were present, deflating spend/CPQL and exaggerating the MoM gap.

Source: memory/08_pitfalls.md "Period windows must end at the last COMPLETE spend day".

Impact: False CPQL regression signal; misleading MoM spend forecast.

Fix / How to handle: Before fixing window bounds, query `SELECT date, SUM(spend) FROM campaigns_daily GROUP BY date ORDER BY date` for the tail and set window END to the last date with non-trivial spend — NOT `CURRENT_DATE()-1`. Never trust a window whose final day shows $0 spend with non-zero leads.
