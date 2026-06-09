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

## 2026-06-09 — Post-fix recon: v_ad_performance leads fan-out only PARTIALLY fixed

**Trigger:** Ran the 7-day BQ↔HubSpot reconciliation (2026-06-02..2026-06-08) on
`v_ad_performance` after the name-grain/fan-out fix (13c76e4). Aggregate had passed
at 14d, so the expectation was "clean."

**Recommendation:** Reconcile PER-CHANNEL, not just total. Result: only Google Ads
reconciles (308 vs HubSpot 332, ratio 0.93). Meta 1.87x, Snapchat 2.14x, TikTok 2.03x,
Microsoft 4.00x — all OVER-COUNT. Root cause: the leads re-join inside `v_ad_performance`
under-dedups (view produces 101 AB-combos / 311 Snapchat leads vs HubSpot 80 buckets /
148); upstream `utm_paid_attribution_daily` is itself correct (meta/tiktok/google EXACT).
Plus a `microsoft`/`microsoft_ads` channel-label dup double-counts Microsoft. Recommend
developer: source leads from `utm_paid_attribution_daily` AB grain rather than re-joining
HubSpot in `v_ad_performance`, and normalize the proxy channel string.

**Decision:** flagged to developer — view-SQL fix, DATA-owned diagnosis, no ad-account write.

**Outcome (immediate, verified live):** Reconciliation FAILED for 4/5 paid channels;
documented in `08_pitfalls.md`. Numbers are live BQ, not recollection.

**Learned:**
- **A reconciliation on the org-wide TOTAL is worthless** — a large clean channel
  (Google Ads) masks 2x over-counts on smaller channels. ALWAYS reconcile per-channel,
  and per-channel is the bar for declaring a fan-out fix "done."
- **"Total ≤ HubSpot truth" is necessary but NOT sufficient.** The earlier fix met
  `1585 ≤ 1843` and was called verified; per-channel it was still 2x wrong. Verification
  must match the grain of the claim — if the view is per-ad, reconcile per-channel minimum.
- When a downstream view re-joins a source that an upstream view already attributed
  correctly, suspect the downstream re-join first — check the upstream view's per-channel
  leads before assuming the source data is wrong.

## 2026-06-09 — Fixed name-grain collapse + leads fan-out in v_ad / v_adset_performance

**Trigger:** Code review flagged the `platform` CTE grouping by name with
`ANY_VALUE(ad_id)`. Live BQ confirmed 370 spend-bearing same-name/diff-ID merged
groups ($7.8k/30d) at ad level, 63 ($4.8k) at adset. Investigation also surfaced a
latent leads fan-out: v_ad_performance reported 5111 leads (14d) vs HubSpot truth
1433 = 3.57x over-count, because the name-keyed platform↔HubSpot FULL OUTER JOIN
repeated `h.leads` across every matching name-row and the old guard only deduped spend.

**Recommendation:** group platform CTE by ID (ad_id/adset_id); restructure SELECT into
joined CTE + outer SELECT with leads-once-per-HubSpot-source-row and deals-once-per-bucket
window guards alongside the existing spend guard.

**Decision:** approved (DATA-owned view fix, no ad-account write).

**Outcome (immediate, verified live):** Check A 370→0 collapse (819 distinct ad_id rows
now kept). Leads 5111→1585, ≤ HubSpot 1843 — fan-out eliminated. Spend held exact
(18270.01 == ads_daily). Materialized + committed 13c76e4.

**Learned:** When auditing any platform↔HubSpot view, check BOTH (a) ID carried via
ANY_VALUE on a name grain (silent entity merge) and (b) leads/deals fan-out from the
name-keyed join — spend being correct does NOT imply leads are. Reconcile view leads
against `hubspot_leads_module_daily` for the window; view total must be ≤ source.

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

## 2026-06-08 — Runtime/subagent unification (deferred, by design)

**Trigger:** After building the 9 dev-time subagents + their playbooks, the
question arose whether to point `claude/roles.py` (the Railway runtime) at those
playbooks so dev-time and production share one source of truth.
**Recommendation:** Do NOT blind-repoint. Runtime personas (`runtime_personas/qoyod-*.md`)
are rich ~23KB operating prompts; the dev playbooks are tight procedures.
Repointing would shrink the runtime prompts and degrade production. Unify instead
by cross-reference (the 3-taxonomy bridge table in `11_agent_roles.md`), or grow
the playbooks to runtime depth first, then repoint.
**Decision:** deferred — left for an explicit go (touches live code).
**Outcome (after Nd):** n/a (not executed).
**Learned:** "one source of truth" ≠ "one file" when two consumers need different
depth. Bridge with a mapping table before merging prompts.

---

## (template for future entries)

## YYYY-MM-DD — <pattern name>

**Trigger:**
**Recommendation:**
**Decision:**
**Outcome (after Nd):**
**Learned:**
