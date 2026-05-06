# CLAUDE.md — Entry point for every Claude session

**You are working on the Qoyod Performance Agent.** Read in this order
before doing anything else:

1. **`docs/PLAYBOOK.md`** — who we are, audience, voice, goals,
   market rules. This is identity context; ~5 minute read.
2. **`memory/00_index.md`** — directory of topical memory files. Read
   only the ones relevant to the task at hand. Do **not** read them all
   up-front; that burns tokens for no gain.
3. **`.claude/skills/README.md`** — reusable recipes for repetitive
   tasks (running a collector, checking creds, verifying BQ, Drive
   reads, OAuth, Meta probes).

## Session start — always resume from latest state (non-negotiable)

Every session begins by reconstructing the current state, not starting fresh:

1. Run `git log --oneline -10` — read the last 10 commits to know what changed recently
2. Read `memory/09_open_tasks.md` — find pending/in-progress tasks and continue them
3. Read `memory/01_architecture.md` — confirm current schema, table names, view names
4. Check Railway deploy status (health endpoint) and recent log errors
5. Note any uncommitted local changes (`git status`) — address before new work

Then proceed directly to the most recent open task **without asking Amar to recap**.
See `.claude/skills/auto-update.md` for the full self-update protocol.

## Continuous learning (non-negotiable)

You build on accumulated knowledge every session — never from scratch:
- Before acting on any familiar topic, check `memory/` for existing context
- When you discover something new (API trap, naming edge case, schema change), write it to `memory/08_pitfalls.md` immediately
- When a task completes, close it in `memory/09_open_tasks.md` and update `memory/01_architecture.md` if the structure changed
- Each session must leave the agent more capable than it arrived

## Pre-send review (non-negotiable)

Before posting to Slack or creating Asana tasks, always verify:
1. **Slack daily format**: main message has dashboard URL (plain text), peak numbers (top + worst per channel with CPQL), agent actions spelled out in full (never abbreviations like IS/QS). Follow-up message has recommendations referencing Asana tasks + `#approvals` channel.
2. **Naming convention applied**: `{Channel}_{Type}_{Language}_{Product}_{Audience}` — no "Prospecting" audience, products normalized, LinkedIn UTM mapping correct (Group=utm_campaign, Campaign=utm_audience, Ad=utm_content).
3. **Asana task footer present**: every task description ends with Created, Due, Priority, Type, Channel, Asset level, Action.
   **Date ranges must always be explicit** (`YYYY-MM-DD to YYYY-MM-DD`, never "last 14 days"). This lets the team open HubSpot and filter the exact same window to verify numbers.
4. **Approval flow correct**: ALL actions go to ONE nightly #approvals digest. ✅ reaction executes all scale + pause items; ❌ skips them. optimize/junk/drilldown are review-only — Asana tasks already created, no further execution. Never auto-execute scale or pause without ✅.

A PreToolUse hook (`.claude/settings.json`) injects this checklist automatically before `slack_post_message` and `create_tasks`.

## Golden rules (non-negotiable)

- **No streaming BQ inserts.** Use `load_table_from_file(BytesIO(ndjson))`
  always. See `memory/08_pitfalls.md`.
- **HubSpot is read-only** unless Amar explicitly approves in Slack.
  No PATCH / DELETE / POST to HubSpot without sign-off.
- **Arabic copy is MSA.** Never colloquial. See `docs/PLAYBOOK.md` §4.
- **Secrets come from `.env` / Replit Secrets.** Never hardcode.
- **Spend is always reported in USD.** `campaigns_daily.spend` stores USD regardless
  of channel. Never label spend figures as SAR. Platforms returning micros (Google Ads
  `cost_micros`, Snap `spend`) are divided by 1,000,000 to get USD before writing to BQ.
- **Time zone is Asia/Riyadh (UTC+3)** for user-facing times; BQ stores UTC.

## KPI measurement rules (non-negotiable)

- **Cost comes from the channel** (`campaigns_daily.spend` — always USD, never SAR).
- **Leads and SQLs come from HubSpot Lead Module only** (`hubspot_leads_module_daily`).
  Never use `hubspot_leads_daily` (legacy contact lifecycle — nothing writes to it).
- **Evaluation order: CPQL first, then CPL.** A good CPL with bad CPQL = bad campaign.
- **Minimum window for pause/scale decisions: 14 days** (`DAYS_FOR_PAUSE_DECISION = 14`).
  Never act on fewer than 14 days of data.
- **Always pre-aggregate HubSpot before joining** to avoid spend fan-out:
  ```sql
  WITH hs AS (
    SELECT date, lead_utm_campaign,
           SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
    FROM hubspot_leads_module_daily
    GROUP BY date, lead_utm_campaign
  )
  SELECT c.*, hs.*
  FROM campaigns_daily c
  LEFT JOIN hs ON c.date = hs.date
             AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
  ```
  Direct JOIN without CTE multiplies spend by the number of matching HubSpot rows.

## Campaign naming convention (non-negotiable)

Format: `{Channel}_{Type}_{Language}_{Product}_{Audience}`

**Audience rules — enforced by `executors/naming.py`:**
- Prospecting campaigns → audience must be `Interests` or `Lookalike`. "Prospecting" alone is invalid and raises `ValueError`.
- Retargeting campaigns → audience is `Retargeting`. Never combine with "Prospecting".

**Product normalization — enforced, auto-corrected:**
- E-Invoice / einvoice / e_invoice → `Invoice`
- Qbookkeeping / bookkeeping → `Bookkeeping`
- qflavours / flavours → `Qflavours`
- Seasonal campaigns → use the actual season name (e.g. `Ramadan`, `NationalDay`, `BackToSchool`)

**Valid audience values:** `Interests` | `Lookalike` | `Retargeting` | `Broad`

Examples (Meta / Google / Snapchat):
```
Meta_LeadGen_AR_Invoice_Interests          ✓ prospecting with Interests
Meta_LeadGen_AR_Invoice_Lookalike          ✓ prospecting with Lookalike
Meta_LeadGen_AR_Invoice_Retargeting        ✓ retargeting
Snapchat_LeadGen_AR_Bookkeeping_Interests  ✓ Qbookkeeping auto-normalised
Google_Search_AR_Ramadan_Broad             ✓ seasonal
Meta_LeadGen_AR_Invoice_Prospecting        ✗ raises ValueError — use Interests or Lookalike
```

**LinkedIn UTM mapping is DIFFERENT — each level maps to a different UTM param:**

| LinkedIn level  | UTM param      | Name format                             | Example                          |
|----------------|----------------|-----------------------------------------|----------------------------------|
| Campaign        | `utm_campaign` | `LinkedIn_{Product}`                    | `LinkedIn_Invoice`               |
| Ad Set          | `utm_audience` | `LinkedIn_{Type}_{Language}_{Audience}` | `LinkedIn_LeadGen_AR_Interests`  |
| Ad              | `utm_content`  | `LinkedIn_{CreativeVariant}`            | `LinkedIn_VideoV1_AR`            |

> LinkedIn UI now matches Meta (Campaign / Ad Set / Ad). Previously called Campaign Group / Campaign / Ad.

All executors delegate to `executors/naming.py::prefixed()` — never bypass it.

## APPROVAL REQUIRED BEFORE ANY PAUSE / ENABLE / CREATE (non-negotiable)

**Never autonomously pause, enable, or create any ad, keyword, campaign, or ad group.**
Every write action — no matter how obvious — must go through one of these two paths:

1. **Slack approval** — post findings to `#approvals`, wait for ✅/❌ reaction, then execute.
2. **Manual prompt** — user runs `python scripts/bulk_ads.py execute` or
   `python scripts/bulk_keywords.py ...` themselves after reviewing the `audit` output.

The nightly `bulk_ads.py audit` and keyword review run automatically but only **report**.
They NEVER execute without explicit approval. If the agent identifies pause candidates,
it posts a summary to `#approvals` and waits. It does not call `execute` on its own.

This applies to everything: Meta ads, Google Ads keywords, campaigns, ad groups.
Exception: adding **negative keywords** can be direct-executed (no spend at risk).

## Keyword management rules (non-negotiable)

- **Keywords are NEVER posted to Slack.** Keyword expansion candidates go to Asana
  only. Negatives are direct-executed silently. The single source of truth for
  keyword policy is `executors/keyword_policy.py` — all call sites import from it.
- **Never remove a keyword unless its all-time spend = $0.** Only delete when zero
  cost ever. Low QS, low CTR, or poor performance = pause, not remove.
- **QS < 5 pause rule — CPA exception applies:**
  - If QS < 5 BUT conv ≥ 3 AND CPA ≤ $90 AND running 30+ days → **leave ENABLED**
  - If QS < 5 AND (conv < 3 OR CPA > $90) → **PAUSE** (after approval)
  - If QS < 5, CPA was ≤ $90, but CPA has since risen above $90 → **PAUSE** (after approval)
  - QS 0 (not set / PMax keywords) → do nothing, cannot evaluate
- **Negative keywords** can be added freely (no approval needed).

### Keyword policy buckets (enforced by `executors/keyword_policy.py`)

1. **ALWAYS_NEGATIVE** — direct-execute as negative, never proposed as a keyword,
   even if the term converted. Patterns:
   - login / sign in / signin / log in / تسجيل الدخول / تسجيل دخول
   - free / مجاني / مجانا / مجانية
   - course / training / دورة / دورات / كورس / كورسات
   - download / تحميل / تنزيل
   - loan / loans / financing / قرض / قروض / تمويل / تمويلات
   - job / jobs / career / hiring / وظيفة / وظائف / فرص عمل / توظيف
2. **BRAND_ONLY** — قيود / qoyod variants only allowed in campaigns whose name
   contains `Brand`. In any other campaign they are dropped from `add_kw` and
   routed to pause-watch for human review. They are NEVER added as negatives.
   **Exception (Arabic ambiguity):** "قيود" + accounting modifier (`محاسبية` /
   `المحاسبة` / `يومية` / `اليومية`) is the accounting NOUN ("journal entries"),
   NOT the brand name. Terms like `قيود محاسبية`, `قيود المحاسبة`, `قيود يومية`
   are feature keywords and route through as `normal`. Disambiguation list lives
   in `keyword_policy.QIYUD_FEATURE_MODIFIERS`.
3. **COMPETITOR** — competitor brand names. Currently tracked: Foodics (فودكس),
   Daftra (دفترة), Manager.io / الاستاذ المحاسبي, Wafeq, Zoho, QuickBooks, Odoo
   (اودو), Xero, Sage, Wave, plus generic منافس. **Rule:** ONLY allowed in
   campaigns whose name contains `Competitor`. In any other campaign:
   - Don't add as keyword (drop from `add_kw`)
   - Don't add as negative (we want to bid on these — just in the right campaign)
   - Pause-watch the keyword that triggered the search → human moves or pauses

### Cross-cutting keyword rules

- **Cadence: weekly, not daily.** Adding new keyword candidates AND pausing
  non-converting keywords run **once a week, on Sunday Riyadh time** — not
  every nightly run. The audit still computes candidates daily so we know the
  state, but the Asana task only fires on Sunday so the team batches the
  review at the start of the work week. Override for one-off runs:
  `FORCE_WEEKLY_KEYWORDS=1`. Negative-keyword direct-execution is unchanged
  (still daily — no spend at risk).
- **Sunday auto-fix is silent.** On Sunday Riyadh, `_run_weekly_keyword_autofix`
  in the operational scheduler scans + applies the rule-mandated action
  (pause / delete / remove-negative) without creating per-violation Asana
  tasks. Counts get logged to BQ; Monday's weekly Slack summary surfaces them
  as a "🔧 Auto-fixed this week" block.
- **Minimum age: 10 days before pausing for performance.** A non-converting
  keyword must have first impressed ≥ `MIN_KEYWORD_AGE_DAYS` (=10) days ago
  before being eligible for the QS+IS-lost rule OR the wasted-spend pause
  rule. Younger keywords get queued for next week — they haven't had time to
  perform. **Exception:** ALWAYS-NEGATIVE policy violations (login / دورة /
  تحميل / etc.) bypass age — those should never be a keyword at any age.
  Helper: `keyword_policy.keyword_first_impression_dates()` (queries last
  365 days of `keyword_view` impressions).
- **30-keyword cap per ad group.** No ad group may exceed 30 enabled keywords.
  When the weekly audit proposes additions, candidates are sorted highest-conv
  first per ad group and only `(30 - existing_count)` are kept; the rest are
  dropped with the reason surfaced in the Asana task body. Helper:
  `analysers.google_ads_audit.filter_kw_against_adgroup_cap()`.
- **Don't ADD a keyword with QS<5 AND >80% lost-IS.** This combination signals
  a keyword that won't win impressions and will lower account-level QS — even
  if it's in our candidate list, drop it. (Applies to existing keywords too —
  see next rule.)
- **EXISTING keyword with QS<5 AND >80% lost-IS:**
  - If all-time spend = 0 → **DELETE** (zero cost, safe to remove cleanly).
  - If all-time spend > 0 → **PAUSE** (per "never delete with cost" rule).
  - Detection: `scripts/audit_active_keywords.py`, lookback window 180 days
    for "all-time spend".
- **Language match (non-negotiable).** A keyword's script must match its
  campaign's language token (`_AR_` / `_EN_`). Latin keyword in Arabic campaign
  or vice versa → pause-watch. Mixed-script terms (transliterated brand inside
  Arabic) are tolerated. Detection: `keyword_policy.is_language_mismatch()`.
- **Wasted-spend KEYWORDS are paused, not negated.** A keyword that has
  burnt $80+ in 7 days with 0 conversions gets PAUSED (not added as negative
  — the keyword itself is the problem, not just one matched query). Threshold
  in `config.KEYWORD_PAUSE_SPEND` / `KEYWORD_PAUSE_DAYS`. Pausing also runs
  WEEKLY only.
- **Never add competitor terms as negatives.** Competitors live in Competitor
  campaigns; negating them in other campaigns blocks the right traffic too.

### Audit scripts (run on demand)

- `python scripts/audit_active_keywords.py` — scans all ENABLED keywords for
  policy violations (always-negative-as-keyword, قيود-in-non-brand,
  competitor-in-generic, language-mismatch). Read-only; creates an Asana task.
- `python scripts/audit_active_negatives.py` — scans all ACTIVE negative
  keywords (campaign + ad-group level). Removes any that match competitor or
  brand-only patterns (removing a negative is safe — re-opens a query). Logs
  removals to Asana.

## Ad pause rules (non-negotiable)

Applied to `ads_daily` joined to `hubspot_leads_module_daily` on `lead_utm_content`:

- **Zero-conversion pause:** spend > $70 over 7+ days with 0 platform conversions → PAUSE
- **Junk lead pause:** ad running 10+ days, converting leads, but
  `leads_disqualified / leads_total >= 0.60` (60%+ disqualification rate) → PAUSE
- **High CPL pause:** CPL (`spend / hs_leads`) > $50 for 10+ days → PAUSE
- **Never remove an ad** — only pause. All ad actions logged and approval-gated.
- These same rules apply in the manual ad-management tool (`scripts/bulk_ads.py`).

## Two runtimes (don't confuse them)

- `reporting_scheduler.py` — 6h data refresh, dashboard-only
- `main.py daily` — always-on operational agent (Slack, Asana, pause/scale
  watchers)

See `memory/05_scheduler.md`.

## Before asking a question (non-negotiable)

Before asking Amar anything, exhaust the knowledge base first:

1. Check `memory/00_index.md` — find the relevant memory file and read it
2. Check `memory/08_pitfalls.md` — the answer may already be documented as a known trap
3. Check `memory/01_architecture.md` — for schema, table names, field names
4. Search the codebase with Grep for the symbol, field, or pattern in question
5. Check `.claude/skills/README.md` — there may be a recipe for it

Only ask Amar **after all of the above have been checked and found no answer**.
When you do ask, state what you already checked so the answer can be written back to memory.

When raising a question, also include **3 follow-up questions** — things that
are likely to break or become ambiguous in future edits related to the same area.
Format them as:
> **While we're here — 3 things that may break later:**
> 1. …
> 2. …
> 3. …

This keeps decisions in memory before they become bugs, not after.

## Always choose simpler and sustainable (non-negotiable)

Before building anything new, ask: does a tool already in use solve this?

- **Use what exists** — Hex is the dashboard (not Streamlit). Railway hosts the agent (not Replit). HubSpot holds leads (not a custom DB).
- **No new infrastructure** unless the existing tool genuinely can't do it.
- **Prefer editing over rebuilding** — update a Hex cell before writing a new page; update a BQ view before adding a new collector.
- **If two options exist**, pick the one with fewer moving parts, fewer credentials to manage, and fewer things that can break.
- **Call it out** — if asked to build something that already exists elsewhere in the stack, say so and propose the simpler path instead.

## When unsure

- **Ask Amar in Slack** rather than invent data or guess a field name — **only after searching memory/ first**
- **Add to `memory/08_pitfalls.md`** the moment a new API trap is
  discovered — one line, include the fix
- **Add to `memory/09_open_tasks.md`** for work that spans sessions

## Update discipline

When a fact changes, edit the relevant `memory/*.md` in place. Don't
sprinkle updates across code comments or commit messages.
