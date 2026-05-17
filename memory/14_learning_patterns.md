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

## 2026-05-17 — HubSpot product-segmented Lookalike seeds: use deal/lead associations, NOT contact properties

**Trigger:** Built 6 product-segmented LAL seed lists using contact-level
`what_kind_of_service_are_you_interested_in` filter. All 6 returned 0-1
members.

**Root cause:** Sampled 500 customer contacts — that property + the
`qoyod_professional_service` alternative both have **0% fill rate** on
customers. They're lead-form-time-only properties that don't propagate
when a contact becomes a customer.

**The correct filter is association-based**, matching what the team builds
in the HubSpot UI:
- **Customer seeds** → filter contacts whose associated **Deal** is in the
  product's pipeline + Closed Won stage.
- **SQL seeds** → filter contacts whose associated **Lead** (object 0-136,
  separate from Contact lifecyclestage) is in the product's Lead pipeline
  + Qualified/Connected stage.

**HubSpot Lists v3 association filter syntax** (figured out the hard way):

```python
{
    "filterBranchType":     "ASSOCIATION",
    "filterBranchOperator": "AND",
    "objectTypeId":         "0-3",      # 0-3=Deal, 0-136=Lead
    "operator":             "IN_LIST",  # misleading name - means
                                        # "associated object matches filters"
    "associationCategory":  "HUBSPOT_DEFINED",
    "associationTypeId":    4,           # 4=contact->deal, 579=contact->lead Primary
    "filterBranches":       [],
    "filters":              [property_filter_1, property_filter_2, ...],
}
```

Must be wrapped in `OR > AND > [association_branch]` at the root.

**Pipeline + stage IDs discovered** (see DEAL_PRODUCT_MAP / LEAD_PRODUCT_MAP
constants in `executors/hubspot_lists.py`).

**Verification (2026-05-17):**
- Bookkeeping Customers: 683 members (manual reference 673 - 1.5% match)
- Bookkeeping SQLs: 636 members (manual reference 639 - 0.5% match)

**Learned:**
- HubSpot's `what_kind_of_service_are_you_interested_in` /
  `qoyod_professional_service` fields are lead-stage only; never use them
  for customer-stage segmentation. Always use deal/lead associations.
- ASSOCIATION filter `operator` must be `"IN_LIST"` — every other value
  (ANY, MATCHES, EXISTS) returns 400 from HubSpot Lists v3.
- Lead-object SQL pipelines have an Arabic-named pipeline ("خدمة المحاسبة
  عن بعد" = Bookkeeping). Always pull pipeline list dynamically rather than
  hardcoding English names.
- HubSpot Lists v3 API does NOT support list renaming. Rename in UI only,
  or create new + delete old.
- HubSpot Private App creator attribution is immutable — to attribute
  programmatic API calls to "Nexa Agent" instead of a human user, a dedicated
  HubSpot service-user account must own the Private App.

---

## (template for future entries)

## YYYY-MM-DD — <pattern name>

**Trigger:**
**Recommendation:**
**Decision:**
**Outcome (after Nd):**
**Learned:**
