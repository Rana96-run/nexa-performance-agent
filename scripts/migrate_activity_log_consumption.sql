-- ─────────────────────────────────────────────────────────────────────────────
-- Migration: extend agent_activity_log with consumption-tracking columns
-- Run once. Idempotent (uses IF NOT EXISTS).
-- GoogleSQL (Standard SQL) — not legacy.
--
-- Adds:
--   tokens_in        — Anthropic input tokens (per row, when role logs an LLM call)
--   tokens_out       — Anthropic output tokens
--   cost_usd         — total $ cost of this row (LLM + BQ + anything else)
--   api_calls        — count of HTTP calls to platform APIs (Google/Meta/Snap/…)
--   bq_bytes_scanned — BigQuery bytes scanned by this row's queries
--
-- After running, all five fields are nullable so existing rows stay valid.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
  ADD COLUMN IF NOT EXISTS tokens_in        INT64   OPTIONS(description="Anthropic input tokens consumed by this action"),
  ADD COLUMN IF NOT EXISTS tokens_out       INT64   OPTIONS(description="Anthropic output tokens consumed by this action"),
  ADD COLUMN IF NOT EXISTS cost_usd         FLOAT64 OPTIONS(description="Total USD cost of this action — LLM + BQ + any priced API"),
  ADD COLUMN IF NOT EXISTS api_calls        INT64   OPTIONS(description="Count of outbound HTTP calls to platform APIs"),
  ADD COLUMN IF NOT EXISTS bq_bytes_scanned INT64   OPTIONS(description="BigQuery bytes scanned by queries this action ran");
