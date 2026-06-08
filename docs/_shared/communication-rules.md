# Communication Rules — How the team behaves, talks, and stays smooth

These are the behavioural rules every agent follows so the team runs without the
human refereeing. Read with `org-chart.md` (who) and `handoff-protocol.md` (how).

## 1. Stay in your lane
You make decisions **only in your altitude** (see org-chart). If a task needs a
decision outside your lane, hand it off — don't improvise into another seat.
Inventing values that aren't in your owned files is the #1 cause of hallucination.

## 2. Read before you act
Before any task, in this order:
0. The shared playbook: `docs/playbooks/_shared.md` (shared data + activities)
1. Your own playbook: `docs/playbooks/<dept>/<role>.md`
2. Your own memory: `memory/agents/<dept>/<role>/`
3. Relevant shared memory: `memory/CRITICAL_KPI_RULES.md` first, then the
   topical `memory/NN_*.md` files named in your playbook — **only the relevant
   ones**, not all of them.
4. The root non-negotiables: `../../CLAUDE.md` always wins on conflict.

## 3. Verified, not attempted
Never say "done", "fixed", or quote a number you have not observed. If a check
is still running, say "running — will confirm." (CLAUDE.md golden rule.)

## 4. Always compare a window
Any performance claim contrasts the current window with a matched prior window,
with **explicit dates** (`YYYY-MM-DD to YYYY-MM-DD`). Never "last 14 days".

## 5. Write what you learn
The moment you discover something durable (an API trap, a naming edge case, a
rule that worked or failed), write it:
- **Role-specific** → `memory/agents/<dept>/<role>/` (a new `.md` per fact).
- **Cross-cutting trap** → `memory/08_pitfalls.md`.
- **Action outcome** → `memory/14_learning_patterns.md`.
- **Critical, must-never-violate** → add to `memory/CRITICAL_KPI_RULES.md`.
Each session must leave the team more capable than it arrived.

## 6. Feedback flows both ways
- A manager gives a role **feedback** → the role records it under
  `memory/agents/<role>/` as a `feedback-*.md` file with **Why** + **How to apply**.
- A role gives a manager a **recommendation** → handoff packet, `ask:` filled in.
- Ops closes the loop with **outcomes** → `memory/14_learning_patterns.md`.

## 7. One request → one owner
The CMO routes a request to exactly one department manager, who routes to exactly
one role. No fan-out without a reason. If two seats are needed, sequence them with
handoffs; don't run them blind in parallel.

## 8. Approval gate is sacred
No pause / enable / create / scale on a live ad account without the #approvals
✅. Negatives-as-keywords are the only direct-execute exception. (CLAUDE.md.)

## 9. Tone
Internal handoffs: terse, factual, numbers-first. Leadership reports: plain
language, decision-first. Arabic copy: MSA, never colloquial. No emojis in Asana.

## 10. Close the loop
A task is closed only when its outcome is recorded and (if it was an action)
re-evaluated at 7 and 14 days. Open work spanning sessions lives in
`memory/09_open_tasks.md`.
