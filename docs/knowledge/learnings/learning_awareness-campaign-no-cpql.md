---
name: learning_awareness-campaign-no-cpql
description: "ImpressionShare_ / WebsiteTraffic campaigns are awareness-type — never apply CPQL, never add tCPA; KPI is IS% ≥ 25% + daily budget control"
metadata: 
  node_type: memory
  type: learning
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

Context: `ImpressionShare_Search_AR_Invoice` was flagged as a "drain" based on CPQL, with recommendations to pause keywords and change bid strategy to tCPA $120. Both recommendations were wrong. `config.py::AWARENESS_PATTERNS = ["impressionshare", "impression_share", "websitetraffic", "reach"]` explicitly marks these as awareness campaigns where zero leads is acceptable.

Outcome: Incorrect pause/bid recommendations would have harmed a healthy awareness campaign.

Pattern: Before selecting any KPI metric or recommending bid strategy, classify campaign type from its name using `AWARENESS_PATTERNS`. ImpressionShare_ / WebsiteTraffic → KPI is IS% (target ≥ 25%) + daily budget control. Zero leads is fine. NEVER add tCPA. NEVER apply CPQL zones. The correct lever: IS% below 25% → increase daily budget; IS% fine but spend high → reduce budget cap. Google Ads acceptable CPQL is $130, not $100.

Applies to: growth-analyst classifying campaign type before any metric recommendation.
