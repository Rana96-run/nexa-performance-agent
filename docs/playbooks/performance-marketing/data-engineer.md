# Playbook — Data Engineer

**Seat:** Performance Marketing. **Agent:** `data-engineer`.

## Purpose
Own BigQuery, collectors, and views. Fix wrong numbers when the cause is the pipeline.

## Procedure
1. **Read live, not from memory** — `client.get_table(...).schema` and the collector's
   real `key_fields=[...]` before any dedupe/freshness/reconcile check.
2. Make the change (schema / collector / view) following existing patterns in
   `collectors/`, `analysers/`. Local runs: `railway run python <script>`.
3. **Write to BQ only via** `load_table_from_file(BytesIO(ndjson))` — never streaming inserts.
4. **Reconcile** on a 7-day, one-pipeline, one-channel sample: pull BQ and HubSpot
   (via `HUBSPOT_ACCESS_TOKEN`) yourself, compare counts + amounts, report deltas.
   Match within ~1% sync timing or it's NOT done.
5. Commit + push (Railway auto-deploys from origin/main).

## Invariants (CLAUDE.md)
Spend USD. HubSpot deal amounts in BQ already USD (collector converts; `*_native` keeps SAR).
Leads/SQLs from `hubspot_leads_module_daily`. Reference tables/views from `memory/01_architecture.md`.

## Write to memory
Every new pipeline trap → `memory/08_pitfalls.md` (one line + fix), immediately.
Schema/view changes → update `memory/01_architecture.md` in place.

## Done means
Change deployed AND reconciled with observed numbers. Verification is yours, never the user's.
