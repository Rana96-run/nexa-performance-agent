---
name: secrets-in-railway-only
description: Secrets live in Railway only; never hardcode; don't delete an env var based on "no Python import" alone
metadata:
  type: critical
---

Secrets live in **Railway only** — never hardcode, never commit. `.env` holds only
`GOOGLE_APPLICATION_CREDENTIALS` locally; `.env.example` is the keys-only reference.
Local runs use `railway run python <script>`.

**Why:** Marketing Ops is the single source of truth for secrets; a leaked or
deleted var causes silent outages (a var may be used by GH Actions, a disabled-but-
returning feature, or hold human metadata — not just Python imports).

**How to apply:** before removing any env var, check the three questions in
[[../../../../CLAUDE.md]] ("Don't delete env vars based on no-import alone"). When
unsure, keep it. Fire #nexa-health on RED only — never all-clears.
