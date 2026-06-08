---
name: no-streaming-inserts
description: Write to BQ only via load_table_from_file(BytesIO(ndjson)) — never streaming inserts
metadata:
  type: critical
---

All BigQuery writes go through `load_table_from_file(BytesIO(ndjson))`. Never use
streaming inserts (`insert_rows*`). Streaming rows sit in a buffer that can't be
updated/deleted for ~90 min, breaks dedupe, and costs more.

**Why:** the agent has repeatedly hit dedupe and freshness false-alarms caused by
streaming-buffer rows; load jobs are atomic and queryable immediately.

**How to apply:** build NDJSON, wrap in `BytesIO`, `load_table_from_file`. Before
any dedupe/reconcile, read the live schema + the collector's real `key_fields`.
Cross-ref [[../../../08_pitfalls.md]].
