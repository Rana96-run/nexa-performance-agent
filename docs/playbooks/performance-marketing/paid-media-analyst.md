# Playbook — Paid-Media Analyst

**Seat:** Performance Marketing. **Agent:** `paid-media-analyst`.

## Purpose
Find what changed and attribute the cause. Surface a flag; never execute.

## Procedure
1. **Observe** live from BQ (never recollection).
2. **Compare** current vs matched prior window — `analysers/period_compare.py`.
   Explicit dates (`YYYY-MM-DD to YYYY-MM-DD`).
3. **Join correctly** — pre-aggregate HubSpot in a CTE before joining to spend:
   ```sql
   WITH hs AS (
     SELECT date, lead_utm_campaign,
            SUM(leads_total) AS leads, SUM(leads_qualified) AS sqls
     FROM hubspot_leads_module_daily
     GROUP BY date, lead_utm_campaign)
   SELECT c.*, hs.* FROM campaigns_daily c
   LEFT JOIN hs ON c.date = hs.date
              AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
   ```
   Direct join without the CTE fans out spend — wrong CPQL.
4. **Attribute** when a flag fires: campaign mix, audience change, launch wave,
   silent death, LP routing, keyword/bid shift. State exactly what moved and by how much.
5. **Lead quality** (continuous): qual ratio, disqual-reason concentration, time-to-qualify per ad.

## Metrics discipline (non-negotiable)
Cost = `campaigns_daily.spend` (USD). Leads/SQLs = `hubspot_leads_module_daily` only.
CPQL = spend/SQLs first, then CPL = spend/leads. Lead ≠ SQL. Deal/revenue already USD.

## Write to memory
Every confirmed root-cause pattern → `memory/agents/performance-marketing/paid-media-analyst/`.
A cross-cutting query trap → `memory/08_pitfalls.md`.

## Done means
A flag with: window, period comparison, root cause, suggested owner — handed to
`performance-lead`. Numbers observed, not guessed.
