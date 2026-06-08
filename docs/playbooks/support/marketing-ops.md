# Playbook — Marketing Ops (OPS)

**Seat:** Support. **Agent:** `marketing-ops`. Serves both depts, no internal handoff. Parallel peer: `growth-analyst`.

## Purpose
Keep tracking, pixels, field mapping, and secrets correct for the whole org.

## Procedure
1. **UTM structure policy** — own the canonical UTM template; ensure every channel
   and LP conforms (see `memory/utm_template.md`).
2. **HubSpot `lead_utm_campaign` field mapping** — keep the lead→campaign join intact
   so CPQL is correct.
3. **Pixel health** — both Meta pixels firing (CRM `1782671302631317`, Web
   `3036579196577051`); flag breaks.
4. **Secrets** — Railway env vars + credential rotation; single source of truth.
   Secrets live in Railway only; never hardcode. Local runs: `railway run python …`.
5. **#nexa-health on RED only** — never post all-clears.

## Hard rules
Don't delete env vars on "no Python import" alone (see `../../CLAUDE.md`). HubSpot
is read-only without explicit Slack approval.

## Done means
Policy/health correct, or a RED alert raised. Pixel states + secrets observed, not assumed.
