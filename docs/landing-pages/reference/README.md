# LP Reference Knowledge (snapshot from the Landing Page Agent)

This is the CRO department's **local copy** of the landing-page knowledge it
needs, so the team is self-contained instead of reaching into another repo at
run time. Copied 2026-06-08 from `D:\Landing Page Agent\`.

> **Source of truth:** `D:\Landing Page Agent\` is maintained by Rana Khalid and
> remains the SoT. These files are a **snapshot** — if the LP Agent's design
> system / brand / prompts change, re-sync this folder. Don't fork the brand here.

## Contents
| Path | What | Used by |
|---|---|---|
| `lp-design-system.md` | Paid/conversion design reference (tokens, brand truth, sections) | all CRO |
| `brand/design-system.md` | Full design system that built qoyod.com | `cro-specialist` |
| `brand/landing-page-wireframes.md` | Section-by-section LP wireframes | `cro-specialist` |
| `brand/value-proposition.md` · `messaging-strategies.md` · `segments.md` | Positioning, messaging, audience segments | `cro-specialist`, `creative-strategist` |
| `brand/identity-guidelines.md` · `ethical-guidelines.md` | Brand identity + ethical limits | all CRO |
| `brand/anti-claims.md` | Claims we may NOT make (compliance) | `cro-specialist`, `developer` |
| `prompts/*.md` | Per-product/sector LP build prompt templates (accounting, bookkeeping, POS, Qflavours, ZATCA, sectors) | `developer` (build), `cro-specialist` (brief) |

## What was deliberately NOT copied
The LP Agent's SEO/organic docs, completed HTML pages, screenshots, Elementor
JSON, and build scripts stay in `D:\Landing Page Agent\` — they're that repo's
workspace and/or belong to other departments, not CRO reference knowledge.

## Re-sync
To refresh: re-copy `lp-design-system.md`, `prompts/*.md`,
`docs-rana/docs-rana/brand/*.md`, and `product/anti-claims.md` from the LP Agent.
