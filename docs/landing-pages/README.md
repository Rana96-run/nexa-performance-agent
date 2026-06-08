# Landing Pages — CRO Department Workspace

This is where the **CRO / Landing Page** department does its work. The folders
mirror the department's sequential handoff chain — each stage writes its artifact
into the next folder and hands off:

```
cro-specialist  ──►  ui-ux-designer  ──►  developer  ──►  (back to) cro-specialist
   writes              writes               writes            reads result,
   briefs/             designs/             specs/            calls the test
```

| Folder | Owner | Holds |
|---|---|---|
| `_templates/` | shared | the 8-section LP brief template + the ZATCA/pixel/UTM compliance checklist |
| `briefs/` | `cro-specialist` | one brief per test: hypothesis, 8 sections, success criteria (14-day CPQL + destination_url) |
| `designs/` | `ui-ux-designer` | annotated LP designs aligned to the OCEAN persona, ZATCA badge above fold, interaction notes |
| `specs/` | `developer` | build/deploy spec: UTM passthrough map, both pixel fires, deploy target, Events-Manager verification |

## Naming convention
One file per test, named `YYYY-MM-DD_<product>_<hypothesis-slug>.md`, e.g.
`2026-06-08_invoice_zatca-above-fold.md`. The **same filename** travels through
`briefs/ → designs/ → specs/` so a test is traceable end-to-end.

## Where the production page lives
These folders hold the **artifacts** (brief → design → spec), not the production
HTML. The `developer` deploys the actual variant to the live site and verifies
the pixel fires in Meta Events Manager before sign-off. This workspace is the
paper trail; the live site is the deploy target.

## Non-negotiables (every test)
- **ZATCA compliance badge above the fold** — see `_templates/zatca-checklist.md`.
- **UTM passthrough on every form field** — a dropped UTM corrupts CPQL.
- **Both Meta pixels fire**: Qoyod_CRM_PIXEL `1782671302631317` + Qoyod_Web_PIXEL `3036579196577051`.
- **14-day data window** + a written success criterion before any test starts.
