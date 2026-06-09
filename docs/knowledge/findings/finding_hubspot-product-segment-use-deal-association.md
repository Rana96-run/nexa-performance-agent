---
name: finding_hubspot-product-segment-use-deal-association
description: HubSpot product-segmented audience seeds must use deal/lead associations — contact-level service interest properties have 0% fill rate on customers
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: 6 product-segmented LAL seed lists were built using contact-level `what_kind_of_service_are_you_interested_in` filter. All returned 0-1 members. That property and `qoyod_professional_service` both have 0% fill rate on customers — they're lead-form-time-only properties that don't propagate when a contact becomes a customer.

Source: memory/14_learning_patterns.md 2026-05-17.

Impact: All product-segmented lookalike audiences were empty; Meta/LinkedIn campaign targeting failed.

Fix / How to handle: Customer seeds → filter contacts whose associated Deal is in the product's pipeline + Closed Won stage. SQL seeds → filter contacts whose associated Lead (0-136) is in the product's Lead pipeline + Qualified/Connected stage. HubSpot Lists v3 association filter: `"filterBranchType": "ASSOCIATION"`, `"operator": "IN_LIST"`, objectTypeId 0-3 (Deal) or 0-136 (Lead). Must be wrapped in OR > AND > [association_branch] at root.
