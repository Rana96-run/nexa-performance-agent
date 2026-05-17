# Learning patterns — what worked, what didn't

This file is the agent's outcome library. Every time a recommended action
is executed and observed for 7–14 days, record the pattern + outcome here.
The next session reads this file before recommending a similar action.

Format per entry:

```
## YYYY-MM-DD — <pattern name>
**Trigger:** <what the agent saw>
**Recommendation:** <what the agent proposed>
**Decision:** approved | overridden | skipped
**Outcome (after Nd):** <CPQL/ROAS/leads delta + qualitative note>
**Learned:** <one-line takeaway for future runs>
```

---

## 2026-05-17 — Mass-pause + LP-repoint after May 4–10 launch wave

**Trigger:** May 1–16 vs Apr 1–16 audit showed CPQL +44%, 4 flags
(CPQL_REGRESSED, ROAS_REGRESSED, QUAL_DROPPED, LAUNCH_WAVE). Root cause:
8 new Generic/ImpressionShare campaigns launched May 4–10 routed to a
new WP `/accounting` LP.

**Recommendation:** Pause PMax_AR_Generic, Generic_Retargeting, the Bing
5-pack; cut WebsiteTraffic to 40% pace; re-point Google Generic LP to
HubSpot `electronic-invoicing`.

**Decision:** ✅ approved (in Asana tasks 1–18); execution pending team

**Outcome (after Nd):** to be filled by post-action monitor

**Learned (pre-result):**
- 8+ new campaigns in 6 days = launch wave that compounds CPQL damage
- Sending Generic-intent traffic to a fresh-pixel LP guarantees garbage
- "Same CPL on two LPs" can hide a 2× CPQL gap when campaign mix differs

---

## 2026-05-17 — PMax_AR_E-Invoice "silent death" was deliberate

**Trigger:** spend_drift Rule 2 (silent death) flagged `PMax_AR_E-Invoice`
$3k → $3. Initial framing: "investigate accidental pause; re-enable."

**Recommendation:** Investigate cause, restore if accidental.

**Decision:** investigated; status=PAUSED on Apr 20 with daily CPQL
trajectory of $200–$574 in the days before pause — deliberate human call.

**Outcome:** No action needed. Asana task closed as "no action" rather
than re-opened.

**Learned:**
- Silent-death rule should weight `recent_status` heavily; PAUSED status
  almost certainly means deliberate, not accidental
- Aggregating "first-16-days" CPQL can mask a within-period cliff. Always
  check the daily trajectory before declaring a campaign "was a winner"

---

## (template for future entries)

## YYYY-MM-DD — <pattern name>

**Trigger:**
**Recommendation:**
**Decision:**
**Outcome (after Nd):**
**Learned:**
