---
name: finding_microsoft-ads-rest-api-3-bugs
description: "Microsoft Ads REST reporting API had 3 bugs: wrong URL path, missing Type discriminator field, per-report status column names differ"
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found:
1. Wrong base URL: `/api/advertiser/reporting/v13` — correct path is `/Reporting/v13`
2. Wrong submit path: `/SubmitGenerateReport` — correct is `/GenerateReport/Submit`
3. Missing `Type` field in ReportRequest body — REST API uses JSON polymorphism; unlike SOAP which infers type from XML, REST/JSON requires explicit `"Type": "CampaignPerformanceReportRequest"` etc.
4. Each report type uses a different status column name: `CampaignStatus`, `Status` (AdGroup), `KeywordStatus`, `AdStatus` — no consistent pattern across report types.

Source: Session d8436485 — Microsoft Ads collector debugging after successful auth.

Impact: Collector returned 404 / "Invalid JSON at position X" until all 3 were fixed.

Fix / How to handle: Status column names are documented in `memory/08_pitfalls.md`. Always probe with a small date window first when adding a new report type to catch column name issues early.
