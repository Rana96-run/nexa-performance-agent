---
name: BigQuery role in the architecture
description: BQ is NOT a channel connector — it's the custom metrics/dimensions layer built from multiple data sources
type: project
originSessionId: 98abfa4b-165c-4f94-9eed-fbd113d7e8d2
---
BigQuery is the **reporting and metrics layer**, not a channel connector.

**Flow:**
1. Collectors pull raw data from each channel API (Google Ads, Meta, Snapchat, TikTok, LinkedIn, HubSpot) and write it to BQ tables
2. BQ combines these sources to build custom metrics and dimensions that don't exist in any single platform (e.g. CPQL = cost from channel + qualified leads from HubSpot)
3. The reporter queries BQ for these derived metrics to build the dashboard and feed the analysers

**Why:** No single platform knows the full picture. CPQL, SQL rate, cross-channel attribution — these only exist after joining channel spend with HubSpot lead quality data in BQ.

**How to apply:** Never treat BQ as "the ad platform connection." Adspirer MCP / direct channel APIs are for campaign mutations (pause, scale, create). BQ is for reading the blended performance truth.
