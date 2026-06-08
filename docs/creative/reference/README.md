# Creative Reference (knowledge from the Design Agent)

The creative-strategist's local copy of the reusable creative knowledge, so the
seat is self-contained. Copied 2026-06-08 from `D:\Design Agent\` (a separate
design-generation pipeline — see "About the source" below).

## Contents
| File | What | Use |
|---|---|---|
| `qoyod_design_philosophy.md` | Qoyod's design philosophy | direction for every brief |
| `design-agent-system-prompt.md` | the Design Agent's full creative system prompt | voice/identity for creative |
| `design-skillset.md` | the design skillset | what good creative covers |
| `design-instructions.md` | operating instructions | process reference |
| `brand-identity.md` | brand identity reference | on-brand creative |
| `design-patterns.md` | reusable design patterns | variant scoping |
| `prompt-templates.md` | creative/design prompt templates | brief → asset prompts |
| `campaign-analysis.md` | campaign analysis reference | tie creative to performance |
| `design-learnings.json` | accumulated design learnings | what worked before |
| `how-to-generate-designs.md` | the operating guide — pipeline, formats, HiggsField, key rules | run the designer capability |

## About the source (`D:\Design Agent\`)
That folder is a **working design-generation pipeline** — Python generators
(`generate.py`, `compositor.py`, `presets.py`), a scheduler (`jobs/weekly.yaml`),
output history (`output/`), fonts, and ~51MB of assets/samples. Only the
**knowledge** (the md docs + learnings above) was copied here; the machinery and
assets were NOT. If the pipeline still generates designs, it remains the source of
truth — re-sync these files if its philosophy/brand/patterns change.

## Note
Creative *production* (cutting actual assets) stays external/with the Design
Agent. `creative-strategist` owns **direction** — it reads this reference to brief
on-brand, persona-mapped creative; it doesn't generate the assets itself.
