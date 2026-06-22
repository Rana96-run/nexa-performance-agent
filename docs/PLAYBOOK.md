# Qoyod Performance Agent — AI Playbook

> Structured context so Claude knows exactly who we are, what we do, and how we
> work. Read this **before** `memory/00_index.md` every new session.
>
> Template by Amar Yassir (Claude Playbook Template). Living document — update
> whenever strategy, audience, or goals change.

---

## 1. Identity — Who Are You?

**Name and role**
Amar Yassir — Head of Product Marketing at Qoyod.

**Business / project**
Qoyod is a Saudi cloud accounting SaaS for SMEs (ZATCA-compliant e-invoicing,
VAT, inventory, payroll). This project — **Nexa / Qoyod Performance Agent** —
is the in-house AI marketing & performance system: it collects paid + organic
+ CRM data into BigQuery, runs daily optimization logic, posts Slack
approvals, and powers a Streamlit reporting dashboard.

**Country / primary market**
Saudi Arabia (KSA) + wider GCC. Arabic-first audience.

**Industry**
B2B SaaS — accounting & fintech for SMEs.

---

## 2. Audience — Who Are You Trying to Reach?

**Primary audience**
Saudi SME owners and finance leads (10–200 employees), retail / F&B / services
/ trading, Riyadh & Jeddah & Eastern Province. Pain points:
1. ZATCA e-invoicing compliance pressure — worried about fines
2. Manual bookkeeping eats owner/finance-manager time
3. Tools that aren't truly Arabic (just Google-translated) frustrate staff

**Secondary audience**
Accounting firms and bookkeepers who recommend software to their SME clients.
Also internal stakeholders (CEO, performance team, finance) who read the
dashboard.

**What they care about**
Compliance (ZATCA, VAT), saving time, clear Arabic UX, price transparency,
local payment methods (Mada, STC Pay), reliable support in Arabic.

---

## 3. Positioning — What Makes You Different?

**Biggest differentiator**
Qoyod is Arabic-first and Saudi-first — built for ZATCA from day one, not a
translated foreign tool retrofitted for the region.

**Top competitors**
- **Zoho Books** — international, Arabic is translated; we win on local
  compliance depth and native Arabic UX.
- **Wafeq** — also regional; we win on breadth (inventory, payroll, POS
  integrations) and ecosystem maturity.
- **Odoo / SAP Business One** — enterprise-weight; we win on SME simplicity
  and price.

**Positioning statement**
> We are the only accounting platform that is Arabic-first and ZATCA-native
> for Saudi SMEs, unlike translated foreign tools or heavy enterprise ERPs.

---

## 4. Voice & Tone — How Do You Communicate?

**Tone**
- Direct / no-fluff (internal analytics & Slack)
- Educational / authoritative (external content)
- Warm & respectful in Arabic (customer-facing)

**Languages**
- Arabic (Modern Standard Arabic — MSA) for all customer-facing copy. Never
  colloquial dialect in product/marketing.
- English for internal engineering, dashboards, Slack threads between the
  team and the agent.
- Bilingual: technical terms (ZATCA, VAT, e-invoicing) stay as-is even in
  Arabic copy.

**Always use**
"قيود", "ZATCA-compliant", "Saudi SMEs", "real-time", concrete numbers
(USD amounts, % deltas, day-ranges). Reporting currency is USD (peg 3.75
SAR/USD, see `config.USD_SAR_PEG`); native ad-account currencies are
preserved alongside the converted USD value.

**Never use**
Buzzwords: "leverage", "synergy", "unlock", "game-changer". No vague
superlatives. No emojis in internal dashboards unless they carry data
meaning (🟢🟡🟠🔴 for CPL zones is OK — that's signal, not decoration).

**Writing style for Claude**
- Lead with the number/outcome, then the reason.
- Short sentences. Verbs over adjectives.
- When unsure, ask; don't invent data.

---

## 5. Channels & Platforms

| Platform | Active | Frequency | Notes |
|---|---|---|---|
| LinkedIn | Y | ~5/week | Primary B2B channel; thought leadership + case studies |
| Instagram | Y | ~daily | Product tips, customer stories, Reels |
| Twitter / X | Y | ~3/week | Product updates, Saudi tech conversation |
| Snapchat | Y | paid-heavy | Performance ads targeting Saudi SMB owners |
| TikTok | Planned | — | Not yet active |
| YouTube | Y | monthly | Tutorials, webinars (Arabic) |
| Email | Y | weekly | Product newsletter, onboarding sequences |
| WhatsApp | Y | on-demand | Sales + support (Saudi-preferred channel) |
| Website/Blog | Y | 2-4/month | SEO-driven Arabic articles on accounting/ZATCA |
| Google Ads | Y | always-on | Search + PMax; primary lead channel |
| Meta Ads | Y | always-on | FB + IG; awareness + lead-gen |

---

## 6. Content — What Works

**Content pillars**
1. ZATCA / compliance explainers (what changed, what to do)
2. Accounting "how to" for non-accountants (SME owner language)
3. Customer stories (Saudi SMEs, named where permitted)
4. Product updates & feature deep-dives
5. Saudi SME economy / market observations

**Formats**
LinkedIn text posts, Instagram Reels + carousels, YouTube tutorials, long-form
Arabic SEO articles, email newsletter, Snap/Meta ad creatives (short video +
static).

**What works**
- Short LinkedIn posts with a bold first line + concrete Saudi example
- Arabic Reels with real screen recordings of Qoyod doing a task in < 30 sec
- Email subject lines that name the pain ("ZATCA Phase 2 — هل أنت جاهز؟")

**What hasn't worked**
- Generic "5 tips for small businesses" posts — zero engagement
- Long Twitter threads — Saudi audience scrolls past
- English-only ads targeting KSA — CPL 3-5× higher than Arabic equivalents

---

## 7. Goals — What Are You Trying to Achieve?

**Primary goal right now**
Lead generation at controlled CPL/CPQL, for the Qoyod sales team to close.

**Top 3 KPIs the agent tracks** (thresholds are sourced from `config.py` —
do not hardcode in prompts or docs)
1. **CPQL** (Cost Per Qualified Lead) — primary health metric; USD zones:
   🟢 <`CPQL_SCALE` / 🟡 <`CPQL_ACCEPTABLE` / 🟠 <`CPQL_WARNING` / 🔴 ≥`CPQL_WARNING`
2. **CPL** (Cost Per Lead) by channel — USD zones:
   🟢 <`CPL_SCALE` / 🟡 <`CPL_ACCEPTABLE` / 🟠 <`CPL_WARNING` / 🔴 ≥`CPL_WARNING`
3. **Channel ROAS** (won-deal revenue ÷ spend) — tracked daily, rolled monthly

**90-day success**
- All 8 collectors running 4×/day on Replit with <1% failure rate
- Streamlit dashboard deployed + shared with CEO & performance team
- UTM-level attribution live (with `__no_utm__` bucket) so every campaign
  ties to leads + deals + USD revenue
- Agent auto-posts pause/scale recommendations to Slack, acted on ≥ 5×/week

---

## 8. Context — Anything Else Claude Must Know

**Cultural / market**
- Saudi calendar matters: **Ramadan** (shifts consumption & working hours),
  **National Day Sept 23**, **Founding Day Feb 22**, **White Friday Nov**,
  **Riyadh Season**. Plan campaigns 6–8 weeks ahead.
- Arabic: always MSA in written copy, never colloquial (Saudi/Egyptian/Khaleeji).
- Weekend = **Friday–Saturday** in KSA. Schedule collectors & reports in
  **Asia/Riyadh (UTC+3)**.

**Industry / regulatory**
- **ZATCA** e-invoicing Phase 2 integration is the defining compliance topic.
  Never give compliance advice that contradicts ZATCA specs.
- VAT rate in KSA is 15%.
- Currency: **reporting in USD** (peg 3.75 SAR/USD via `config.USD_SAR_PEG`).
  Each ad-account's native currency is detected and preserved alongside
  the USD-converted value (`spend`, `currency`="USD", `spend_native`,
  `currency_native`). Platforms that return micros (Google Ads
  `cost_micros`, Snap spend micro) must be divided by 1,000,000 BEFORE
  the USD conversion (see `memory/08_pitfalls.md`).

**Agent team** (authoritative roster: `docs/_shared/org-chart.md`)

The team is **9 Claude Code subagents** = 1 manager + 3 departments (see
`CLAUDE.manager.md` for how they run):
- **Manager:** `ai-orchestrator` — 8-step loop 08:00, gates writes ✅, owns handoffs.
- **Performance** (LEAD `performance-lead`): `campaign-manager` ∥ `creative-strategist`.
- **CRO / Landing Page** (sequential): `cro-specialist` (brief + design) → `developer`.
- **Support** (parallel): `project-coordinator` ∥ `growth-analyst` (owns `memory/`).

> **Note:** `claude/roles.py`, `runtime_personas/`, `main.py`, and `reporting_scheduler.py`
> were all **deleted on 2026-06-16** as part of the Railway deprecation. The dev-time
> subagents in `.claude/agents/` are now the single active layer. See `memory/11_agent_roles.md`.

**Tech stack** (authoritative — see `memory/` for details)
- **Data:** BigQuery (project-dataset via `.env`), load-job writes only, no streaming
- **Orchestration:** n8n Cloud (daily/weekly/monthly analysis + Slack + Asana + approval gates)
- **Data collection:** GitHub Actions (`.github/workflows/collectors.yml` — Python BQ collectors every 6h at 00/06/12/18 UTC)
- **CRM:** HubSpot (Lead module = object `0-136`, standard Deals)
- **Ads:** Google Ads (MCC + children), Meta (2 ad accounts), Snap, LinkedIn
- **Organic:** Meta (FB+IG), YouTube, LinkedIn
- **Dashboard:** Hex (internal) + Databox (team-facing external)
- **AI analysis:** Claude API via n8n HTTP Request nodes (12 workflows)
- **Ops:** Slack approvals, Asana tasks
- **Storage:** Google Drive (shared creative + reporting folder — see Drive
  section below)
- **Hosting:** Railway (deprecated — pending shutdown; GitHub Actions runs collectors independently)

**Never say, assume, or do**
- Never PATCH/DELETE/CREATE HubSpot objects without explicit Slack approval
  from Amar (user has repeated this rule).
- Never hard-code credentials in code; always read from `.env` / Replit
  Secrets.
- Never use streaming BQ inserts (`insert_rows_json`) — breaks DELETE for
  90 min. Always use `load_table_from_file(BytesIO(ndjson))`.
- Never recommend tools not available in KSA or that conflict with Islamic
  values (no gambling / alcohol / etc. adjacencies).
- Never produce content in colloquial Arabic for official channels.
- Never assume — if a field/property/account is unclear, ask in Slack or
  pause and surface the question.

---

## Google Drive — Shared Knowledge Folder

**Folder:** https://drive.google.com/drive/folders/1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74
**Folder ID:** `1yI0-3TirRuVAxKIKrq2aR-9gVB2UdT74`

How Claude is connected to Drive → see `memory/10_google_drive.md`.

---

## How to use this Playbook

1. **Every new Claude session** reads this file first, then `memory/00_index.md`.
2. This Playbook = **who & why**. `memory/` = **what & how** (architecture,
   collectors, pitfalls, open tasks).
3. When strategy, audience, or goals change — update the relevant section
   here and commit.
