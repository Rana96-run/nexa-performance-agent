# Skill: auto-update — keep the system current after every change

Run this protocol **automatically** after any edit, new feature, schema change,
API decision, or naming rule. Do not wait to be asked.

---

## 1. After any code change

| What changed | What to update |
|---|---|
| New BQ table / view | `memory/01_architecture.md` — add table name, schema, purpose |
| New collector / scheduler | `memory/05_scheduler.md` — add job name, frequency, trigger |
| New channel added | `memory/01_architecture.md` + `memory/03_channels.md` + `looker/setup.py` views |
| Naming rule changed | `CLAUDE.md` Campaign naming section + `executors/naming.py` + `memory/08_pitfalls.md` |
| API trap discovered | `memory/08_pitfalls.md` — one line, include the fix |
| Executor changed | `memory/09_open_tasks.md` — close the task, note what shipped |
| Dashboard page added | `dashboard/app.py` navigation hint + `memory/01_architecture.md` |

## 2. After any discussion / decision with Amar

Even if no code changed, if a **decision was made** (e.g. "always use Lookalike not Broad for Retargeting",
"LinkedIn campaign level = utm_campaign"), write it to the right memory file immediately:

- Naming / UTM decisions → `CLAUDE.md` naming section
- KPI thresholds / zones → `CLAUDE.md` KPI section + `memory/06_kpis.md`
- API / platform quirks → `memory/08_pitfalls.md`
- Architecture decisions → `memory/01_architecture.md`
- Open work → `memory/09_open_tasks.md`

## 3. Session close checklist

Before the session ends (or context runs low), run through:

- [ ] All new facts written to `memory/`
- [ ] Completed tasks closed in `memory/09_open_tasks.md`
- [ ] All code changes committed and pushed to Railway
- [ ] `memory/01_architecture.md` reflects current table/view list
- [ ] No decision lives only in the chat — it must be in a file

## 4. Session resume checklist (run at START of every session)

```
git log --oneline -10              # what shipped recently
cat memory/09_open_tasks.md        # what is still open
cat memory/01_architecture.md      # current schema state
curl <railway-health-url>          # is the deploy healthy
git status                         # any uncommitted work to finish first
```

Then continue the **most recent open task** without asking Amar to recap.

## 5. Self-update rule

If this skill file itself becomes outdated (new table pattern, new channel,
new runtime), update it in the same commit that introduces the change.
The skill must always describe reality, not history.
