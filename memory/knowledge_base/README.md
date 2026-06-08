# Knowledge Base

Curated, longer-form **reference knowledge** — the "how things map / how things
work" guides that don't fit the append-only topical notes (`../NN_*.md`) or a
single agent's memory. This is where durable, cross-cutting reference docs live
(consolidated here so they stop scattering across `md_files/` and the repo root).

## How memory is organised (so you know where to look / write)
| Layer | Path | What |
|---|---|---|
| **Critical rules** | `../CRITICAL_KPI_RULES.md` | non-negotiables, read every session |
| **Topical notes** | `../NN_*.md` | append-only single-concern notes (architecture, bigquery, pitfalls, learning patterns…) |
| **Knowledge base** | `knowledge_base/` *(here)* | curated reference guides + mappings |
| **Per-agent memory** | `../agents/<dept>/<role>/` | one agent's private feedback + learnings |
| **Team docs** | `../../docs/_shared/` + `../../docs/playbooks/` | org chart, handoffs, how-to, playbooks |

## Articles
- [looker_to_bq_mapping.md](looker_to_bq_mapping.md) — the 3 Looker dashboards → BigQuery field mapping
- [organic_setup_guide.md](organic_setup_guide.md) — organic-channel setup reference

## Related reference (lives elsewhere, by necessity)
- `../../md_files/qoyod-brand-identity.md` — brand identity (kept in md_files because the
  Railway runtime `claude/roles.py` loads it by exact path; don't move it).
- `../13_hubspot_fields.md` · `../07_attribution.md` — HubSpot/UTM field reference.

## Adding a KB article
Drop a focused `.md` here for any durable reference guide (a mapping, a setup
walk-through, a methodology). One topic per file. Add a row above. If it's a
single short fact instead of a guide, it belongs in a `../NN_*.md` note or a
per-agent memory file — not here.
