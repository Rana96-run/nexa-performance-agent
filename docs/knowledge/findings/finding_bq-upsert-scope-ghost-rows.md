---
name: finding_bq-upsert-scope-ghost-rows
description: upsert_rows with secondary scope key_field accumulates ghost rows when lead source changes — use date-only key for date-partitioned tables
metadata: 
  node_type: memory
  type: finding
  originSessionId: 284817cb-4507-4772-bfff-6dea3d56e0f5
---

What was found: When `key_fields=[date, scope_field, ...]`, the DELETE only removes rows where `scope_field IN (values present in the new build)`. If a lead's source changes between builds, the old row (old_source, same date) is NEVER deleted. Found 2026-05-11: 60,156 rows / 186,384 leads (5x inflated) in `hubspot_leads_module_daily`.

Source: memory/08_pitfalls.md "BigQuery: upsert_rows scope-field DELETE".

Impact: 5x lead inflation — every CPQL metric was critically wrong.

Fix / How to handle: For tables rebuilt entirely per date, use `key_fields=["date"]` only — DELETE wipes the whole date partition before re-inserting. `hubspot_leads_module_daily` was fixed this way. Never use a secondary scope field as a key for date-partitioned tables that are fully rebuilt per date.
